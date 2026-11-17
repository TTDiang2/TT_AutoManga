"""Font resolution for server-side page rendering.

Order: the requested family's own file in ``data/fonts/`` → the user's
``default*`` font (also what unnamed text, i.e. every bubble, uses) →
well-known system fonts (Windows / Linux / macOS, CJK first) → Pillow's
built-in scalable default. Sizes are in 1x page pixels (the renderer
multiplies by scale before calling :func:`get_font`).

A user font's family is its file name up to the first "-", lower-cased —
the same rule api/fonts.py exposes to the browser: title-bebas.ttf is family
"title", default-letter-bold.ttf is family "default".
"""
import os
from pathlib import Path
from typing import List, Optional
from PIL import ImageFont
from ..core.config import DATA_DIR

_USER_FONT_DIR = DATA_DIR / "fonts"
_FONT_SUFFIXES = (".ttf", ".otf", ".ttc")

_FALLBACKS = [
    "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/simsun.ttc",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    # macOS (PingFang is not a plain file on recent macOS; Hiragino Sans GB
    # and STHeiti are, and cover CJK + Latin)
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]

_BOLD_FALLBACKS = [
    "C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]
_cache: dict = {}
# (dir mtime, family, bold) → path: text auto-shrink calls get_font once per
# shrink step, and resolving globs the font dir every time
_find_cache: dict = {}


def font_family(name: str) -> str:
    """Family of a user font file name (title-bebas.ttf → "title")."""
    return name.split("-")[0].rsplit(".", 1)[0].lower()


def _user_fonts() -> List[Path]:
    if not _USER_FONT_DIR.exists():
        return []
    return [f for f in sorted(_USER_FONT_DIR.iterdir())
            if f.is_file() and f.suffix.lower() in _FONT_SUFFIXES]


def _pick_weight(files: List[Path], bold: bool) -> Optional[str]:
    """Prefer the file whose weight matches; any file of the family else."""
    if not files:
        return None
    for f in files:
        if ("bold" in f.stem.lower()) == bold:
            return str(f)
    return str(files[0])


def _match_user_font(family: Optional[str], bold: bool) -> Optional[str]:
    fonts = _user_fonts()
    if family:
        own = _pick_weight([f for f in fonts if font_family(f.name) == family.lower()],
                           bold)
        if own:
            return own
    # a user font named default* replaces the system fallback — for
    # unnamed text (bubbles never name a family) and for a named family
    # that has no file in data/fonts
    return _pick_weight([f for f in fonts if f.name.lower().startswith("default")],
                        bold)


def _system_font(family: Optional[str], bold: bool) -> Optional[str]:
    if family:
        for p in _FALLBACKS + _BOLD_FALLBACKS:
            base = os.path.basename(p).lower()
            if family.lower() in base and os.path.exists(p):
                if not bold or "bold" in base or "bd" in base or "hei" in base:
                    return p
    fallbacks = _BOLD_FALLBACKS + _FALLBACKS if bold else _FALLBACKS
    for p in fallbacks:
        if os.path.exists(p):
            return p
    return None


def _find_font(family: Optional[str], bold: bool = False) -> Optional[str]:
    try:
        stamp = _USER_FONT_DIR.stat().st_mtime_ns   # adding a font invalidates
    except OSError:
        stamp = None
    key = (stamp, (family or "").lower(), bool(bold))
    if key not in _find_cache:
        _find_cache[key] = _match_user_font(family, bold) or _system_font(family, bold)
    return _find_cache[key]


def get_font(size: float, family: Optional[str] = None,
             bold: bool = False) -> ImageFont.FreeTypeFont:
    """Font for page-pixel rendering; size is in 1x-scaled page pixels."""
    path = _find_font(family, bold)
    px = int(round(max(1, size)))
    key = (path, px)
    if key not in _cache:
        # Pillow's scalable built-in font as the last resort: the size-less
        # bitmap default would ignore fontSize entirely
        _cache[key] = ImageFont.truetype(path, px) if path \
            else ImageFont.load_default(size=px)
    return _cache[key]
