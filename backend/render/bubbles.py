"""Bubble rendering, ported from frontend/src/components/composer/pageRenderer.ts.

Parity notes (verified against pageRenderer.ts and the live editor's CSS):
- speech/inner-voice: solid-stroke ellipse; thought: dashed (5,5) width 2;
  whisper: dashed width 1.
- shout: 12-spike star, inner radius 0.78x outer, stroke width 3.
- narration: rounded rect (radius 4), no tail.
- tail 'bottom' renders a triangle ABOVE the top edge pointing up; 'top'
  renders BELOW the bottom edge pointing down (same quirk in pageRenderer.ts
  and the live editor's .composer-bubble-tail CSS). 'left'/'right' draw nothing.
- italic styles (thought/whisper/narration/inner-voice) fall back to regular
  on the server; no italic CJK font is guaranteed to exist.
- optional fields (absent = the behaviour above, pixel for pixel):
  ``tailTip {x, y}`` (fractions of the unrotated box, may lie outside it)
  draws a pointed tail at that point instead of ``tailPosition`` (geometry
  in tails.py, mirrored by the frontend); ``textAlign`` left/right/center;
  ``markup: "stars"`` sets ``*x*`` as emphasis (default bold font, sheared
  EM_SHEAR — a synthetic italic; horizontal text only).
- text is drawn run by run through a font chain (fonts.get_font_chain), so
  glyphs the lettering font lacks (♪, CJK in a Latin font) come from the
  first fallback font that has them, on the primary font's baseline.
"""
import math
import re
from typing import List, NamedTuple, Optional, Tuple
from PIL import Image, ImageDraw, ImageFilter
from .fonts import FontChain, get_font_chain
from .tails import tail_bounds, tail_geometry, wedge_edge

EM_SHEAR = 0.2
TIP_LIMIT = 2.0     # tailTip fractions are clamped to at most this many box sizes beyond the box
TIP_MIN, TIP_MAX = -TIP_LIMIT, 1 + TIP_LIMIT     # the valid tailTip range (also the API's)
MAX_LOCAL_PIXELS = 16_000_000   # cap of one bubble's local image (body + tail margins)


class Pad(NamedTuple):
    """Margins of a bubble image around its body: paste at (x - left, y - top)."""
    left: int
    top: int
    right: int = 0
    bottom: int = 0


def clamp_tail_tip(tip):
    """A tailTip clamped into [TIP_MIN, TIP_MAX]; None when it is not a
    finite {x, y} (renderers ignore it then)."""
    if not isinstance(tip, dict):
        return None
    try:
        fx, fy = float(tip.get("x")), float(tip.get("y"))
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(fx) and math.isfinite(fy)):
        return None
    return {"x": max(TIP_MIN, min(TIP_MAX, fx)), "y": max(TIP_MIN, min(TIP_MAX, fy))}


def sanitize_pages(pages) -> None:
    """In place: clamp every bubble's tailTip into range and drop invalid
    ones (elements saved by the UI or older clients)."""
    for page in pages or []:
        if not isinstance(page, dict):
            continue
        for el in page.get("elements") or []:
            if isinstance(el, dict) and el.get("tailTip") is not None:
                tip = clamp_tail_tip(el["tailTip"])
                if tip is None:
                    el.pop("tailTip", None)
                else:
                    el["tailTip"] = tip
_STARS = re.compile(r"\*([^*\n]+)\*")


def _hex(s: str, fallback) -> Tuple[int, int, int, int]:
    try:
        s = (s or "").lstrip("#")
        if len(s) == 3:
            s = "".join(c * 2 for c in s)
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4)) + (255,)
    except Exception:
        return fallback


def dashed_ellipse(draw, box, dash, gap, width, fill):
    x0, y0, x1, y1 = box
    rx, ry = (x1 - x0) / 2, (y1 - y0) / 2
    if rx <= 0 or ry <= 0:
        return
    circ = math.pi * (3 * (rx + ry) - math.sqrt((3 * rx + ry) * (rx + 3 * ry)))
    on = max(0.5, 360.0 * dash / circ) if circ else 360.0
    off = max(0.5, 360.0 * gap / circ) if circ else 0.0
    a = 0.0
    while a < 360:
        draw.arc(box, start=a, end=min(a + on, 360), fill=fill, width=width)
        a += on + off


