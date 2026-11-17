"""Collection export: every episode of a collection in one PDF and/or ZIP.

Output order: an optional generated collection cover, then per episode an
optional generated title page (collection name, the episode's subtitle, a
thumbnail of its first page) followed by the episode's own pages. Pages are
rendered ONE at a time into a temp dir (and straight into the incremental
PDF); the ZIP is assembled from those PNG files afterwards, so memory stays
at about one page image whatever the collection's length.

Generated pages are ordinary page dicts drawn by the shared renderer and
fonts (titles in font family "title" when data/fonts has one). Their images
(thumbnail, cover art) are pre-rendered pages handed to the renderer through
a resolver wrapper under THUMB_PREFIX refs.
"""
import logging
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from PIL import Image

from . import render_page as _render_page
from .export_service import PdfWriter, prune_exports, stamp_label
from ..storage.collections import split_title

logger = logging.getLogger(__name__)

THUMB_PREFIX = "collection-thumb:"
DEFAULT_W, DEFAULT_H = 600, 900

# tests swap this for a slow / counting renderer
render_page = _render_page


def plan_episodes(collection: Dict[str, Any],
                  load_project: Callable[[str], Optional[Dict[str, Any]]]
                  ) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Episodes to export, in collection order: [{id, name, title, pages}].
    Missing projects and episodes without pages are skipped with a warning."""
    episodes: List[Dict[str, Any]] = []
    warnings: List[str] = []
    cname = collection.get("name") or ""
    for pid in collection.get("projectIds") or []:
        try:
            project = load_project(pid)
        except Exception as e:   # unreadable / invalid id
            project = None
            logger.warning("collection %s: cannot load project %s: %s",
                           collection.get("id"), pid, e)
        if not project:
            msg = f"project {pid} not found; skipped"
            logger.warning("collection %s: %s", collection.get("id"), msg)
            warnings.append(msg)
            continue
        pages = project.get("composerPages") or []
        name = project.get("name") or pid
        if not pages:
            msg = f"project {name!r} has no pages; skipped"
            logger.warning("collection %s: %s", collection.get("id"), msg)
            warnings.append(msg)
            continue
        base, sub = split_title(name)
        title = sub if sub and base == cname else name
        episodes.append({"id": pid, "name": name, "title": title, "pages": pages})
    return episodes, warnings


def page_total(episodes: List[Dict[str, Any]], cover: bool,
               episode_title_pages: bool) -> int:
    return (1 if cover and episodes else 0) + sum(
        len(e["pages"]) + (1 if episode_title_pages else 0) for e in episodes)


def _text(content: str, y: float, h: float, size: float, *, family: str = "",
          bold: bool = False, color: str = "#111111", stroke: float = 0,
          x: float = 8, w: float = 84) -> Dict[str, Any]:
    return {"id": uuid.uuid4().hex, "type": "text", "content": content,
            "x": x, "y": y, "width": w, "height": h, "rotation": 0,
            "zIndex": 2, "visible": True, "fontSize": size,
            "fontFamily": family, "color": color, "direction": "horizontal",
            "fontWeight": "bold" if bold else "normal", "textAlign": "center",
            "strokeWidth": stroke, "strokeColor": "#000000"}


def _image(ref: str, x: float, y: float, w: float, h: float,
           border: float) -> Dict[str, Any]:
    return {"id": uuid.uuid4().hex, "type": "image", "src": ref,
            "x": x, "y": y, "width": w, "height": h, "rotation": 0,
            "zIndex": 1, "visible": True, "frameBorderWidth": border}


def _page(name: str, w: int, h: int, elements: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"id": uuid.uuid4().hex, "name": name, "width": w, "height": h,
            "elements": elements}


def _render_scaled(page: Dict[str, Any], target_w_px: float, resolve) -> Image.Image:
    """Render a source page so its width is about target_w_px."""
    pw = float(page.get("width") or DEFAULT_W)
    return render_page(page, max(0.05, min(8.0, target_w_px / pw)), resolve)


def _cover_page(collection: Dict[str, Any], episodes: List[Dict[str, Any]],
                W: int, H: int, scale: float, resolve) -> Tuple[Dict[str, Any], Dict[str, Image.Image]]:
    art_page = None
    chosen = collection.get("cover") or {}
    ep = next((e for e in episodes if e["id"] == chosen.get("projectId")), None)
    if ep is not None:
        art_page = next((p for p in ep["pages"] if p.get("id") == chosen.get("pageId")),
                        ep["pages"][0])
    if art_page is None:
        art_page = episodes[0]["pages"][0]
    ref = THUMB_PREFIX + "cover"
    art = _render_scaled(art_page, W * scale, resolve)
    els = [_image(ref, 0, 0, 100, 100, 0),
           _text(collection.get("name") or "", 6, 16, 56, family="title",
                 bold=True, color="#ffffff", stroke=6)]
    desc = (collection.get("description") or "").strip()
    if desc:
        els.append(_text(desc, 23, 8, 22, color="#ffffff", stroke=3, x=12, w=76))
    return _page("cover", W, H, els), {ref: art}


def _title_page(collection: Dict[str, Any], ep: Dict[str, Any], W: int, H: int,
                scale: float, resolve) -> Tuple[Dict[str, Any], Dict[str, Image.Image]]:
    first = ep["pages"][0]
    fw = float(first.get("width") or DEFAULT_W)
    fh = float(first.get("height") or DEFAULT_H)
    # thumbnail box: 50% of the page width, aspect kept, at most 55% high
    bw = 50.0
    bh = bw * (fh / fw) * (W / H)
    if bh > 55.0:
        bh = 55.0
        bw = bh * (fw / fh) * (H / W)
    ref = THUMB_PREFIX + "thumb"
    thumb = _render_scaled(first, bw / 100 * W * scale, resolve)
    els = [_text(collection.get("name") or "", 7, 7, 26, family="title",
                 color="#555555"),
           _text(ep["title"], 15, 14, 44, family="title", bold=True),
           _image(ref, (100 - bw) / 2, 34, bw, bh, 1.5)]
    return _page(f"title: {ep['name']}", W, H, els), {ref: thumb}


def _with_images(resolve, images: Dict[str, Image.Image]):
    def r(url: str):
        if isinstance(url, str) and url.startswith(THUMB_PREFIX):
            return images.get(url)
        return resolve(url) if resolve else None
    return r


def _generated(page: Dict[str, Any], images: Dict[str, Image.Image], scale: float,
               resolve) -> Tuple[Dict[str, Any], Image.Image]:
    return page, render_page(page, scale, _with_images(resolve, images))


def _iter_output(collection, episodes, scale, resolve, cover: bool,
                 episode_title_pages: bool) -> Iterator[Tuple[Dict[str, Any], Image.Image, bool]]:
    """(page, rendered image, is_cover) one at a time."""
    first = episodes[0]["pages"][0]
    W = int(first.get("width") or DEFAULT_W)
    H = int(first.get("height") or DEFAULT_H)
    # no rendered image is kept in a local across a yield: the consumer's
    # page is the only one alive while it is written out
    if cover:
        yield _generated(*_cover_page(collection, episodes, W, H, scale, resolve),
                         scale, resolve) + (True,)
    for ep in episodes:
        if episode_title_pages:
            yield _generated(*_title_page(collection, ep, W, H, scale, resolve),
                             scale, resolve) + (False,)
        for page in ep["pages"]:
            yield page, render_page(page, scale, resolve), False


def export_collection(collection: Dict[str, Any], episodes: List[Dict[str, Any]],
                      fmt: str, scale: float, resolve, out_dir: Path,
                      base_name: str, *, page_numbers: bool = False,
                      episode_title_pages: bool = True, cover: bool = False,
                      progress: Optional[Callable[[int, int], None]] = None) -> dict:
    """Write <base_name>.pdf / .zip under out_dir; returns
    {pages, pdf?: {path, url}, zip?: {path, url}}. Page numbers run across
    the whole collection; the generated cover is page 1 and unnumbered."""
    if fmt not in ("pdf", "zip", "both"):
        raise ValueError(f"unknown export format: {fmt}")
    if not episodes:
        raise ValueError("collection has no episodes with pages to export")
    total = page_total(episodes, cover, episode_title_pages)
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / f"{base_name}.pdf"
    zip_path = out_dir / f"{base_name}.zip"
    want_pdf, want_zip = fmt in ("pdf", "both"), fmt in ("zip", "both")
    pdf_part = out_dir / f".{base_name}.pdf.part"
    zip_part = out_dir / f".{base_name}.zip.part"
    tmp = Path(tempfile.mkdtemp(prefix="automanga_collection_"))
    digits = max(3, len(str(total)))
    try:
        pdf = PdfWriter(str(pdf_part)) if want_pdf else None
        png_files: List[Path] = []
        done = 0
        for i, (page, img, is_cover) in enumerate(_iter_output(
                collection, episodes, scale, resolve, cover, episode_title_pages)):
            if page_numbers and not is_cover:
                stamp_label(img, str(i + 1), scale)
            if want_zip:
                f = tmp / f"page_{i + 1:0{digits}d}.png"
                img.save(f, format="PNG")
                png_files.append(f)
            if pdf:
                pdf.add(img, page)
            del img   # drop the page before rendering the next one
            done += 1
            if progress:
                progress(done, total)
        result: dict = {"pages": done}
        if pdf:
            pdf.close()
            pdf_part.replace(pdf_path)
            result["pdf"] = {"path": str(pdf_path),
                             "url": f"/api/export/download/{pdf_path.name}"}
        if want_zip:
            # PNGs are already deflate-compressed: store them as-is
            with zipfile.ZipFile(zip_part, "w", zipfile.ZIP_STORED) as zf:
                for f in png_files:
                    zf.write(f, f.name)
            zip_part.replace(zip_path)
            result["zip"] = {"path": str(zip_path),
                             "url": f"/api/export/download/{zip_path.name}"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        for p in (pdf_part, zip_part):
            try:
                p.unlink()
            except FileNotFoundError:
                pass
    prune_exports(out_dir, keep={base_name})
    return result
