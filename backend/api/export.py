from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import io
import zipfile
import uuid
import base64
import logging
from pathlib import Path

router = APIRouter(prefix="/api/export", tags=["export"])

logger = logging.getLogger(__name__)

EXPORTS_DIR = Path(__file__).parent.parent.parent / "data" / "exports"
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
EXPORTS_ROOT = EXPORTS_DIR.resolve()


def _panel_image_bytes(image: str) -> Optional[bytes]:
    """Resolve a panel image ref (data URL / asset URL / local path) to bytes."""
    try:
        if image.startswith("data:"):
            return base64.b64decode(image.split(",", 1)[1])
        if image.startswith("/api/assets/file/"):
            from ..storage.asset_store import asset_store
            path = asset_store.path_for(image.rsplit("/", 1)[-1])
            return path.read_bytes() if path else None
        path = Path(image)
        return path.read_bytes() if path.is_file() else None
    except Exception:
        return None


class ExportPDFRequest(BaseModel):
    project_id: str
    panels: List[Dict[str, Any]]
    page_size: str = "A4"
    quality: str = "high"
    include_cover: bool = True


class ExportImagesRequest(BaseModel):
    project_id: str
    panels: List[Dict[str, Any]]
    format: str = "png"


class ComposerPageRequest(BaseModel):
    name: str = "page"
    dataUrl: str = ""


class ComposerExportRequest(BaseModel):
    pages: List[ComposerPageRequest]


@router.post("/pdf")
async def export_pdf(req: ExportPDFRequest):
    try:
        from reportlab.lib.pagesizes import A4, LETTER
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import inch
        import base64
        
        page_sizes = {"A4": A4, "LETTER": LETTER}
        page_size = page_sizes.get(req.page_size, A4)
        
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=page_size)
        width, height = page_size
        
        if req.include_cover:
            c.setFont("Helvetica-Bold", 36)
            c.drawString(1*inch, height - 2*inch, f"Project: {req.project_id}")
            c.showPage()
        
        quality_mult = 2 if req.quality == "high" else 1
        
        for i, panel in enumerate(req.panels):
            if panel.get("image"):
                img_bytes = _panel_image_bytes(panel["image"])
                if img_bytes:
                    img_stream = io.BytesIO(img_bytes)

                    try:
                        from reportlab.lib.utils import ImageReader
                        img_reader = ImageReader(img_stream)
                        img_width, img_height = img_reader.getSize()
                        
                        aspect = img_height / img_width
                        draw_width = width - 2*inch
                        draw_height = draw_width * aspect
                        
                        if draw_height > height - 2*inch:
                            draw_height = height - 2*inch
                            draw_width = draw_height / aspect
                        
                        x = (width - draw_width) / 2
                        y = height - draw_height - 1*inch
                        
                        c.drawImage(img_reader, x, y, width=draw_width, height=draw_height)
                    except Exception as e:
                        logger.warning("export pdf: skipping unreadable image: %s", e)
            
            c.showPage()
        
        c.save()
        buffer.seek(0)
        
        filename = f"manga_{req.project_id}_{uuid.uuid4().hex[:8]}.pdf"
        output_path = EXPORTS_DIR / filename
        
        with open(output_path, "wb") as f:
            f.write(buffer.read())
        
        return {"success": True, "file": str(output_path)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/images")
async def export_images(req: ExportImagesRequest):
    try:
        import base64
        import uuid
        
        output_dir = EXPORTS_DIR / f"images_{uuid.uuid4().hex[:8]}"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for i, panel in enumerate(req.panels):
            if panel.get("image"):
                img_bytes = _panel_image_bytes(panel["image"])
                if img_bytes:
                    filename = output_dir / f"panel_{i+1:03d}.{req.format}"
                    with open(filename, "wb") as f:
                        f.write(img_bytes)
        
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for img_file in output_dir.glob("*"):
                zf.write(img_file, img_file.name)
        
        buffer.seek(0)
        
        zip_filename = f"manga_{req.project_id}_{uuid.uuid4().hex[:8]}.zip"
        output_path = EXPORTS_DIR / zip_filename
        
        with open(output_path, "wb") as f:
            f.write(buffer.read())
        
        return {"success": True, "file": str(output_path)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/composer-pdf")
async def export_composer_pdf(req: ComposerExportRequest):
    try:
        from reportlab.lib.pagesizes import A4, LETTER
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import inch

        page_size = A4
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=page_size)
        width, height = page_size

        for page in req.pages:
            c.setFillColorRGB(1, 1, 1)
            c.rect(0, 0, width, height, fill=1)
            if page.dataUrl:
                img_data = page.dataUrl
                if img_data.startswith("data:"):
                    img_data = img_data.split(",", 1)[1]
                try:
                    img_bytes = base64.b64decode(img_data)
                    img_stream = io.BytesIO(img_bytes)
                    from reportlab.lib.utils import ImageReader
                    img_reader = ImageReader(img_stream)
                    img_w, img_h = img_reader.getSize()
                    aspect = img_h / img_w
                    draw_w = width - 2 * inch
                    draw_h = draw_w * aspect
                    if draw_h > height - 2 * inch:
                        draw_h = height - 2 * inch
                        draw_w = draw_h / aspect
                    x = (width - draw_w) / 2
                    y = height - draw_h - 1 * inch
                    c.drawImage(img_reader, x, y, width=draw_w, height=draw_h)
                except Exception as e:
                    logger.warning("composer pdf: skipping unreadable page image: %s", e)
            c.showPage()

        c.save()
        buffer.seek(0)

        filename = f"composer_{uuid.uuid4().hex[:8]}.pdf"
        output_path = EXPORTS_DIR / filename
        with open(output_path, "wb") as f:
            f.write(buffer.read())

        return {
            "success": True,
            "downloadUrl": f"/api/export/download/{filename}"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/composer-images")
async def export_composer_images(req: ComposerExportRequest):
    try:
        zip_name = f"composer_{uuid.uuid4().hex[:8]}.zip"
        zip_path = EXPORTS_DIR / zip_name

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for i, page in enumerate(req.pages):
                if page.dataUrl and page.dataUrl.startswith("data:"):
                    img_data = page.dataUrl.split(",", 1)[1]
                    try:
                        img_bytes = base64.b64decode(img_data)
                        fname = f"{page.name or 'page'}_{i+1:03d}.png"
                        zf.writestr(fname, img_bytes)
                    except Exception as e:
                        logger.warning("composer zip: skipping undecodable page %d: %s", i + 1, e)

        return {
            "success": True,
            "downloadUrl": f"/api/export/download/{zip_name}"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/{filename}")
async def download_file(filename: str):
    path = (EXPORTS_DIR / filename).resolve()
    # filename is client-supplied and may carry ../ segments; only serve
    # files that resolve inside data/exports
    if not path.is_relative_to(EXPORTS_ROOT):
        raise HTTPException(status_code=404, detail="File not found")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, media_type="application/octet-stream", filename=filename)
