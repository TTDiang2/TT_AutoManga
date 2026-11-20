import hashlib
import json
import logging
import re
import shutil
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any
from ..core.config import PROJECTS_DIR, atomic_write_json

logger = logging.getLogger(__name__)

# Client-supplied ids become directory names under data/projects — only
# [A-Za-z0-9_-] is allowed so "../" and friends can never escape it.
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def pages_base(project: Dict[str, Any]) -> str:
    """Version token of a project's composer pages (optimistic concurrency
    for the Composer autosave): sha1 of the canonical JSON of composerPages."""
    pages = project.get("composerPages", []) if project else []
    blob = json.dumps(pages, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


class InvalidProjectIdError(ValueError):
    """Raised when a project id contains characters unsafe for a path."""


def validate_project_id(project_id: str) -> str:
    if not isinstance(project_id, str) or not _SAFE_ID_RE.fullmatch(project_id):
        raise InvalidProjectIdError(
            f"invalid project id {project_id!r}: only letters, digits, "
            "'_' and '-' are allowed")
    return project_id


class StorageManager:
    @staticmethod
    def _migrate_flat_project_file() -> None:
        flat_file = PROJECTS_DIR / "project.json"
        if flat_file.exists():
            try:
                with open(flat_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                new_id = data.get("id") or str(uuid.uuid4())
                if not _SAFE_ID_RE.fullmatch(str(new_id)):
                    new_id = str(uuid.uuid4())
                data["id"] = new_id
                proj_dir = PROJECTS_DIR / new_id
                proj_dir.mkdir(exist_ok=True)
                atomic_write_json(proj_dir / "project.json", data, indent=2)
                flat_file.unlink()
            except Exception as e:
                logger.warning("flat project migration failed: %s", e)

    @staticmethod
    def list_projects() -> List[Dict[str, Any]]:
        StorageManager._migrate_flat_project_file()
        projects = []
        for proj_dir in PROJECTS_DIR.iterdir():
            if proj_dir.is_dir():
                meta_file = proj_dir / "project.json"
                if meta_file.exists():
                    # one damaged project must not hide all the others
                    try:
                        with open(meta_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                    except Exception as e:
                        logger.warning("skipping unreadable %s: %s", meta_file, e)
                        continue
                    if isinstance(data, dict):
                        projects.append(data)
                    else:
                        logger.warning("skipping %s: not a JSON object", meta_file)
        return sorted(projects, key=lambda x: x.get("updatedAt", ""), reverse=True)

    @staticmethod
    def _normalize_image_refs(project: Dict[str, Any]) -> None:
        """Rewrite embedded data-URL images as asset files, referenced by URL."""
        from .asset_store import asset_store
        pid = project.get("id")

        def norm(v, kind):
            if isinstance(v, str) and v.startswith("data:"):
                entry = asset_store.save_dataurl(v, project_id=pid, kind=kind)
                return asset_store.url_for(entry["asset_id"])
            return v

        for panel in project.get("panels", []):
            if panel.get("image"):
                panel["image"] = norm(panel["image"], "panel")
        for page in project.get("composerPages", []):
            for el in page.get("elements", []):
                if el.get("src"):
                    el["src"] = norm(el["src"], "composer")
                if el.get("originalSrc"):
                    el["originalSrc"] = norm(el["originalSrc"], "composer")

    @staticmethod
    def save_project(project_data: Dict[str, Any]) -> Dict[str, Any]:
        project_id = project_data.get("id") or str(uuid.uuid4())
        validate_project_id(project_id)
        project_data["id"] = project_id

        proj_dir = PROJECTS_DIR / project_id
        proj_dir.mkdir(exist_ok=True)

        from datetime import datetime, timezone
        project_data["updatedAt"] = datetime.now(timezone.utc).isoformat()

        StorageManager._normalize_image_refs(project_data)

        atomic_write_json(proj_dir / "project.json", project_data, indent=2)

        return project_data

    @staticmethod
    def load_project(project_id: str) -> Optional[Dict[str, Any]]:
        validate_project_id(project_id)
        proj_dir = PROJECTS_DIR / project_id
        meta_file = proj_dir / "project.json"

        if meta_file.exists():
            with open(meta_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    @staticmethod
    def delete_project(project_id: str) -> bool:
        validate_project_id(project_id)
        proj_dir = PROJECTS_DIR / project_id
        if proj_dir.exists():
            shutil.rmtree(proj_dir)
            # a deleted project is no longer an episode of any collection
            from .collections import remove_project
            remove_project(project_id)
            return True
        return False


storage = StorageManager()
