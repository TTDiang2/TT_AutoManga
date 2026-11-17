"""Font resolution for server-side page rendering.

Order: the requested family's own file in ``data/fonts/`` → the user's
``default*`` font (also what unnamed text, i.e. every bubble, uses) →
well-known system fonts (Windows / Linux / macOS, CJK first) → Pillow's
built-in scalable default.

Pillow has no glyph fallback, so text is drawn as RUNS: :func:`get_font_chain`
returns the resolved font followed by symbol fonts (♪ ♥ …) and the system
fallbacks above, and :meth:`FontChain.runs` splits a string by the first
font in the chain whose cmap covers each character (fontTools). Text the
primary font covers fully stays one run, drawn exactly as before. Sizes are in 1x page pixels (the renderer
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
# symbol fonts tried right after the requested font, before the CJK/Latin
# fallbacks: music notes, hearts, stars, arrows. Arial Unicode first: its ♪
# is cap-height, Apple Symbols' is drawn small. They are skipped for CJK
# codepoints (Arial Unicode covers CJK too), which go to the CJK fallbacks.
_SYMBOL_FALLBACKS = [
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Apple Symbols.ttf",
    "C:/Windows/Fonts/seguisym.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
_cache: dict = {}
_cmap_cache: dict = {}
_chain_cache: dict = {}
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


def _cmap(path: Optional[str]):
    """Codepoints the font file covers (face 0, the face ImageFont.truetype
    opens by default), cached; None = unknown (no path, no fontTools, an
    unreadable file) and treated as covering everything."""
    if not path:
        return None
    if path not in _cmap_cache:
        try:
            from fontTools.ttLib import TTFont
            with TTFont(path, fontNumber=0, lazy=True) as tt:
                _cmap_cache[path] = frozenset(tt.getBestCmap() or ())
        except Exception:
            _cmap_cache[path] = None
    return _cmap_cache[path]


def _is_cjk(cp: int) -> bool:
    return (0x2E80 <= cp <= 0x9FFF or 0xAC00 <= cp <= 0xD7AF
            or 0xF900 <= cp <= 0xFAFF or 0xFE10 <= cp <= 0xFE4F
            or 0xFF00 <= cp <= 0xFFEF or cp >= 0x20000)


class FontChain:
    """The resolved font plus per-glyph fallbacks, all at the same pixel size.

    ``primary`` is what :func:`get_font` returns for the same arguments, so
    ``size``/``path``/``getmetrics`` mirror it and a chain can stand in for
    a font wherever only those are read (vtext's punctuation check)."""

    def __init__(self, fonts: List[ImageFont.FreeTypeFont], symbol: frozenset = frozenset()):
        self.fonts = fonts
        self._symbol = symbol         # indexes of the symbol-only fallbacks
        self.primary = fonts[0]
        self.size = self.primary.size
        self.path = getattr(self.primary, "path", None)
        self._cmaps = [_cmap(getattr(f, "path", None)) for f in fonts]
        self._pick: dict = {}

    def getmetrics(self):
        return self.primary.getmetrics()

    def font_for(self, ch: str) -> ImageFont.FreeTypeFont:
        f = self._pick.get(ch)
        if f is None:
            f = self.primary
            cp = ord(ch[0]) if ch else 0
            # control chars / spaces stay with the primary font
            if cp > 0x20:
                cjk = _is_cjk(cp)
                for i, (font, cmap) in enumerate(zip(self.fonts, self._cmaps)):
                    if cjk and i in self._symbol:
                        continue
                    if cmap is None or cp in cmap:
                        f = font
                        break
            self._pick[ch] = f
        return f

    def covers(self, cp: int) -> bool:
        return any(cmap is None or cp in cmap for cmap in self._cmaps)

    def runs(self, text: str):
        """[(substring, font)] in order; one run when the primary covers all."""
        out = []
        for ch in text:
            f = self.font_for(ch)
            if out and out[-1][1] is f:
                out[-1][0].append(ch)
            else:
                out.append(([ch], f))
        return [("".join(chars), f) for chars, f in out]

    def getlength(self, text: str) -> float:
        rs = self.runs(text)
        if len(rs) == 1:
            return rs[0][1].getlength(rs[0][0])
        return sum(f.getlength(t) for t, f in rs)


def runs(text: str, chain: FontChain):
    """Split text into (substring, font) runs by covering font."""
    return chain.runs(text)


def get_font_chain(size: float, family: Optional[str] = None,
                   bold: bool = False) -> FontChain:
    """:func:`get_font` followed by the symbol fonts and the system
    fallbacks (bold ones first for bold text) that exist on this host."""
    primary = get_font(size, family, bold)
    key = (getattr(primary, "path", None), primary.size, bool(bold))
    chain = _chain_cache.get(key)
    if chain is None:
        fonts, seen, symbol = [primary], {key[0]}, set()
        extra = _SYMBOL_FALLBACKS + (_BOLD_FALLBACKS + _FALLBACKS if bold else _FALLBACKS)
        for p in extra:
            if p in seen or not os.path.exists(p):
                continue
            seen.add(p)
            try:
                f = _cache.get((p, primary.size))
                if f is None:
                    f = _cache[(p, primary.size)] = ImageFont.truetype(p, primary.size)
                if p in _SYMBOL_FALLBACKS:
                    symbol.add(len(fonts))
                fonts.append(f)
            except OSError:
                continue
        chain = _chain_cache[key] = FontChain(fonts, frozenset(symbol))
    return chain
