from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from pathlib import Path
import json

router = APIRouter(prefix="/api/characters", tags=["characters"])

CHARACTERS_FILE = Path(__file__).parent.parent.parent / "data" / "characters.json"


class CharacterInput(BaseModel):
    id: str
    name: str
    description: str = ""
    appearance: Optional[str] = None
    image: Optional[str] = None
    sourcePanelIds: List[str] = []
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None


def _load_characters() -> List[Dict[str, Any]]:
    if CHARACTERS_FILE.exists():
        with open(CHARACTERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_characters(characters: List[Dict[str, Any]]) -> None:
    CHARACTERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CHARACTERS_FILE, "w", encoding="utf-8") as f:
        json.dump(characters, f, indent=2, ensure_ascii=False)


@router.get("/")
async def list_characters():
    return _load_characters()


@router.post("/")
async def save_characters(characters: List[CharacterInput]):
    _save_characters([c.model_dump() for c in characters])
    return {"success": True}


@router.post("/add")
async def add_character(character: CharacterInput):
    characters = _load_characters()
    characters.append(character.model_dump())
    _save_characters(characters)
    return {"success": True}


@router.patch("/{character_id}")
async def update_character(character_id: str, updates: Dict[str, Any]):
    characters = _load_characters()
    for c in characters:
        if c["id"] == character_id:
            c.update(updates)
            _save_characters(characters)
            return {"success": True}
    raise HTTPException(status_code=404, detail="Character not found")


@router.delete("/{character_id}")
async def delete_character(character_id: str):
    characters = _load_characters()
    characters = [c for c in characters if c["id"] != character_id]
    _save_characters(characters)
    return {"success": True}