def parse_stars(text: str):
    """``*x*`` → (plain text, per-character emphasis flags). A star without a
    partner on the same line stays literal."""
    plain: List[str] = []
    em: List[bool] = []
    i = 0
    for m in _STARS.finditer(text):
        plain.append(text[i:m.start()])
        em.extend([False] * (m.start() - i))
        plain.append(m.group(1))
        em.extend([True] * len(m.group(1)))
        i = m.end()
    plain.append(text[i:])
    em.extend([False] * (len(text) - i))
    return "".join(plain), em


class Styled:
    """Measures and draws lines of ``(char, emphasis)`` cells: regular cells
    through ``chain``, emphasis cells through ``em_chain``, each character
    in the first font of its chain that covers it."""

    def __init__(self, chain, em_chain=None):
        self.chain = chain
        self.em_chain = em_chain or chain
        self.primary = getattr(chain, "primary", chain)

    def _font(self, ch: str, em: bool):
        c = self.em_chain if em else self.chain
        pick = getattr(c, "font_for", None)
        return pick(ch) if pick else c

    def segments(self, cells):
        segs: list = []
        for ch, em in cells:
            f = self._font(ch, em)
            if segs and segs[-1][1] is f and segs[-1][2] == em:
                segs[-1][0].append(ch)
            else:
                segs.append(([ch], f, em))
        return [("".join(c), f, em) for c, f, em in segs]

    def getlength(self, cells) -> float:
        return sum(f.getlength(t) for t, f, _ in self.segments(cells))


def _cells(text: str, em: Optional[List[bool]] = None):
    return list(zip(text, em or [False] * len(text)))


def _wrap_text(font, text, max_width: float, em: Optional[List[bool]] = None):
    """Char-by-char wrapping, mirroring pageRenderer.ts wrapText().

    ``font`` is a font, a FontChain or a :class:`Styled`; ``text`` a string
    (returns strings, as before) or, with ``em`` flags, returns cell lists."""
    styled = font if isinstance(font, Styled) else Styled(font)
    as_cells = em is not None
    result = []
    line: list = []
    for cell in _cells(text, em):
        if cell[0] == "\n":
            result.append(line)
            line = []
            continue
        test = line + [cell]
        if line and styled.getlength(test) > max_width:
            result.append(line)
            line = [cell]
        else:
            line = test
    result.append(line)
    if as_cells:
        return result
    return ["".join(ch for ch, _ in ln) for ln in result]


def draw_cells(layer: Image.Image, x: float, y: float, cells, styled: Styled,
               anchor: str, fill, **stroke) -> None:
    """Draw one line of cells with its horizontal ``anchor`` ("l"/"m"/"r")
    at x and its vertical middle (PIL's "m") at y. A line in one plain run
    is a single draw.text call — identical to the pre-fallback renderer."""
    d = ImageDraw.Draw(layer)
    segs = styled.segments(cells)
    if not segs:
        return
    if len(segs) == 1 and not segs[0][2]:
        d.text((x, y), segs[0][0], font=segs[0][1], fill=fill,
               anchor=anchor + "m", **stroke)
        return
    total = sum(f.getlength(t) for t, f, _ in segs)
    cx = x - {"l": 0.0, "m": total / 2, "r": total}[anchor]
    asc, desc = styled.primary.getmetrics()
    base = y + (asc - desc) / 2       # shared baseline for every run
    for t, f, em in segs:
        if em:
            _draw_sheared(layer, cx, base, t, f, fill, stroke)
        else:
            d.text((cx, base), t, font=f, fill=fill, anchor="ls", **stroke)
        cx += f.getlength(t)


