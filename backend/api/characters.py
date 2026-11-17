from contextlib import contextmanager
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ValidationError, field_validator
from typing import Optional, List, Dict, Any
from pathlib import Path
import base64
import binascii
import json
import logging
import math
import re
import threading

from ..core.config import atomic_write_json

router = APIRouter(prefix="/api/characters", tags=["characters"])

logger = logging.getLogger(__name__)

CHARACTERS_FILE = Path(__file__).parent.parent.parent / "data" / "characters.json"

# One lock around every read-modify-write of characters.json: the API
# handlers here and the training worker (training._set_character_lora).
CHARACTERS_LOCK = threading.RLock()

_LORA_NAME_RE = re.compile(r"^[\w .-]+(/[\w .-]+)*$")


class CharacterLora(BaseModel):
    """A trained LoRA for the character: the SwarmUI name relative to
    Models/Lora without extension (e.g. "SecondFloor/sf_nova"), its weight and
    trigger word (None: the name convention, sf_nova -> sfnova)."""
    name: str
    weight: float = Field(default=0.8, ge=0, le=2, allow_inf_nan=False)
    trigger: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not _LORA_NAME_RE.fullmatch(v) or ".." in v:
            raise ValueError("a LoRA name is folder/name of letters, digits, "
                             "space, _ . and - (no ..)")
        return v

    @field_validator("trigger")
    @classmethod
    def _trigger(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if any(c in v for c in "<>:") or any(ord(c) < 32 for c in v):
            raise ValueError("a trigger word can't contain <, >, : or control characters")
        return v.strip() or None


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
    refWeight: Optional[float] = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    # the character's age (0-120; None = unknown). Mature projects only make
    # mature images of characters known to be adults (18+): unknown is SFW
    age: Optional[int] = Field(default=None, ge=0, le=120)
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None


def _load_characters() -> List[Dict[str, Any]]:
    if CHARACTERS_FILE.exists():
        with open(CHARACTERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_characters(characters: List[Dict[str, Any]]) -> None:
    atomic_write_json(CHARACTERS_FILE, characters, indent=2, ensure_ascii=False)


@contextmanager
def edit_characters():
    """Read-modify-write characters.json under CHARACTERS_LOCK: yields the
    list; it is saved when the block exits normally."""
    with CHARACTERS_LOCK:
        characters = _load_characters()
        yield characters
        _save_characters(characters)


_DATA_URL_RE = re.compile(r"data:image/(png|jpeg|jpg|webp);base64,", re.I)


def migrate_character_images(characters: List[Dict[str, Any]]) -> Dict[str, int]:
    """Move data-URL sheets (``image``) into the asset store (kind
    "character") and keep their /api/assets/file/<id> URL instead, in place.
    Idempotent: asset URLs are left alone. A data URL that does not decode
    stays as it is (counted in ``failed``)."""
    from ..storage import asset_store as asset_store_mod
    store = asset_store_mod.asset_store
    migrated = failed = 0
    for c in characters:
        img = c.get("image") if isinstance(c, dict) else None
        if not isinstance(img, str) or not img.startswith("data:"):
            continue
        m = _DATA_URL_RE.match(img)
        try:
            if not m:
                raise ValueError("not a base64 PNG/JPEG/WebP data URL")
            data = base64.b64decode(img[m.end():], validate=False)
            if not data:
                raise ValueError("empty image")
        except (ValueError, binascii.Error) as e:
            logger.warning("character %s: image not migrated (%s)", c.get("id"), e)
            failed += 1
            continue
        entry = store.save_bytes(data, ext=m.group(1).lower(), kind="character",
                                 meta={"character_id": c.get("id")})
        c["image"] = store.url_for(entry["asset_id"])
        migrated += 1
    return {"migrated": migrated, "failed": failed}


@router.post("/migrate-images")
async def migrate_images():
    """Convert every library character's data-URL sheet into an asset (the
    Characters tab's "move photos out of characters.json" button)."""
    with edit_characters() as characters:
        result = migrate_character_images(characters)
    if result["migrated"]:
        logger.info("characters: %d image(s) moved to the asset store", result["migrated"])
    return {"success": True, **result}


@router.get("/")
async def list_characters():
    with CHARACTERS_LOCK:
        return _load_characters()


@router.post("/")
async def save_characters(characters: List[CharacterInput]):
    with CHARACTERS_LOCK:
        _save_characters([c.model_dump() for c in characters])
    return {"success": True}


@router.post("/add")
async def add_character(character: CharacterInput):
    with edit_characters() as characters:
        characters.append(character.model_dump())
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
            if isinstance(w, bool) or not isinstance(w, (int, float)) \
                    or not math.isfinite(w) or not 0 <= w <= 1:
                raise HTTPException(status_code=422, detail="refWeight: a number from 0 to 1 (0 = off)")
            updates["refWeight"] = round(float(w), 3) or None
    if "age" in updates:
        # null clears it; else a whole number 0-120
        a = updates["age"]
        if a is not None:
            if isinstance(a, bool) or not isinstance(a, int) or not 0 <= a <= 120:
                raise HTTPException(status_code=422, detail="age: a whole number from 0 to 120 (or null = unknown)")
    with CHARACTERS_LOCK:
        characters = _load_characters()
        for c in characters:
            if c["id"] == character_id:
                c.update(updates)
                _save_characters(characters)
                return {"success": True}
    raise HTTPException(status_code=404, detail="Character not found")


@router.delete("/{character_id}")
async def delete_character(character_id: str):
    with edit_characters() as characters:
        characters[:] = [c for c in characters if c["id"] != character_id]
    return {"success": True}
