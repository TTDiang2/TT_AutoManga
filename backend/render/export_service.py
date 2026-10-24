"""Shared page-export service.

Two entry points over the same renderer:
- export_pages_to_bytes: in-memory PDF/ZIP (used by POST /api/render/export)
- export_pages: writes files under data/exports and returns download URLs
  (used by POST /api/agent/export)

PDF pages are sized 1 image px = 1 pt, i.e. the page's own width/height.
"""
import io
import zipfile
from pathlib import Path
from typing import Callable, List, Optional
from PIL import Image
from . import render_page

# Maximum viewer compatibility: embed images FlateDecode-only (no ASCII85
# layer). Some PDF viewers render A85+Flate filter arrays as blank pages.
from reportlab import rl_config as _rl_config
_rl_config.useA85 = 0


def _render_pngs(pages: List[dict], scale: float, resolve) -> List[Image.Image]:
    return [render_page(p, scale, resolve) for p in pages]


def _stamp_page_numbers(images: List[Image.Image], scale: float) -> None:
    """Number pages bottom-center; page 1 (the cover) stays unnumbered."""
    from PIL import ImageDraw
    from .fonts import get_font
    for i, img in enumerate(images):
        if i == 0:
            continue
        d = ImageDraw.Draw(img)
        fs = max(10, int(14 * scale))
        font = get_font(fs)
        label = str(i + 1)
        w = font.getlength(label)
        d.text(((img.width - w) / 2, img.height - fs * 1.8), label,
               font=font, fill=(102, 102, 102, 255))


def _build_pdf(images: List[Image.Image], pages: List[dict]) -> bytes:
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.utils import ImageReader
    buf = io.BytesIO()
    c = None
    for img, page in zip(images, pages):
        w = page.get("width", 600)
        h = page.get("height", 900)
        if c is None:
            c = rl_canvas.Canvas(buf, pagesize=(w, h))
        else:
            c.setPageSize((w, h))
        c.drawImage(ImageReader(img), 0, 0, width=w, height=h)
        c.showPage()
    c.save()
    return buf.getvalue()


def _build_zip(images: List[Image.Image]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, img in enumerate(images):
            b = io.BytesIO()
            img.save(b, format="PNG")
            zf.writestr(f"page_{i + 1:03d}.png", b.getvalue())
    return buf.getvalue()


def export_pages_to_bytes(pages: List[dict], fmt: str, scale: float,
                          resolve, page_numbers: bool = False) -> dict:
    """fmt ∈ pdf|zip|both → {"pdf": bytes|None, "zip": bytes|None}."""
    if fmt not in ("pdf", "zip", "both"):
        raise ValueError(f"unknown export format: {fmt}")
    images = _render_pngs(pages, scale, resolve)
    if page_numbers:
        _stamp_page_numbers(images, scale)
    out = {"pdf": None, "zip": None}
    if fmt in ("pdf", "both"):
        out["pdf"] = _build_pdf(images, pages)
    if fmt in ("zip", "both"):
        out["zip"] = _build_zip(images)
    return out


def export_pages(pages: List[dict], fmt: str, scale: float, resolve,
                 out_dir: Path, base_name: str,
                 page_numbers: bool = False) -> dict:
    """Render + write PNGs/PDF/ZIP; returns paths and /api/export/download URLs."""
    out_dir.mkdir(parents=True, exist_ok=True)
    images = _render_pngs(pages, scale, resolve)
    if page_numbers:
        _stamp_page_numbers(images, scale)

    png_dir = out_dir / f"{base_name}_pages"
    png_dir.mkdir(exist_ok=True)
    for i, img in enumerate(images):
        img.save(png_dir / f"page_{i + 1:03d}.png", format="PNG")

    result: dict = {"pages_dir": str(png_dir)}
    exports_parent = out_dir
    if fmt in ("pdf", "both"):
        pdf_path = exports_parent / f"{base_name}.pdf"
        pdf_path.write_bytes(_build_pdf(images, pages))
        result["pdf"] = {"path": str(pdf_path),
                         "url": f"/api/export/download/{pdf_path.name}"}
    if fmt in ("zip", "both"):
        zip_path = exports_parent / f"{base_name}.zip"
        zip_path.write_bytes(_build_zip(images))
        result["zip"] = {"path": str(zip_path),
                         "url": f"/api/export/download/{zip_path.name}"}
    return result
