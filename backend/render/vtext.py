"""Native CJK vertical typesetting.

Single source of truth for vertical text layout, shared by the bubble
renderer (bubbles.py), the text-element renderer (renderer.py) and the
frontend port (pageRenderer.ts must mirror these constants).

Design (replacing the old "horizontal text force-wrapped into columns"):
- tight manga metrics — glyph advance inside a column is 1.06 × fontSize,
  column advance is 1.14 × fontSize (was 1.3 × both);
- columns are BALANCED: with n glyphs over c columns, column lengths differ
  by at most one, so no 1-2 glyph orphan columns;
- punctuation and brackets map to Unicode vertical presentation forms
  (U+FE10 block: ，→︐ 。→︒ ！→︕ ？→︖ ——→︱︱ …→︙ 「」→﹁﹂ …) when the
  resolved font carries those glyphs (msyh, simsun, Noto CJK, PingFang do).
"""
import math
from typing import List, Optional, Tuple

CHAR_ADV = 1.06   # glyph advance within a column, × fontSize
COL_ADV = 1.14    # column-to-column advance, × fontSize

# horizontal codepoint -> vertical presentation form
VERTICAL_MAP = str.maketrans({
    "，": "︐", "。": "︒", "：": "︓", "；": "︔",
    "！": "︕", "？": "︖", "（": "︵", "）": "︶",
    "【": "︻", "】": "︼", "《": "︽", "》": "︾",
    "「": "﹁", "」": "﹂", "『": "﹃", "』": "﹄",
    "…": "︙", "‥": "︰", "—": "︱", "－": "︱", "ー": "︱",
})

_cmap_cache: dict = {}


def _cmap_has(font, codepoints) -> bool:
    """True when the resolved font file covers every codepoint (fontTools,
    guarded — falls back to True since all shipped CJK fonts carry the
    presentation forms). ``codepoints`` are ints. Note: TTFont fontNumber=0
    matches ImageFont.truetype()'s default face selection for .ttc files —
    keep the two in sync if fonts.py ever picks a face index."""
    path = getattr(font, "path", None)
    if not path:
        return True
    if path not in _cmap_cache:
        try:
            from fontTools.ttLib import TTFont
            with TTFont(path, fontNumber=0, lazy=True) as tt:
                _cmap_cache[path] = tt.getBestCmap()
        except Exception:
            _cmap_cache[path] = True   # assume coverage rather than tofu
    cmap = _cmap_cache[path]
    if cmap is True:
        return True
    return all(cp in cmap for cp in codepoints)


def to_vertical_punctuation(text: str, font=None) -> str:
    """Map horizontal punctuation to vertical presentation forms when the
    font supports them; otherwise return text unchanged (old behaviour).

    Parity note: the frontend canvas maps unconditionally (browsers do
    per-glyph fallback, so no tofu there) — for fonts lacking the forms
    (e.g. simhei.ttf) server render and UI preview can differ per glyph."""
    if not text:
        return text
    codepoints = {ord(c) for c in VERTICAL_MAP.values()}
    if font is not None and not _cmap_has(font, codepoints):
        return text
    return text.translate(VERTICAL_MAP)


def layout_vertical(text: str, ew: float, eh: float, pad_px: float,
                    fs: float, font=None
                    ) -> Tuple[List[Tuple[str, float, float]],
                               List[Tuple[float, float, float, float]]]:
    """Lay glyphs out in tight right-to-left columns.

    Returns (positions, extents): positions are ``(ch, cx, cy)`` center
    anchors for draw.text(anchor="mm"); extents are per-column
    ``(x0, x1, y0, y1)`` boxes for the shape-fit check.
    """
    chars = [c for c in to_vertical_punctuation(text, font) if c != "\n"]
    if not chars:
        return [], []
    char_h = fs * CHAR_ADV
    col_w = fs * COL_ADV
    capacity = max(1, int((eh - 2 * pad_px) // char_h))
    total_cols = max(1, math.ceil(len(chars) / capacity))
    per, rem = divmod(len(chars), total_cols)
    # block centered horizontally; columns read right-to-left, the first
    # (rightmost) columns take the remainder so the LAST column is shortest
    first_cx = ew / 2 + (total_cols * col_w) / 2 - col_w / 2
    positions: List[Tuple[str, float, float]] = []
    extents: List[Tuple[float, float, float, float]] = []
    idx = 0
    for c in range(total_cols):
        count = per + (1 if c < rem else 0)
        col = chars[idx:idx + count]
        idx += count
        x = first_cx - c * col_w
        col_h = len(col) * char_h
        y0 = (eh - col_h) / 2
        for i, ch in enumerate(col):
            positions.append((ch, x, y0 + i * char_h + char_h / 2))
        extents.append((x - col_w / 2, x + col_w / 2, y0, y0 + col_h))
    return positions, extents
