"""Font resolution for server-side page rendering.

Order: user-provided fonts in ``data/fonts/`` → well-known system fonts
(Windows CJK first) → Pillow default. Sizes are in 1x page pixels (the
renderer multiplies by scale before calling :func:`get_font`).
"""
import os
from pathlib import Path
from typing import Optional
from PIL import ImageFont
from ..core.config import DATA_DIR

_USER_FONT_DIR = DATA_DIR / "fonts"

_FALLBACKS = [
    "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/simsun.ttc",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/PingFang.ttc",
]
_cache: dict = {}


def _find_font(family: Optional[str]) -> Optional[str]:
    if family:
        # 1) user-provided fonts dir, match by fuzzy file name
        if _USER_FONT_DIR.exists():
            for f in sorted(_USER_FONT_DIR.glob("*")):
                if f.suffix.lower() in (".ttf", ".otf", ".ttc") \
                        and family.lower() in f.stem.lower():
                    return str(f)
        # 2) fallbacks matching family name
        for p in _FALLBACKS:
            if family.lower() in os.path.basename(p).lower() and os.path.exists(p):
                return p
    if _USER_FONT_DIR.exists():
        for f in sorted(_USER_FONT_DIR.glob("*")):
            if f.suffix.lower() in (".ttf", ".otf", ".ttc"):
                return str(f)
    for p in _FALLBACKS:
        if os.path.exists(p):
            return p
    return None


def get_font(size: float, family: Optional[str] = None) -> ImageFont.FreeTypeFont:
    """Font for page-pixel rendering; size is in 1x-scaled page pixels."""
    path = _find_font(family)
    key = (path, round(size))
    if key not in _cache:
        _cache[key] = ImageFont.truetype(path, int(round(max(1, size)))) if path \
            else ImageFont.load_default()
    return _cache[key]
