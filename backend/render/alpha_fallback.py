"""Local transparent-background fallback.

SwarmUI's RemoveBackground component can be missing or broken (e.g. Numba /
NumPy version conflicts). When a caller asks for a transparent asset and the
result comes back opaque, we retry locally:

1. ``rembg`` (U2Net) if the package is importable — best quality, handles
   complex scenes.
2. Luminance threshold — works well for illustrations on plain white
   backgrounds (the agent should prompt for that), falls back gracefully
   otherwise. The method used is always reported so callers can re-roll.
"""
import io
import logging
from typing import Tuple
from PIL import Image

logger = logging.getLogger(__name__)


def ensure_alpha(img_bytes: bytes) -> Tuple[bytes, str]:
    """Return (png_bytes, method). method ∈ swarmui|rembg|threshold|none."""
    img = Image.open(io.BytesIO(img_bytes))
    if img.mode == "RGBA":
        alpha_min, _ = img.getchannel("A").getextrema()
        if alpha_min < 255:
            return img_bytes, "swarmui"

    # 1) rembg if installed
    try:
        from rembg import remove  # type: ignore
        out = remove(Image.open(io.BytesIO(img_bytes)))
        buf = io.BytesIO()
        out.save(buf, format="PNG")
        return buf.getvalue(), "rembg"
    except ImportError:
        pass
    except Exception as e:
        logger.warning("rembg fallback failed (%s); using white-threshold", e)

    # 2) luminance threshold (white-background illustrations)
    rgb = img.convert("RGB")
    gray = rgb.convert("L")
    alpha = gray.point(
        lambda v: 0 if v > 235 else (255 if v < 200 else int((235 - v) / 35 * 255)))
    rgba = rgb.convert("RGBA")
    rgba.putalpha(alpha)
    buf = io.BytesIO()
    rgba.save(buf, format="PNG")
    return buf.getvalue(), "threshold"
