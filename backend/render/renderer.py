"""Server-side page renderer (Pillow), ported from the frontend composer.

Semantic parity checklist (see docs/plans/2026-10-06-agent-pipeline-design.md §6):
- coordinates are page percentages; zIndex ascending stable order;
  visible=false skipped; white RGB base
- rotation about element center, clockwise-positive (CSS convention)
- image: object-fit cover crop, cropArea override, imageScale/imageOffset,
  quadrilateral corners clip, frame border (default 1.5px panels, 0 page-image)
- page-image: alpha-composited above frames (breakout/transparent overlays)
- image-slot: empty slots render nothing (same as the old export path)
"""
from __future__ import annotations
from typing import Any, Callable, Optional, Tuple
from PIL import Image, ImageChops, ImageDraw
from . import bubbles
from .fonts import get_font

Resolver = Callable[[str], Optional[Image.Image]]

DEFAULT_CORNERS = {"tl": {"x": 0, "y": 0}, "tr": {"x": 100, "y": 0},
                   "br": {"x": 100, "y": 100}, "bl": {"x": 0, "y": 100}}


def render_page(page: dict, scale: float = 1.0,
                resolve: Optional[Resolver] = None) -> Image.Image:
    W = max(1, int(round(page.get("width", 600) * scale)))
    H = max(1, int(round(page.get("height", 900) * scale)))
    canvas = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    elements = [e for e in page.get("elements", []) if e.get("visible", True)]
    elements.sort(key=lambda e: e.get("zIndex", 0))
    for el in elements:
        layer = _render_element(el, W, H, scale, resolve)
        if layer is not None:
            canvas = Image.alpha_composite(canvas, layer)
    return canvas.convert("RGB")


def _corners_polygon(el: dict, w: int, h: int):
    c = el.get("corners") or DEFAULT_CORNERS
    pts = []
    for key in ("tl", "tr", "br", "bl"):
        p = c.get(key) or DEFAULT_CORNERS[key]
        pts.append((p.get("x", 0) / 100 * w, p.get("y", 0) / 100 * h))
    return pts


def _render_element(el, W, H, scale, resolve) -> Optional[Image.Image]:
    X = el.get("x", 0) / 100 * W
    Y = el.get("y", 0) / 100 * H
    EW = el.get("width", 0) / 100 * W
    EH = el.get("height", 0) / 100 * H
    ew, eh = int(round(EW)), int(round(EH))
    if ew <= 0 or eh <= 0:
        return None

    t = el.get("type")
    if t in ("image", "page-image"):
        local = _draw_image(el, ew, eh, scale, resolve)
        pad = 0
    elif t == "text":
        local = _draw_text(el, ew, eh, scale)
        pad = 0
    elif t == "bubble":
        result = bubbles.draw_bubble(el, ew, eh, scale)
        local, pad = result if result else (None, 0)
    else:
        return None  # image-slot renders nothing
    if local is None:
        return None

    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # Replace (not blend) the empty region with the element layer so its
    # alpha channel is preserved exactly; alpha_composite blends once later.
    layer.paste(local, (int(round(X)) - pad, int(round(Y)) - pad))
    rot = el.get("rotation") or 0
    if rot:
        # CSS rotate() is clockwise; PIL rotates counter-clockwise.
        layer = layer.rotate(-float(rot), center=(X + EW / 2, Y + EH / 2),
                             resample=Image.BICUBIC, expand=False)
    return layer


