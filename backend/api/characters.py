from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ValidationError
from typing import Optional, List, Dict, Any
from pathlib import Path
import json

from ..core.config import atomic_write_json

router = APIRouter(prefix="/api/characters", tags=["characters"])

CHARACTERS_FILE = Path(__file__).parent.parent.parent / "data" / "characters.json"


class CharacterLora(BaseModel):
    """A trained LoRA for the character: the SwarmUI name relative to
    Models/Lora without extension (e.g. "SecondFloor/sf_nova"), its weight and
    trigger word (None: the name convention, sf_nova -> sfnova)."""
    name: str
    weight: float = 0.8
    trigger: Optional[str] = None


class CharacterInput(BaseModel):
    id: str
    name: str
    description: str = ""
    appearance: Optional[str] = None
    image: Optional[str] = None
    sourcePanelIds: List[str] = []
    lora: Optional[CharacterLora] = None
    # 0-1: how strongly the sheet (``image``) guides the character's solo
    # panels through SwarmUI's IP-Adapter; None / 0 = off (opt-in)
    refWeight: Optional[float] = None
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None


def _load_characters() -> List[Dict[str, Any]]:
    if CHARACTERS_FILE.exists():
        with open(CHARACTERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_characters(characters: List[Dict[str, Any]]) -> None:
    atomic_write_json(CHARACTERS_FILE, characters, indent=2, ensure_ascii=False)


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
    if "lora" in updates:
        # null or a name-less entry clears it; anything else must be {name, weight, trigger}
        lora = updates["lora"]
        if lora is None or (isinstance(lora, dict) and not str(lora.get("name") or "").strip()):
            updates["lora"] = None
        else:
            try:
                updates["lora"] = CharacterLora.model_validate(lora).model_dump()
            except ValidationError as e:
                raise HTTPException(status_code=422, detail=f"lora: {e.errors()[0].get('msg', 'invalid')}")
    if "refWeight" in updates:
        # null or 0 turns the sheet reference off; else a number in 0..1
        w = updates["refWeight"]
        if w is not None:
            if isinstance(w, bool) or not isinstance(w, (int, float)) or not 0 <= w <= 1:
                raise HTTPException(status_code=422, detail="refWeight: a number from 0 to 1 (0 = off)")
            updates["refWeight"] = round(float(w), 3) or None
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