def _draw_sheared(layer: Image.Image, x: float, base: float, text: str, font,
                  fill, stroke: dict) -> None:
    """Synthetic italic: draw upright on a scratch layer, shear about the
    baseline (EM_SHEAR px right per px of height), composite."""
    asc, desc = font.getmetrics()
    m = 2 + int(stroke.get("stroke_width", 0))
    w = int(math.ceil(font.getlength(text) + EM_SHEAR * (asc + m) + 2 * m))
    h = asc + desc + 2 * m
    tmp = Image.new("RGBA", (max(1, w), max(1, h)), (0, 0, 0, 0))
    b = m + asc
    ImageDraw.Draw(tmp).text((m, b), text, font=font, fill=fill, anchor="ls", **stroke)
    tmp = tmp.transform(tmp.size, Image.AFFINE,
                        (1, EM_SHEAR, -EM_SHEAR * b, 0, 1, 0),
                        resample=Image.BICUBIC)
    ox, oy = int(round(x)) - m, int(round(base)) - b
    _paste(layer, tmp, ox, oy)


def _paste(dst: Image.Image, src: Image.Image, x: int, y: int) -> None:
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(dst.width, x + src.width), min(dst.height, y + src.height)
    if x1 <= x0 or y1 <= y0:
        return
    dst.alpha_composite(src.crop((x0 - x, y0 - y, x1 - x, y1 - y)), (x0, y0))


def _tip_px(el: dict, ew: int, eh: int) -> Optional[Tuple[float, float]]:
    tip = clamp_tail_tip(el.get("tailTip"))
    if tip is None:
        return None
    return tip["x"] * ew, tip["y"] * eh


def _cap_pads(ew: int, eh: int, pads: List[int]) -> List[int]:
    """Shrink the margins (never the body) until the image fits
    MAX_LOCAL_PIXELS; a tail cut off this way lies far off the bubble."""
    def area(p):
        return (ew + p[0] + p[2]) * (eh + p[1] + p[3])
    if area(pads) <= MAX_LOCAL_PIXELS:
        return pads
    lo, hi = 0.0, 1.0
    for _ in range(20):
        mid = (lo + hi) / 2
        if area([int(v * mid) for v in pads]) <= MAX_LOCAL_PIXELS:
            lo = mid
        else:
            hi = mid
    return [int(v * lo) for v in pads]


