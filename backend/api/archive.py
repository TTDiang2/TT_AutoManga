from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path
import json
import logging
import re
import shutil
import uuid
import base64
import zipfile
import io

from ..core.config import _backup_corrupt

router = APIRouter(prefix="/api/archive", tags=["archive"])

logger = logging.getLogger(__name__)

ARCHIVE_DIR = Path(__file__).parent.parent.parent / "data" / "archive"
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
METADATA_FILE = ARCHIVE_DIR / "metadata.json"
ARCHIVE_ROOT = ARCHIVE_DIR.resolve()

# Folder ids become directory names under data/archive — same rule as
# project ids, so ids can never traverse out of the archive.
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _validate_id(value: str, what: str = "id") -> str:
    if not isinstance(value, str) or not _SAFE_ID_RE.fullmatch(value):
        raise HTTPException(
            status_code=400,
            detail=f"invalid {what}: only letters, digits, '_' and '-' are allowed")
    return value


def _archive_file(path: str) -> Path:
    """Resolve a metadata-recorded path, refusing anything outside data/archive."""
    p = Path(path).resolve()
    if not p.is_relative_to(ARCHIVE_ROOT):
        raise HTTPException(status_code=400,
                            detail="image path is outside the archive directory")
    return p


class ArchiveImage(BaseModel):
    id: str
    name: str
    path: str
    folder_id: Optional[str] = None
    created_at: str
    thumbnail_path: Optional[str] = None


class ArchiveFolder(BaseModel):
    id: str
    name: str
    parent_id: Optional[str] = None
    created_at: str
    sort_order: int = 0
    group: Optional[str] = None


class ArchiveMetadata(BaseModel):
    images: List[ArchiveImage]
    folders: List[ArchiveFolder]


