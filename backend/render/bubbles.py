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
"""
import math
from typing import Tuple
from PIL import Image, ImageDraw
from .fonts import get_font


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


def _wrap_text(font, text: str, max_width: float):
    """Char-by-char wrapping, mirroring pageRenderer.ts wrapText()."""
    result = []
    for raw in text.split("\n"):
        if not raw:
            result.append("")
            continue
        line = ""
        for ch in raw:
            test = line + ch
            if font.getlength(test) > max_width and line:
                result.append(line)
                line = ch
            else:
                line = test
        if line:
            result.append(line)
    return result


def draw_bubble(el: dict, ew: int, eh: int, scale: float) -> Tuple[Image.Image, int]:
    """Render one bubble in element-local pixels.

    Returns ``(img, pad)`` where ``img`` is an RGBA image of size
    ``(ew + 2*pad, eh + 2*pad)`` with the bubble body at offset ``pad`` —
    the extra margin absorbs tails that stick out of the bounding box.
    The caller pastes at ``(x - pad, y - pad)``.
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

    tail_size = min(ew, eh) * 0.12 * k
    pad = int(math.ceil(tail_size * 1.2)) + 2 if bt != "narration" else 2

    img = Image.new("RGBA", (ew + 2 * pad, eh + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    box = (pad + 2, pad + 2, pad + ew - 2, pad + eh - 2)
    cx = pad + ew / 2
    top = pad
    bottom = pad + eh

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
    elif bt == "narration":
        d.rounded_rectangle(
            (pad + 2, pad + 2, pad + ew - 2, pad + eh - 2),
            radius=max(1, round(4 * k)), fill=bg, outline=border,
            width=max(1, round(2 * k)))
    else:
        d.ellipse(box, fill=bg)
        if bt in ("thought", "whisper"):
            width = 1 if bt == "whisper" else 2
            dashed_ellipse(d, box, 5 * k, 5 * k, max(1, round(width * k)), border)
        else:
            d.ellipse(box, outline=border, width=max(1, round(2 * k)))

    # Tail (pageRenderer parity: 'bottom' = above top edge, 'top' = below bottom).
    if bt != "narration" and el.get("tailPosition") in ("bottom", "top"):
        t = tail_size
        stroke_w = max(1, round(2 * k))
        if el["tailPosition"] == "bottom":
            pts = [(cx - t, top), (cx, top - t * 1.2), (cx + t, top)]
        else:
            pts = [(cx - t, bottom), (cx, bottom + t * 1.2), (cx + t, bottom)]
        d.polygon(pts, fill=bg)
        _stroke_polyline(d, pts + [pts[0]], border, stroke_w)

    _draw_bubble_text(d, el, ew, eh, pad, k)
    return img, pad


def _stroke_polyline(d: ImageDraw.ImageDraw, pts, fill, width):
    if width <= 1:
        d.line(pts, fill=fill, width=1, joint="curve")
        return
    d.line(pts, fill=fill, width=width, joint="curve")
    # round the joints/ends
    r = width / 2
    for px, py in pts:
        d.ellipse((px - r, py - r, px + r, py + r), fill=fill)


def _draw_bubble_text(d: ImageDraw.ImageDraw, el: dict, ew: int, eh: int,
                      pad: int, k: float):
    fs = (el.get("fontSize") or 12) * k
    font = get_font(fs, None)
    text = el.get("text") or ""
    bt = el.get("bubbleType", "speech")
    color = (0, 0, 0, 178) if bt == "whisper" else (0, 0, 0, 255)
    pad_px = 10 * k

    if el.get("direction") == "vertical":
        # Columns right-to-left, chars top-to-bottom (live editor: vertical-rl).
        char_h = fs * 1.3
        capacity = max(1, int((eh - 2 * pad_px) // char_h))
        chars = list(text)
        if not chars:
            return
        col_w = fs * 1.3
        total_cols = math.ceil(len(chars) / capacity)
        start_x = pad + ew - pad_px - fs / 2
        for c in range(total_cols):
            col_chars = chars[c * capacity:(c + 1) * capacity]
            x = start_x - c * col_w
            col_h = len(col_chars) * char_h
            y0 = pad + (eh - col_h) / 2
            for i, ch in enumerate(col_chars):
                d.text((x, y0 + i * char_h + char_h / 2), ch, font=font,
                       fill=color, anchor="mm")
        return

    max_w = ew - 2 * pad_px
    lines = _wrap_text(font, text, max_w)
    line_h = fs * 1.4
    total_h = len(lines) * line_h
    start_y = pad + eh / 2 - total_h / 2 + line_h / 2
    for i, line in enumerate(lines):
        d.text((pad + ew / 2, start_y + i * line_h), line, font=font,
               fill=color, anchor="mm")
