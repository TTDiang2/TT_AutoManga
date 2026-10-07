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

_BOLD_FALLBACKS = [
    "C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
_cache: dict = {}


def _match_user_font(family: Optional[str], bold: bool) -> Optional[str]:
    if not _USER_FONT_DIR.exists():
        return None
    candidates = sorted(_USER_FONT_DIR.glob("*"))
    if family:
        for f in candidates:
            if f.suffix.lower() in (".ttf", ".otf", ".ttc") \
                    and family.lower() in f.stem.lower():
                if not bold or "bold" in f.stem.lower():
                    return str(f)
    if bold:
        for f in candidates:
            if f.suffix.lower() in (".ttf", ".otf", ".ttc") \
                    and "bold" in f.stem.lower():
                return str(f)
    if family:
        for f in candidates:
            if f.suffix.lower() in (".ttf", ".otf", ".ttc") \
                    and family.lower() in f.stem.lower():
                return str(f)
    return None


def _find_font(family: Optional[str], bold: bool = False) -> Optional[str]:
    user = _match_user_font(family, bold)
    if user:
        return user
    if family:
        for p in _FALLBACKS:
            if family.lower() in os.path.basename(p).lower() and os.path.exists(p):
                if not bold or "bold" in os.path.basename(p).lower() or "hei" in p:
                    return p
    fallbacks = _BOLD_FALLBACKS + _FALLBACKS if bold else _FALLBACKS
    for p in fallbacks:
        if os.path.exists(p):
            return p
    return None


def get_font(size: float, family: Optional[str] = None,
             bold: bool = False) -> ImageFont.FreeTypeFont:
    """Font for page-pixel rendering; size is in 1x-scaled page pixels."""
    path = _find_font(family, bold)
    key = (path, round(size))
    if key not in _cache:
        _cache[key] = ImageFont.truetype(path, int(round(max(1, size)))) if path \
            else ImageFont.load_default()
    return _cache[key]
