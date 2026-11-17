"""Resolve element image refs to PIL images / bytes.

Only three ref forms are accepted — data: URLs, managed assets
(``/api/assets/file/<id>``) and archive images
(``/api/archive/images/<id>/serve``, resolved through the archive's own
metadata). Plain filesystem paths are refused: refs come from clients, and
honouring them would let any request read (and export) arbitrary files.
"""
import base64
import io
from pathlib import Path
from typing import Callable, Optional
from PIL import Image

ASSET_PREFIX = "/api/assets/file/"
ARCHIVE_PREFIX = "/api/archive/images/"


def ref_to_path(ref: str, asset_store) -> Optional[Path]:
    """Managed file behind an asset / archive ref, or None (also for data:
    URLs and anything that looks like a filesystem path)."""
    if not isinstance(ref, str):
        return None
    if ref.startswith(ASSET_PREFIX):
        asset_id = ref[len(ASSET_PREFIX):].split("?", 1)[0]
        return asset_store.path_for(asset_id) if asset_id else None
    if ref.startswith(ARCHIVE_PREFIX):
        from ..api.archive import resolve_archive_ref
        return resolve_archive_ref(ref)
    return None


def ref_to_bytes(ref: str, asset_store) -> Optional[bytes]:
    try:
        if not isinstance(ref, str) or not ref:
            return None
        if ref.startswith("data:"):
            return base64.b64decode(ref.partition(",")[2])
        path = ref_to_path(ref, asset_store)
        return path.read_bytes() if path else None
    except Exception:
        return None


def make_resolver(asset_store) -> Callable[[str], Optional[Image.Image]]:
    def resolve(url: str) -> Optional[Image.Image]:
        try:
            if not url:
                return None
            if url.startswith("data:"):
                _, _, b64 = url.partition(",")
                return Image.open(io.BytesIO(base64.b64decode(b64)))
            if url.startswith(ASSET_PREFIX):
                return asset_store.open_image(url[len(ASSET_PREFIX):].split("?", 1)[0])
            path = ref_to_path(url, asset_store)
            if path:
                return Image.open(path)
        except Exception:
            return None
        return None
    return resolve
