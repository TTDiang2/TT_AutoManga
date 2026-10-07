"""Prompt-block resolution for characters and project style profiles.

Character blocks resolve per panel: project-scoped entries
(``project.settings.characters = [{name, prompt_block}]``) win over the
global character library (``data/characters.json``), matched by name
(case-insensitive). Global entries use their ``appearance`` (falling back to
``description``) as the prompt block.
"""
import json
from pathlib import Path
from typing import Any, Dict, List

from .core.config import DATA_DIR

_CHARACTERS_FILE = DATA_DIR / "characters.json"


def _global_blocks() -> Dict[str, str]:
    try:
        with open(_CHARACTERS_FILE, "r", encoding="utf-8") as f:
            chars = json.load(f)
    except Exception:
        return {}
    out = {}
    for c in chars if isinstance(chars, list) else []:
        name = (c.get("name") or "").strip()
        block = (c.get("appearance") or c.get("description") or "").strip()
        if name and block:
            out[name.lower()] = block
    return out


def resolve_blocks(project: Dict[str, Any]) -> Dict[str, str]:
    """Merged {lowercase name -> prompt block}; project entries win."""
    merged = _global_blocks()
    for c in (project.get("settings") or {}).get("characters") or []:
        name = (c.get("name") or "").strip()
        block = (c.get("prompt_block") or "").strip()
        if name and block:
            merged[name.lower()] = block
    return merged


def blocks_for_panel(project: Dict[str, Any], panel: Dict[str, Any]) -> List[str]:
    """Prompt blocks for the characters listed on a panel, in panel order."""
    blocks = resolve_blocks(project)
    out = []
    for name in panel.get("characters") or []:
        block = blocks.get(str(name).strip().lower())
        if block:
            out.append(block)
    return out


def style_suffix(project: Dict[str, Any]) -> str:
    return ((project.get("settings") or {}).get("style") or "").strip()