def _draw_image(el, ew, eh, scale, resolve):
    src = el.get("src")
    if not src or resolve is None:
        return None
    img = resolve(src)
    if img is None:
        return None
    img = img.convert("RGBA")
    iw, ih = img.size

    out = Image.new("RGBA", (ew, eh), (0, 0, 0, 0))

    # --- source rect: object-fit cover (pageRenderer.ts) ---
    slot_aspect, img_aspect = ew / eh, iw / ih
    if img_aspect > slot_aspect:
        sh = ih; sw = ih * slot_aspect; sx = (iw - sw) / 2; sy = 0.0
    else:
        sw = iw; sh = iw / slot_aspect; sx = 0.0; sy = (ih - sh) / 2
    ca = el.get("cropArea")
    if ca:
        sx = ca.get("x", 0) * iw; sy = ca.get("y", 0) * ih
        sw = ca.get("width", 1) * iw; sh = ca.get("height", 1) * ih

    s = el.get("imageScale") or 1
    draw_w, draw_h = ew * s, eh * s
    dx = (ew - draw_w) / 2 + (el.get("imageOffsetX") or 0) / 100 * ew
    dy = (eh - draw_h) / 2 + (el.get("imageOffsetY") or 0) / 100 * eh

    crop = img.crop((int(sx), int(sy), max(1, int(sx + sw)), max(1, int(sy + sh))))
    crop = crop.resize((max(1, int(round(draw_w))), max(1, int(round(draw_h)))),
                       Image.LANCZOS)
    out.alpha_composite(crop, (int(round(dx)), int(round(dy))))

    # --- quadrilateral clip ---
    poly = [(int(px), int(py)) for px, py in _corners_polygon(el, ew, eh)]
    mask = Image.new("L", (ew, eh), 0)
    ImageDraw.Draw(mask).polygon(poly, fill=255)
    out.putalpha(ImageChops.multiply(out.getchannel("A"), mask))

    # --- frame border (Canvas.tsx defaults: panels 1.5, page-image 0) ---
    default_bw = 1.5 if el.get("type") == "image" else 0.0
    bw = el.get("frameBorderWidth")
    bw = default_bw if bw is None else float(bw)
    if bw > 0:
        w_px = max(1, int(round(bw * scale)))
        d = ImageDraw.Draw(out)
        d.line(poly + [poly[0]], fill=(0, 0, 0, 255), width=w_px, joint="curve")
        r = w_px / 2
        for px, py in poly + [poly[0]]:
            d.ellipse((px - r, py - r, px + r, py + r), fill=(0, 0, 0, 255))
    return out


def _draw_text(el, ew, eh, scale):
    out = Image.new("RGBA", (ew, eh), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    color = _hex(el.get("color") or "#000000")
    content = el.get("content") or ""
    vertical = el.get("direction") == "vertical"
    stroke = {}
    sw = float(el.get("strokeWidth") or 0)
    if sw > 0:
        stroke = {"stroke_width": max(1, int(round(sw * scale))),
                  "stroke_fill": _hex(el.get("strokeColor") or "#000000")}

    # auto-shrink: never let a text element overflow its box. The stroke
    # halo (sw*scale px total, sw/2 per side) eats into the usable box.
    fs_req = (el.get("fontSize") or 14) * scale
    stroke_px = max(1, int(round(sw * scale))) if sw > 0 else 0
    box_w, box_h = ew - stroke_px, eh - stroke_px
    fs = fs_req
    while fs > fs_req * 0.55 and fs > 6:
        font = get_font(fs, el.get("fontFamily"),
                        bold=(el.get("fontWeight") or "").lower() == "bold")
        if vertical:
            # measure the REAL balanced-column block, not a one-column model —
            # when the 55% floor is hit the drawn block can span several columns
            from .vtext import layout_vertical
            _, exts = layout_vertical(content, ew, eh, 0.0, fs, font)
            if not exts:
                break
            needed_w = max(x1 for _, x1, _, _ in exts) - min(x0 for x0, _, _, _ in exts)
            needed_h = max(y1 for *_, y1 in exts) - min(y0 for *_, y0, _ in exts)
        else:
            lines = content.split("\n")
            needed_w = max((font.getlength(l) for l in lines), default=0)
            needed_h = len(lines) * fs * 1.4
        if needed_w <= box_w and needed_h <= box_h:
            break
        fs = max(6.0, fs * 0.9)
    font = get_font(fs, el.get("fontFamily"),
                    bold=(el.get("fontWeight") or "").lower() == "bold")

    line_h = fs * 1.4
    if vertical:
        from .vtext import layout_vertical
        positions, _ = layout_vertical(content, ew, eh, 0.0, fs, font)
        for ch, x, y in positions:
            d.text((x, y), ch, font=font, fill=color, anchor="mm", **stroke)
    else:
        lines = content.split("\n")
        total = len(lines) * line_h
        y0 = (eh - total) / 2
        align = el.get("textAlign") or "left"
        ax = {"left": "lm", "center": "mm", "right": "rm"}[align]
        x = {"left": 0, "center": ew / 2, "right": ew}[align]
        for i, line in enumerate(lines):
            d.text((x, y0 + i * line_h + line_h / 2), line, font=font,
                   fill=color, anchor=ax, **stroke)
    return out


def _hex(s: str) -> Tuple[int, int, int, int]:
    s = (s or "").lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    try:
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4)) + (255,)
    except Exception:
        return (0, 0, 0, 255)
