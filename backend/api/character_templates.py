from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import json
import logging

from ..core.swarmui_client import swarm_client
from ..core.config import DATA_DIR, settings, atomic_write_json

router = APIRouter(prefix="/api/characters/templates", tags=["character_templates"])

TEMPLATES_FILE = DATA_DIR / "character_templates.json"

TEMPLATES_FILE.parent.mkdir(parents=True, exist_ok=True)

DEFAULT_TEMPLATES = [
    {
        "id": "protagonist",
        "name": "Protagonist",
        "description": "Main hero/heroine of the story",
        "appearance": "young adult, heroic expression, distinctive outfit",
        "isBuiltIn": True,
        "createdAt": "2026-01-01T00:00:00Z"
    },
    {
        "id": "mentor",
        "name": "Mentor Figure",
        "description": "Wise guide or teacher character",
        "appearance": "older, wise expression, formal or traditional clothing",
        "isBuiltIn": True,
        "createdAt": "2026-01-01T00:00:00Z"
    },
    {
        "id": "villain",
        "name": "Villain",
        "description": "Antagonist character",
        "appearance": "menacing expression, dark clothing, dramatic pose",
        "isBuiltIn": True,
        "createdAt": "2026-01-01T00:00:00Z"
    }
]


class CharacterTemplate(BaseModel):
    id: str
    name: str
    description: str
    appearance: Optional[str] = None
    image: Optional[str] = None
    isBuiltIn: bool = False
    createdAt: str


def load_templates() -> List[dict]:
    if TEMPLATES_FILE.exists():
        try:
            with open(TEMPLATES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.warning("character templates file unreadable (%s); using built-ins", e)
    return DEFAULT_TEMPLATES.copy()


def save_templates(templates: List[dict]) -> None:
    atomic_write_json(TEMPLATES_FILE, templates, indent=2)


@router.get("/")
async def get_templates():
    return load_templates()


@router.post("/")
async def create_template(template: CharacterTemplate):
    templates = load_templates()
    if any(t["id"] == template.id for t in templates):
        raise HTTPException(status_code=400, detail="Template ID already exists")
    templates.append(template.model_dump())
    save_templates(templates)
    return {"success": True, "id": template.id}


@router.delete("/{template_id}")
async def delete_template(template_id: str):
    templates = load_templates()
    for t in templates:
        if t["id"] == template_id:
            if t.get("isBuiltIn"):
                raise HTTPException(status_code=400, detail="Cannot delete built-in templates")
            templates.remove(t)
            save_templates(templates)
            return {"success": True}
    raise HTTPException(status_code=404, detail="Template not found")


class GenerateCharacterImageRequest(BaseModel):
    prompt: str
    negative_prompt: str = ""
    seed: Optional[int] = None
    character_id: str
    project_id: str = ""


@router.post("/generate-image")
async def generate_character_image(req: GenerateCharacterImageRequest):
    swarmsettings = settings.swarmui
    loras = None
    if swarmsettings.currentLoras:
        # settings loras are LoraConfig models (settings.py normalizes on save)
        loras = [l for l in swarmsettings.currentLoras if l.name]

    # the content rating (backend/content_rating.py): the project's (else the
    # global default), judged on this character's own age and description
    from ..content_rating import RatingRefused, apply_rating, character_record
    from ..storage.manager import storage, InvalidProjectIdError
    project = None
    try:
        project = storage.load_project(req.project_id) if req.project_id else None
    except InvalidProjectIdError:
        project = None
    from .characters import _load_characters
    try:
        library = _load_characters()
    except Exception as e:   # unreadable library: the character's age is unknown
        logging.warning("characters library unreadable: %s", e)
        library = []
    char = next((c for c in library if isinstance(c, dict) and c.get("id") == req.character_id), None)
    if char:
        rec = character_record(char.get("name") or "", None, [char])
    else:
        rec = {"name": "this character", "age": None, "text": req.prompt}
    rec["text"] = f"{rec['text']}, {req.prompt}"
    try:
        rated = apply_rating(req.prompt, req.negative_prompt, project=project, cast=[rec])
    except RatingRefused as e:
        raise HTTPException(status_code=400, detail=str(e))
    if rated["notice"]:
        logging.info("character sheet %s: %s", req.character_id, rated["notice"])

    try:
        result = await swarm_client.generate_image(
            prompt=rated["prompt"],
            negative_prompt=rated["negative"],
            model=swarmsettings.currentModel or None,
            steps=swarmsettings.currentSteps,
            cfg_scale=swarmsettings.currentCfgScale,
            width=swarmsettings.currentWidth,
            height=swarmsettings.currentHeight,
            sampler_name=swarmsettings.currentSamplerName,
            loras=loras,
            seed=req.seed
        )
        result["content_rating"] = rated["rating"]
        if rated["notice"]:
            result["notice"] = rated["notice"]
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))