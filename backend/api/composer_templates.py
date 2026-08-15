"""User-saved composer frame templates.

Templates store only the geometric layout of a composer page (x/y/w/h/rotation,
optional 4-corner deformation, label). Image data (base64 src) is intentionally
stripped on save and not persisted, so templates can be safely shared or reused
without leaking generated/uploaded artwork.

Persistence is a single JSON file under ``data/composer_templates.json`` — same
pattern as ``backend/api/layouts.py``.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Any
from pathlib import Path
import json
import time

router = APIRouter(prefix="/api/composer/templates", tags=["composer-templates"])

TEMPLATES_FILE = Path(__file__).parent.parent.parent / "data" / "composer_templates.json"
TEMPLATES_FILE.parent.mkdir(parents=True, exist_ok=True)


class SavedTemplateElement(BaseModel):
    """Mirrors ``frontend/src/types`` ``ComposerTemplate.elements`` shape.

    Fields beyond x/y/w/h/rotation are kept optional because built-in
    templates only carry geometry. ``corners`` is added so users can save
    deformed (non-rectangular) frames.
    """

    type: str = "image-slot"
    x: float
    y: float
    width: float
    height: float
    rotation: float = 0
    label: Optional[str] = None
    corners: Optional[dict] = None  # QuadCorners {tl,tr,br,bl:{x,y}} in bbox %


class SavedTemplate(BaseModel):
    id: str
    name: str
    width: int
    height: int
    elements: List[SavedTemplateElement] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())


def _load() -> List[dict]:
    if TEMPLATES_FILE.exists():
        try:
            with open(TEMPLATES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
    return []


def _save(templates: List[dict]) -> None:
    with open(TEMPLATES_FILE, "w", encoding="utf-8") as f:
        json.dump(templates, f, indent=2, ensure_ascii=False)


def _strip_image_payload(el: dict) -> dict:
    """Remove any image payload fields before persisting.

    User-saved templates intentionally do NOT carry image base64. If a user
    saves a page that has image elements (not slots), we keep only the
    geometry and turn the element into an empty slot.
    """
    cleaned = {k: v for k, v in el.items() if k not in ("src", "originalSrc", "cropArea")}
    if cleaned.get("type") in ("image", "page-image"):
        cleaned["type"] = "image-slot"
        cleaned.pop("label", None)
        cleaned["label"] = "Frame"
    return cleaned


@router.get("/")
async def list_templates() -> List[dict]:
    return _load()


@router.get("/{template_id}")
async def get_template(template_id: str):
    for t in _load():
        if t.get("id") == template_id:
            return t
    raise HTTPException(status_code=404, detail="Template not found")


@router.post("/")
async def create_template(template: SavedTemplate):
    payload = template.model_dump()
    payload["elements"] = [_strip_image_payload(dict(e)) for e in payload.get("elements", [])]

    existing = _load()
    if any(t.get("id") == payload["id"] for t in existing):
        raise HTTPException(status_code=400, detail="Template ID already exists")

    now = _now_iso()
    payload.setdefault("created_at", now)
    payload["updated_at"] = now
    existing.append(payload)
    _save(existing)
    return {"success": True, "id": payload["id"], "template": payload}


@router.put("/{template_id}")
async def update_template(template_id: str, template: SavedTemplate):
    payload = template.model_dump()
    payload["elements"] = [_strip_image_payload(dict(e)) for e in payload.get("elements", [])]

    existing = _load()
    for i, t in enumerate(existing):
        if t.get("id") == template_id:
            payload["id"] = template_id
            payload["created_at"] = t.get("created_at") or _now_iso()
            payload["updated_at"] = _now_iso()
            existing[i] = payload
            _save(existing)
            return {"success": True}
    raise HTTPException(status_code=404, detail="Template not found")


@router.delete("/{template_id}")
async def delete_template(template_id: str):
    existing = _load()
    for t in existing:
        if t.get("id") == template_id:
            existing.remove(t)
            _save(existing)
            return {"success": True}
    raise HTTPException(status_code=404, detail="Template not found")