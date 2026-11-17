from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import asyncio
import io
import re
import zipfile
import uuid
import base64
import logging
import shutil
from pathlib import Path

from ..render.export_service import prune_exports
from ..render.resolve import ref_to_bytes
from ..storage.manager import validate_project_id, InvalidProjectIdError

router = APIRouter(prefix="/api/export", tags=["export"])

logger = logging.getLogger(__name__)

EXPORTS_DIR = Path(__file__).parent.parent.parent / "data" / "exports"
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
EXPORTS_ROOT = EXPORTS_DIR.resolve()


def _panel_image_bytes(image: str) -> Optional[bytes]:
    """Resolve a panel image ref to bytes. Only data: URLs, managed assets
    and archive images are accepted — never a filesystem path, which would
    let any client zip up and download arbitrary local files."""
    from ..storage.asset_store import asset_store
    return ref_to_bytes(image, asset_store)


def _checked_project_id(project_id: str) -> str:
    # project_id ends up in an export file name
    try:
        return validate_project_id(project_id)
    except InvalidProjectIdError as e:
        raise HTTPException(status_code=400, detail=str(e))


_IMAGE_FORMATS = {"png", "jpg", "jpeg", "webp"}


def _safe_entry_name(name: str) -> str:
    """Client-supplied page names become ZIP entry names: keep them flat."""
    cleaned = re.sub(r"[^\w\- ]", "_", name or "").strip()
    return cleaned[:80] or "page"


def _fit_on_page(img_reader, width: float, height: float, inch: float):
    """Centered draw box (x, y, w, h) keeping 1in margins and aspect."""
    img_w, img_h = img_reader.getSize()
    aspect = img_h / img_w
    draw_w = width - 2 * inch
    draw_h = draw_w * aspect
    if draw_h > height - 2 * inch:
        draw_h = height - 2 * inch
        draw_w = draw_h / aspect
    return (width - draw_w) / 2, height - draw_h - 1 * inch, draw_w, draw_h


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


# The export bodies are CPU-bound PIL/reportlab work; the endpoints run them
# with asyncio.to_thread so a long export never freezes the event loop.

def _export_pdf_sync(req: ExportPDFRequest) -> dict:
    from reportlab.lib.pagesizes import A4, LETTER
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import inch
    from reportlab.lib.utils import ImageReader

    page_size = {"A4": A4, "LETTER": LETTER}.get(req.page_size, A4)
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=page_size)
    width, height = page_size

    if req.include_cover:
        c.setFont("Helvetica-Bold", 36)
        c.drawString(1*inch, height - 2*inch, f"Project: {req.project_id}")
        c.showPage()

    for panel in req.panels:
        if panel.get("image"):
            img_bytes = _panel_image_bytes(panel["image"])
            if img_bytes:
                try:
                    img_reader = ImageReader(io.BytesIO(img_bytes))
                    x, y, w, h = _fit_on_page(img_reader, width, height, inch)
                    c.drawImage(img_reader, x, y, width=w, height=h)
                except Exception as e:
                    logger.warning("export pdf: skipping unreadable image: %s", e)
        c.showPage()

    c.save()
    filename = f"manga_{req.project_id}_{uuid.uuid4().hex[:8]}.pdf"
    output_path = EXPORTS_DIR / filename
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(buffer.getvalue())
    prune_exports(EXPORTS_DIR, keep={output_path.stem})
    return {"success": True, "file": str(output_path)}


