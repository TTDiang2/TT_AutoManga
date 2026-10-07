"""File-based asset storage.

Images used to be embedded in project.json as base64 data URLs, which made
projects grow unbounded. Assets now live as flat files under ``data/assets/``
with metadata in ``data/assets/index.json``; projects reference them via
``/api/assets/file/<asset_id>`` URLs. ``StorageManager.save_project``
normalizes legacy data URLs on save (see manager.py).
"""
import base64
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

_EXT_BY_MIME = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


class AssetStore:
    def __init__(self, root: Path, index_file: Path):
        self.root = root
        self.index_file = index_file
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._index: Dict[str, Dict[str, Any]] = self._load()

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if self.index_file.exists():
            try:
                with open(self.index_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except Exception:
                pass
        return {}

    def _flush(self) -> None:
        tmp = self.index_file.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._index, f, ensure_ascii=False, indent=2)
        tmp.replace(self.index_file)

    def save_bytes(self, data: bytes, ext: str = "png", *,
                   project_id: Optional[str] = None, kind: str = "embed",
                   meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        asset_id = uuid.uuid4().hex
        ext = (ext or "png").lstrip(".").lower()
        if ext not in ("png", "jpg", "jpeg", "webp"):
            ext = "png"
        path = self.root / f"{asset_id}.{ext}"
        path.write_bytes(data)
        entry = {
            "asset_id": asset_id,
            "path": str(path),
            "project_id": project_id,
            "kind": kind,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            **(meta or {}),
        }
        with self._lock:
            self._index[asset_id] = entry
            self._flush()
        return entry

    def save_dataurl(self, dataurl: str, **kwargs) -> Dict[str, Any]:
        header, _, b64 = dataurl.partition(",")
        mime = header[5:].split(";")[0] if header.startswith("data:") else "image/png"
        ext = _EXT_BY_MIME.get(mime, "png")
        return self.save_bytes(base64.b64decode(b64), ext=ext, **kwargs)

    def get(self, asset_id: str) -> Optional[Dict[str, Any]]:
        return self._index.get(asset_id)

    def url_for(self, asset_id: str) -> str:
        return f"/api/assets/file/{asset_id}"

    def path_for(self, asset_id: str) -> Optional[Path]:
        entry = self._index.get(asset_id)
        if entry and Path(entry["path"]).exists():
            return Path(entry["path"])
        return None

    def open_image(self, asset_id: str):
        p = self.path_for(asset_id)
        if p is None:
            return None
        try:
            from PIL import Image
            return Image.open(p)
        except Exception:
            return None

    def ids(self):
        return set(self._index.keys())

    def remove(self, asset_id: str) -> bool:
        with self._lock:
            entry = self._index.pop(asset_id, None)
            self._flush()
        if entry:
            Path(entry["path"]).unlink(missing_ok=True)
            return True
        return False


from ..core.config import DATA_DIR  # noqa: E402

asset_store = AssetStore(DATA_DIR / "assets", DATA_DIR / "assets" / "index.json")