def load_metadata() -> ArchiveMetadata:
    if METADATA_FILE.exists():
        try:
            with open(METADATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return ArchiveMetadata(**data)
        except Exception as e:
            logger.warning("archive metadata unreadable (%s); backed up and "
                           "starting empty", e)
            _backup_corrupt(METADATA_FILE)
    return ArchiveMetadata(images=[], folders=[])


def save_metadata(metadata: ArchiveMetadata) -> None:
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(metadata.model_dump(), f, indent=2)


@router.get("/images")
async def list_images(folder_id: Optional[str] = None):
    metadata = load_metadata()
    if folder_id is None:
        return [img for img in metadata.images if img.folder_id is None]
    return [img for img in metadata.images if img.folder_id == folder_id]


@router.get("/folders")
async def list_folders(parent_id: Optional[str] = None, sort_by: Optional[str] = None):
    metadata = load_metadata()
    folders = metadata.folders if parent_id is None else [f for f in metadata.folders if f.parent_id == parent_id]
    if sort_by == "name":
        folders = sorted(folders, key=lambda f: f.name.lower())
    elif sort_by == "created":
        folders = sorted(folders, key=lambda f: float(f.created_at))
    else:
        folders = sorted(folders, key=lambda f: f.sort_order)
    return folders


@router.post("/folders")
async def create_folder(folder: ArchiveFolder):
    _validate_id(folder.id, "folder id")
    metadata = load_metadata()
    if any(f.id == folder.id for f in metadata.folders):
        raise HTTPException(status_code=400, detail="Folder already exists")
    metadata.folders.append(folder)
    save_metadata(metadata)
    folder_path = ARCHIVE_DIR / folder.id
    folder_path.mkdir(parents=True, exist_ok=True)
    return {"success": True, "id": folder.id}


@router.patch("/folders/{folder_id}")
async def update_folder(folder_id: str, req: dict):
    metadata = load_metadata()
    folder = next((f for f in metadata.folders if f.id == folder_id), None)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    if "name" in req:
        folder.name = req["name"]
    if "group" in req:
        folder.group = req["group"]
    if "sort_order" in req:
        folder.sort_order = req["sort_order"]
    save_metadata(metadata)
    return {"success": True, "folder": folder}


@router.delete("/folders/{folder_id}")
async def delete_folder(folder_id: str):
    _validate_id(folder_id, "folder id")
    metadata = load_metadata()
    folder = next((f for f in metadata.folders if f.id == folder_id), None)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    metadata.folders = [f for f in metadata.folders if f.id != folder_id]
    metadata.images = [img for img in metadata.images if img.folder_id != folder_id]
    save_metadata(metadata)
    folder_path = ARCHIVE_DIR / folder_id
    if folder_path.exists():
        shutil.rmtree(folder_path)
    return {"success": True}


@router.post("/images")
async def add_image(req: dict):
    source_data = req.get("source_data") or req.get("source_path")
    name = req.get("name", "Untitled")
    folder_id = req.get("folder_id")

    if not source_data:
        raise HTTPException(status_code=400, detail="No source data provided")
    if folder_id:
        _validate_id(folder_id, "folder id")

    metadata = load_metadata()
    image_id = str(uuid.uuid4())

    target_dir = ARCHIVE_DIR / (folder_id if folder_id else "root")
    target_dir.mkdir(parents=True, exist_ok=True)
    
    target_path = target_dir / f"{image_id}.png"
    
    if source_data.startswith("data:"):
        header, b64_data = source_data.split(",", 1)
        try:
            img_bytes = base64.b64decode(b64_data, validate=True)
        except Exception:
            raise HTTPException(status_code=400,
                                detail="source is not valid base64 image data")
        with open(target_path, "wb") as f:
            f.write(img_bytes)
    elif source_data.startswith("/api/assets/file/"):
        # Asset referenced by URL (post-refactor panel images).
        from ..storage.asset_store import asset_store
        source = asset_store.path_for(source_data.rsplit("/", 1)[-1])
        if source is None:
            raise HTTPException(status_code=400, detail="Source asset not found")
        shutil.copy2(source, target_path)
    else:
        # Only embedded data URLs and managed assets are accepted; an
        # arbitrary filesystem path here would turn this endpoint into a
        # copy-anything-then-serve-it read primitive.
        raise HTTPException(
            status_code=400,
            detail="source must be a data: URL or an /api/assets/file/ reference")

    image = ArchiveImage(
        id=image_id,
        name=name,
        path=str(target_path),
        folder_id=folder_id,
        created_at=str(Path(target_path).stat().st_mtime)
    )
    metadata.images.append(image)
    save_metadata(metadata)
    
    return {"success": True, "id": image_id, "path": str(target_path)}


@router.patch("/images/{image_id}")
async def update_image(image_id: str, req: dict):
    """Move image to a different folder by updating folder_id."""
    metadata = load_metadata()
    image = next((img for img in metadata.images if img.id == image_id), None)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    new_folder_id = req.get("folder_id")
    old_folder_id = image.folder_id
    image.folder_id = new_folder_id
    save_metadata(metadata)
    
    return {"success": True, "folder_id": new_folder_id}


@router.delete("/images/{image_id}")
async def delete_image(image_id: str):
    metadata = load_metadata()
    image = next((img for img in metadata.images if img.id == image_id), None)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Drop the entry even when the recorded file is missing or lives outside
    # the archive (legacy metadata); otherwise it could never be removed.
    try:
        image_path = _archive_file(image.path)
        if image_path.exists():
            image_path.unlink()
    except HTTPException:
        logger.warning("archive image %s points outside the archive (%s); "
                       "removing metadata entry only", image_id, image.path)

    metadata.images = [img for img in metadata.images if img.id != image_id]
    save_metadata(metadata)
    return {"success": True}


@router.get("/images/{image_id}/serve")
async def serve_image(image_id: str):
    metadata = load_metadata()
    image = next((img for img in metadata.images if img.id == image_id), None)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(_archive_file(image.path))


@router.get("/folders/{folder_id}/download")
async def download_folder(folder_id: str):
    """Download all PNG images in a folder as a ZIP file."""
    metadata = load_metadata()
    folder = next((f for f in metadata.folders if f.id == folder_id), None)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    images = [img for img in metadata.images if img.folder_id == folder_id]
    if not images:
        raise HTTPException(status_code=404, detail="No images in this folder")

    # Sanitize folder name for zip filename
    safe_name = "".join(c for c in folder.name if c.isalnum() or c in (" ", "_", "-")).rstrip()
    zip_filename = f"{safe_name}_{folder_id}.zip"

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for img in images:
            try:
                img_path = _archive_file(img.path)
            except HTTPException:
                logger.warning("skipping archive image outside root: %s", img.path)
                continue
            if img_path.exists() and img_path.suffix.lower() == ".png":
                zf.write(img_path, img_path.name)
    buffer.seek(0)

    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_filename}"'}
    )