@router.post("/pdf")
async def export_pdf(req: ExportPDFRequest):
    _checked_project_id(req.project_id)
    try:
        return await asyncio.to_thread(_export_pdf_sync, req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _export_images_sync(req: ExportImagesRequest) -> dict:
    zip_filename = f"manga_{req.project_id}_{uuid.uuid4().hex[:8]}.zip"
    output_path = EXPORTS_DIR / zip_filename
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, panel in enumerate(req.panels):
            if panel.get("image"):
                img_bytes = _panel_image_bytes(panel["image"])
                if img_bytes:
                    zf.writestr(f"panel_{i+1:03d}.{req.format}", img_bytes)
    prune_exports(EXPORTS_DIR, keep={output_path.stem})
    return {"success": True, "file": str(output_path)}


@router.post("/images")
async def export_images(req: ExportImagesRequest):
    _checked_project_id(req.project_id)
    # format becomes a file extension
    if req.format.lower() not in _IMAGE_FORMATS:
        raise HTTPException(status_code=400,
                            detail=f"format must be one of {sorted(_IMAGE_FORMATS)}")
    try:
        return await asyncio.to_thread(_export_images_sync, req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _export_composer_pdf_sync(req: ComposerExportRequest) -> dict:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import inch
    from reportlab.lib.utils import ImageReader

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
                img_reader = ImageReader(io.BytesIO(base64.b64decode(img_data)))
                x, y, w, h = _fit_on_page(img_reader, width, height, inch)
                c.drawImage(img_reader, x, y, width=w, height=h)
            except Exception as e:
                logger.warning("composer pdf: skipping unreadable page image: %s", e)
        c.showPage()

    c.save()
    filename = f"composer_{uuid.uuid4().hex[:8]}.pdf"
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (EXPORTS_DIR / filename).write_bytes(buffer.getvalue())
    prune_exports(EXPORTS_DIR, keep={Path(filename).stem})
    return {"success": True, "downloadUrl": f"/api/export/download/{filename}"}


@router.post("/composer-pdf")
async def export_composer_pdf(req: ComposerExportRequest):
    try:
        return await asyncio.to_thread(_export_composer_pdf_sync, req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _export_composer_images_sync(req: ComposerExportRequest) -> dict:
    zip_name = f"composer_{uuid.uuid4().hex[:8]}.zip"
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(EXPORTS_DIR / zip_name, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, page in enumerate(req.pages):
            if page.dataUrl and page.dataUrl.startswith("data:"):
                try:
                    img_bytes = base64.b64decode(page.dataUrl.split(",", 1)[1])
                    fname = f"{_safe_entry_name(page.name)}_{i+1:03d}.png"
                    zf.writestr(fname, img_bytes)
                except Exception as e:
                    logger.warning("composer zip: skipping undecodable page %d: %s", i + 1, e)
    prune_exports(EXPORTS_DIR, keep={Path(zip_name).stem})
    return {"success": True, "downloadUrl": f"/api/export/download/{zip_name}"}


@router.post("/composer-images")
async def export_composer_images(req: ComposerExportRequest):
    try:
        return await asyncio.to_thread(_export_composer_images_sync, req)
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


# what the export endpoints write: a flat <name>.pdf or <name>.zip
_EXPORT_FILE_RE = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9_.-]{0,200}\.(?:pdf|zip)")


@router.delete("/download/{filename}")
async def delete_export(filename: str):
    """Remove an export (once a client has downloaded it) and, when no PDF or
    ZIP of the same name is left, its <name>_pages/ folder of page PNGs."""
    if not _EXPORT_FILE_RE.fullmatch(filename) or ".." in filename:
        raise HTTPException(status_code=400, detail="not an export file name")
    root = EXPORTS_DIR.resolve()
    path = (EXPORTS_DIR / filename).resolve()
    if path.parent != root or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    path.unlink()
    deleted = [filename]
    stem = path.stem
    pages = EXPORTS_DIR / f"{stem}_pages"
    siblings = [EXPORTS_DIR / f"{stem}{ext}" for ext in (".pdf", ".zip")]
    if pages.is_dir() and not pages.is_symlink() \
            and pages.resolve().parent == root \
            and not any(p.exists() for p in siblings):
        shutil.rmtree(pages)
        deleted.append(pages.name)
    logger.info("export deleted: %s", ", ".join(deleted))
    return {"success": True, "deleted": deleted}
