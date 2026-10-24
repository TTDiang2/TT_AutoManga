from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path
import json
import logging

from ..core.swarmui_client import swarm_client
from ..core.config import settings, LoraConfig

router = APIRouter(prefix="/api/characters/templates", tags=["character_templates"])

TEMPLATES_FILE = Path(__file__).parent.parent.parent / "data" / "character_templates.json"

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
    with open(TEMPLATES_FILE, "w", encoding="utf-8") as f:
        json.dump(templates, f, indent=2)


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
    project_id: str


@router.post("/generate-image")
async def generate_character_image(req: GenerateCharacterImageRequest):
    swarmsettings = settings.swarmui
    loras = None
    if swarmsettings.currentLoras:
        loras = [LoraConfig(name=l.get("name", ""), weight=l.get("weight", 1.0)) for l in swarmsettings.currentLoras if l.get("name")]

    try:
        result = await swarm_client.generate_image(
            prompt=req.prompt,
            negative_prompt=req.negative_prompt,
            model=swarmsettings.currentModel or None,
            steps=swarmsettings.currentSteps,
            cfg_scale=swarmsettings.currentCfgScale,
            width=swarmsettings.currentWidth,
            height=swarmsettings.currentHeight,
            sampler_name=swarmsettings.currentSamplerName,
            loras=loras,
            seed=req.seed
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))