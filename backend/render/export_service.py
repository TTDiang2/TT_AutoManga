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
from typing import Iterator, List, Tuple
from PIL import Image
from . import render_page

# Maximum viewer compatibility: embed images FlateDecode-only (no ASCII85
# layer). Some PDF viewers render A85+Flate filter arrays as blank pages.
from reportlab import rl_config as _rl_config
_rl_config.useA85 = 0


def _stamp_page_number(img: Image.Image, index: int, scale: float) -> None:
    """Number a page bottom-center; page 1 (the cover) stays unnumbered."""
    if index == 0:
        return
    from PIL import ImageDraw
    from .fonts import get_font
    d = ImageDraw.Draw(img)
    fs = max(10, int(14 * scale))
    font = get_font(fs)
    label = str(index + 1)
    w = font.getlength(label)
    d.text(((img.width - w) / 2, img.height - fs * 1.8), label,
           font=font, fill=(102, 102, 102, 255))


def _stamp_page_numbers(images: List[Image.Image], scale: float) -> None:
    for i, img in enumerate(images):
        _stamp_page_number(img, i, scale)


def _iter_pages(pages: List[dict], scale: float, resolve,
                page_numbers: bool) -> Iterator[Tuple[int, dict, Image.Image]]:
    """Render one page at a time: a 30-page export at scale 2 must never
    hold every page image in memory at once."""
    for i, page in enumerate(pages):
        img = render_page(page, scale, resolve)
        if page_numbers:
            _stamp_page_number(img, i, scale)
        yield i, page, img


class _PdfWriter:
    """Incremental PDF: each page is embedded as soon as it is rendered."""

    def __init__(self, target):
        from reportlab.pdfgen import canvas as rl_canvas
        self._rl_canvas = rl_canvas
        self.target = target
        self.c = None

    def add(self, img: Image.Image, page: dict) -> None:
        from reportlab.lib.utils import ImageReader
        w = page.get("width", 600)
        h = page.get("height", 900)
        if self.c is None:
            self.c = self._rl_canvas.Canvas(self.target, pagesize=(w, h))
        else:
            self.c.setPageSize((w, h))
        self.c.drawImage(ImageReader(img), 0, 0, width=w, height=h)
        self.c.showPage()

    def close(self) -> None:
        if self.c is not None:
            self.c.save()


def _png_bytes(img: Image.Image) -> bytes:
    b = io.BytesIO()
    img.save(b, format="PNG")
    return b.getvalue()


def export_pages_to_bytes(pages: List[dict], fmt: str, scale: float,
                          resolve, page_numbers: bool = False) -> dict:
    """fmt ∈ pdf|zip|both → {"pdf": bytes|None, "zip": bytes|None}."""
    if fmt not in ("pdf", "zip", "both"):
        raise ValueError(f"unknown export format: {fmt}")
    pdf_buf = io.BytesIO() if fmt in ("pdf", "both") else None
    zip_buf = io.BytesIO() if fmt in ("zip", "both") else None
    pdf = _PdfWriter(pdf_buf) if pdf_buf else None
    # PNGs are already deflate-compressed: store them, don't re-compress
    zf = zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_STORED) if zip_buf else None
    try:
        for i, page, img in _iter_pages(pages, scale, resolve, page_numbers):
            if pdf:
                pdf.add(img, page)
            if zf:
                zf.writestr(f"page_{i + 1:03d}.png", _png_bytes(img))
            del img
    finally:
        if zf:
            zf.close()
    if pdf:
        pdf.close()
    return {"pdf": pdf_buf.getvalue() if pdf_buf else None,
            "zip": zip_buf.getvalue() if zip_buf else None}


def export_pages(pages: List[dict], fmt: str, scale: float, resolve,
                 out_dir: Path, base_name: str,
                 page_numbers: bool = False) -> dict:
    """Render + write PNGs/PDF/ZIP; returns paths and /api/export/download URLs."""
    out_dir.mkdir(parents=True, exist_ok=True)
    png_dir = out_dir / f"{base_name}_pages"
    png_dir.mkdir(exist_ok=True)

    pdf_path = out_dir / f"{base_name}.pdf"
    pdf = _PdfWriter(str(pdf_path)) if fmt in ("pdf", "both") else None
    png_files: List[Path] = []
    for i, page, img in _iter_pages(pages, scale, resolve, page_numbers):
        f = png_dir / f"page_{i + 1:03d}.png"
        img.save(f, format="PNG")
        png_files.append(f)
        if pdf:
            pdf.add(img, page)
        del img   # drop the page before rendering the next one
    if pdf:
        pdf.close()

    result: dict = {"pages_dir": str(png_dir)}
    if pdf:
        result["pdf"] = {"path": str(pdf_path),
                         "url": f"/api/export/download/{pdf_path.name}"}
    if fmt in ("zip", "both"):
        zip_path = out_dir / f"{base_name}.zip"
        # build the ZIP from the PNG files just written, stored as-is
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
            for f in png_files:
                zf.write(f, f.name)
        result["zip"] = {"path": str(zip_path),
                         "url": f"/api/export/download/{zip_path.name}"}
    return result