def draw_bubble(el: dict, ew: int, eh: int, scale: float) -> Optional[Tuple[Image.Image, Pad]]:
    """Render one bubble in element-local pixels.

    Returns ``(img, pad)`` where ``img`` is an RGBA image of size
    ``(pad.left + ew + pad.right, pad.top + eh + pad.bottom)`` with the
    bubble body at ``(pad.left, pad.top)`` — the margins absorb tails that
    stick out of the bounding box (each side only as much as it needs).
    The caller pastes at ``(x - pad.left, y - pad.top)``. None for a bubble
    too small to draw (under 1 px inside its outline).

    Text is auto-shrunk until it fits the bubble box and is clipped to the
    bubble shape, so long dialogue can never spill outside the balloon.
    """
    k = scale
    bt = el.get("bubbleType", "speech")
    bg = _hex(el.get("backgroundColor"), None)
    border = _hex(el.get("borderColor"), (0, 0, 0, 255))
    defaults = {
        "shout": (255, 249, 196, 255),
        "narration": (245, 245, 245, 255),
    }
    if bg is None:
        bg = defaults.get(bt, (255, 255, 255, 255))

    # ew/eh are already scale-multiplied page pixels, so the tail ratio
    # (12% of the bubble) must NOT be multiplied by scale again.
    tail_size = min(ew, eh) * 0.12
    pad = int(math.ceil(tail_size * 1.2)) + 2 if bt != "narration" else 2
    inset = max(1, round(2 * k))
    if ew - 2 * inset < 1 or eh - 2 * inset < 1:
        return None
    # tail outline width = the body's (shout 3, whisper 1, others 2)
    stroke_w = max(1, round({"shout": 3, "whisper": 1}.get(bt, 2) * k))

    # pointed tail: grow each side's margin until the tip (plus stroke) fits
    pads = [pad] * 4                      # left, top, right, bottom
    tail = None
    tip = _tip_px(el, ew, eh)
    if tip is not None:
        tail = tail_geometry(bt, ew, eh, tip, inset)
    if tail is not None:
        x0, y0, x1, y1 = tail_bounds(tail)
        for i, over in enumerate((-x0, -y0, x1 - ew, y1 - eh)):
            if over > 0:
                pads[i] = max(pads[i], int(math.ceil(over)) + stroke_w + 2)
        pads = _cap_pads(ew, eh, pads)
    pl, pt, pr, pb = pads

    img = Image.new("RGBA", (pl + ew + pr, pt + eh + pb), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    box = (pl + inset, pt + inset, pl + ew - inset, pt + eh - inset)
    cx = pl + ew / 2
    top = pt
    bottom = pt + eh

    shape_mask = Image.new("L", img.size, 0)
    md = ImageDraw.Draw(shape_mask)

    if bt == "shout":
        spikes = 12
        outer_rx, outer_ry = (box[2] - box[0]) / 2, (box[3] - box[1]) / 2
        inner_rx, inner_ry = outer_rx * 0.78, outer_ry * 0.78
        cx_b, cy_b = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        pts = []
        for i in range(spikes * 2):
            angle = (math.pi * 2 * i) / (spikes * 2) - math.pi / 2
            rx = outer_rx if i % 2 == 0 else inner_rx
            ry = outer_ry if i % 2 == 0 else inner_ry
            pts.append((cx_b + rx * math.cos(angle), cy_b + ry * math.sin(angle)))
        d.polygon(pts, fill=bg, outline=border)
        # PIL polygon outline width is 1; stroke with lines for width 3.
        _stroke_polyline(d, pts + [pts[0]], border, max(1, round(3 * k)))
        md.polygon(pts, fill=255)
    elif bt == "narration":
        d.rounded_rectangle(box, radius=max(1, round(4 * k)), fill=bg,
                            outline=border, width=max(1, round(2 * k)))
        md.rounded_rectangle(box, radius=max(1, round(4 * k)), fill=255)
    else:
        d.ellipse(box, fill=bg)
        if bt in ("thought", "whisper"):
            width = 1 if bt == "whisper" else 2
            dashed_ellipse(d, box, 5 * k, 5 * k, max(1, round(width * k)), border)
        else:
            d.ellipse(box, outline=border, width=max(1, round(2 * k)))
        md.ellipse(box, fill=255)

    if tail is not None:
        _draw_pointed_tail(img, tail, (pl, pt), bg, border, stroke_w, shape_mask)
    # Tail (pageRenderer parity: 'bottom' = above top edge, 'top' = below bottom).
    elif bt != "narration" and el.get("tailPosition") in ("bottom", "top"):
        t = tail_size
        stroke_w = max(1, round(2 * k))
        if el["tailPosition"] == "bottom":
            pts = [(cx - t, top), (cx, top - t * 1.2), (cx + t, top)]
        else:
            pts = [(cx - t, bottom), (cx, bottom + t * 1.2), (cx + t, bottom)]
        d.polygon(pts, fill=bg)
        _stroke_polyline(d, pts + [pts[0]], border, stroke_w)

    _draw_bubble_text(d, el, ew, eh, (pl, pt), k, img, shape_mask)
    return img, Pad(pl, pt, pr, pb)


def _draw_pointed_tail(img: Image.Image, tail: dict, pad: Tuple[int, int], bg, border,
                       stroke_w: int, shape_mask: Image.Image) -> None:
    """Draw a tailTip tail over the already-drawn body with a seamless root:
    the tail fill covers the body's outline between the two root points,
    then the two tail edges are stroked — only outside the body's interior,
    so they meet the body outline without stubs inside the balloon."""
    d = ImageDraw.Draw(img)
    ox, oy = pad
    if tail["kind"] == "circles":
        for x, y, r in tail["circles"]:
            box = (ox + x - r, oy + y - r, ox + x + r, oy + y + r)
            d.ellipse(box, fill=bg, outline=border, width=stroke_w)
        return
    edge = [(ox + x, oy + y) for x, y in wedge_edge(tail)]
    d.polygon(edge, fill=bg)
    lines = Image.new("RGBA", img.size, (0, 0, 0, 0))
    _stroke_polyline(ImageDraw.Draw(lines), edge, border, stroke_w)
    size = 2 * stroke_w + 1
    interior = shape_mask.filter(ImageFilter.MinFilter(size))
    outside = interior.point(lambda v: 255 - v)
    lines.putalpha(Image.composite(lines.getchannel("A"),
                                   Image.new("L", img.size, 0), outside))
    img.alpha_composite(lines)


def _stroke_polyline(d: ImageDraw.ImageDraw, pts, fill, width):
    if width <= 1:
        d.line(pts, fill=fill, width=1, joint="curve")
        return
    d.line(pts, fill=fill, width=width, joint="curve")
    # round the joints/ends
    r = width / 2
    for px, py in pts:
        d.ellipse((px - r, py - r, px + r, py + r), fill=fill)


def _text_layout(text: str, ew: int, eh: int, pad_px: float,
                 font, fs: float, vertical: bool, align: str = "center",
                 em: Optional[List[bool]] = None, box_align: bool = False):
    """Single source of truth for text layout, used by BOTH the fit check and
    the actual drawing (they must never diverge).

    ``font`` is a font, FontChain or :class:`Styled`; ``em`` per-character
    emphasis flags of ``text`` (markup already stripped). ``align`` left /
    right aligns the lines to the edge of the centred text block — or, with
    ``box_align`` (narration boxes), to the padded box edge.

    Returns (positions, extents): ``(content, x, y, anchor)`` for
    :func:`draw_cells` (content is a cell list; for vertical text a single
    char, anchor "m") plus per-line/column bounding boxes (x0, x1, y0, y1)
    for the shape-fit check."""
    if vertical:
        from .vtext import layout_vertical
        chain = font.chain if isinstance(font, Styled) else font
        pos, ext = layout_vertical(text, ew, eh, pad_px, fs, chain)
        return [([(ch, False)], x, y, "m") for ch, x, y in pos], ext

    styled = font if isinstance(font, Styled) else Styled(font)
    max_w = ew - 2 * pad_px
    lines = _wrap_text(styled, text, max_w, em or [False] * len(text))
    line_h = fs * 1.4
    total_h = len(lines) * line_h
    y0 = (eh - total_h) / 2
    widths = [styled.getlength(line) for line in lines]
    block = max(widths, default=0.0)
    if align == "left":
        left = pad_px if box_align else ew / 2 - block / 2
    elif align == "right":
        right = ew - pad_px if box_align else ew / 2 + block / 2
    positions, extents = [], []
    for i, line in enumerate(lines):
        yc = y0 + i * line_h + line_h / 2
        w = widths[i]
        if align == "left":
            positions.append((line, left, yc, "l"))
            extents.append((left, left + w, yc - line_h / 2, yc + line_h / 2))
        elif align == "right":
            positions.append((line, right, yc, "r"))
            extents.append((right - w, right, yc - line_h / 2, yc + line_h / 2))
        else:
            positions.append((line, ew / 2, yc, "m"))
            extents.append((ew / 2 - w / 2, ew / 2 + w / 2, yc - line_h / 2, yc + line_h / 2))
    return positions, extents


def _bubble_text(el: dict):
    """(plain text, emphasis flags or None, align) of a bubble."""
    text = el.get("text") or ""
    em = None
    if el.get("markup") == "stars":
        text, em = parse_stars(text)
    align = el.get("textAlign")
    if align not in ("left", "right"):
        align = "center"
    return text, em, align


def _styled(fs: float, bold: bool) -> Styled:
    """Regular + emphasis chains at one size (emphasis: the bold font)."""
    chain = get_font_chain(fs, None, bold=bold)
    return Styled(chain, get_font_chain(float(chain.size), None, bold=True))


def _extents_fit_shape(extents, bt: str, ew: int, eh: int, inset: float) -> bool:
    """True when every text extent lies inside the bubble's real shape.

    Ellipse: farthest corner of each extent must satisfy the ellipse
    inequality. Shout: same against the inner (0.78) star ellipse —
    conservative. Narration: plain inset rectangle."""
    rx, ry = (ew - 2 * inset) / 2, (eh - 2 * inset) / 2
    if rx <= 0 or ry <= 0:
        return False
    cx, cy = ew / 2, eh / 2
    k = 0.78 if bt == "shout" else 1.0
    for x0, x1, y0, y1 in extents:
        if bt == "narration":
            if x0 < inset or x1 > ew - inset or y0 < inset or y1 > eh - inset:
                return False
            continue
        dx = max(abs(x0 - cx), abs(x1 - cx)) / (rx * k)
        dy = max(abs(y0 - cy), abs(y1 - cy)) / (ry * k)
        if dx * dx + dy * dy > 1.0:
            return False
    return True


def _fit_font_size(el: dict, ew: int, eh: int, pad_px: float,
                   bold: bool, k: float) -> FontChain:
    """Shrink the font until the REAL drawn layout fits the REAL bubble shape
    (same layout function as drawing), floor at 55% of the requested size.

    Lettering floor: a vertical layout whose shortest column carries fewer
    than 5 glyphs reads badly (the production-review bar), so keep shrinking
    while a larger capacity would still balance into fewer columns — unless
    the line is shorter than 5 glyphs or the floor is hit."""
    bt = el.get("bubbleType", "speech")
    fs_req = (el.get("fontSize") or 12) * k
    text, em, align = _bubble_text(el)
    vertical = el.get("direction") == "vertical"
    inset = max(1, round(2 * k))
    fs = fs_req
    while True:
        styled = _styled(fs, bold)
        # lay out with the size the font actually resolved to (get_font
        # int-rounds) so fit-check and draw see identical metrics
        _, extents = _text_layout(text, ew, eh, pad_px, styled,
                                  float(styled.chain.size), vertical, align, em,
                                  box_align=bt == "narration")
        fits = _extents_fit_shape(extents, bt, ew, eh, inset)
        at_floor = fs <= fs_req * 0.55 or fs <= 6
        min_col_ok = True
        if vertical and not at_floor:
            n = len([c for c in text if c != "\n"])
            if n >= 5:
                cols = max(1, len(extents))
                min_col_ok = n // cols >= 5
        if (fits and min_col_ok) or at_floor:
            return styled.chain
        # whole pixels (get_font rounds anyway), always at least 1 px smaller:
        # a handful of distinct sizes per bubble, not a cache key per float
        fs = float(max(6, min(int(round(fs * 0.9)), int(round(fs)) - 1)))


def _draw_bubble_text(d: ImageDraw.ImageDraw, el: dict, ew: int, eh: int,
                      pad: Tuple[int, int], k: float, img: Image.Image,
                      shape_mask: Image.Image):
    bt = el.get("bubbleType", "speech")
    # pageRenderer.ts: only shout renders bold.
    bold = bt == "shout"
    chain = _fit_font_size(el, ew, eh, 10 * k, bold, k)
    text, em, align = _bubble_text(el)
    color = (0, 0, 0, 178) if bt == "whisper" else (0, 0, 0, 255)
    pad_px = 10 * k
    fs = float(chain.size)
    styled = _styled(fs, bold)

    # draw text on its own layer, clipped to the bubble shape; the layout is
    # the same function the fit check used, so nothing gets clipped that the
    # fit check didn't already account for
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    positions, _ = _text_layout(text, ew, eh, pad_px, styled, fs,
                                el.get("direction") == "vertical", align, em,
                                box_align=bt == "narration")
    for cells, x, y, anchor in positions:
        draw_cells(layer, pad[0] + x, pad[1] + y, cells, styled, anchor, color)

    clipped = Image.composite(layer, Image.new("RGBA", img.size, (0, 0, 0, 0)),
                              shape_mask)
    img.alpha_composite(clipped)
