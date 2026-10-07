"""Resolve element image refs (asset URL / data URL / legacy path) to PIL images."""
from typing import Callable, Optional
from PIL import Image


def make_resolver(asset_store) -> Callable[[str], Optional[Image.Image]]:
    def resolve(url: str) -> Optional[Image.Image]:
        try:
            if not url:
                return None
            if url.startswith("data:"):
                import base64, io
                _, _, b64 = url.partition(",")
                return Image.open(io.BytesIO(base64.b64decode(b64)))
            if url.startswith("/api/assets/file/"):
                return asset_store.open_image(url.rsplit("/", 1)[-1])
            from pathlib import Path
            p = Path(url)
            if p.is_file():
                return Image.open(p)  # legacy absolute paths / archive files
        except Exception:
            return None
        return None
    return resolve
