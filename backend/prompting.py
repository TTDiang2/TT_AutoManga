"""Prompt-block resolution for characters and project style profiles.

Character blocks resolve per panel: project-scoped entries
(``project.settings.characters = [{name, prompt_block}]``) win over the
global character library (``data/characters.json``), matched by name
(case-insensitive). Global entries use their ``appearance`` (falling back to
``description``) as the prompt block.

Characters can also carry a trained LoRA (``lora = {name, weight, trigger}``,
the SwarmUI name relative to Models/Lora, e.g. ``SecondFloor/sf_nova``);
``conditioning_for_panel`` turns the ones on a panel into LoraConfigs plus
their trigger words, at 0.6 of the weight on multi-character panels.
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .core.config import DATA_DIR, LoraConfig

_CHARACTERS_FILE = DATA_DIR / "characters.json"


def _global_characters() -> List[Dict[str, Any]]:
    try:
        with open(_CHARACTERS_FILE, "r", encoding="utf-8") as f:
            chars = json.load(f)
    except Exception as e:
        logging.getLogger(__name__).debug("characters library unreadable: %s", e)
        return []
    return [c for c in chars if isinstance(c, dict)] if isinstance(chars, list) else []


def _global_blocks() -> Dict[str, str]:
    out = {}
    for c in _global_characters():
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


def resolve_locations(project: Dict[str, Any]) -> Dict[str, str]:
    """Project-scoped location library: ``settings.locations =
    [{name, prompt_block}]`` → {lowercase name -> prompt block}."""
    out = {}
    for loc in (project.get("settings") or {}).get("locations") or []:
        name = (loc.get("name") or "").strip()
        block = (loc.get("prompt_block") or "").strip()
        if name and block:
            out[name.lower()] = block
    return out


def location_block_for_panel(project: Dict[str, Any],
                             panel: Dict[str, Any]) -> str:
    """Prompt block for the panel's named location ("" when none matches)."""
    loc = (panel.get("location") or "").strip()
    if not loc:
        return ""
    return resolve_locations(project).get(loc.lower(), "")


# a LoRA's weight when the panel shows more than one person (several LoRAs at
# full weight fight each other and bleed faces across characters)
MULTI_CHARACTER_LORA_SCALE = 0.6


def lora_base_name(name: str) -> str:
    """"SecondFloor/sf_nova.safetensors" -> "SecondFloor/sf_nova"."""
    name = str(name or "").strip()
    return name[:-len(".safetensors")] if name.lower().endswith(".safetensors") else name


def default_trigger(name: str) -> str:
    """The trained LoRAs' convention: the file name without "_" (sf_nova -> sfnova)."""
    return lora_base_name(name).rsplit("/", 1)[-1].replace("_", "")


def normalize_lora(value: Any) -> Optional[Dict[str, Any]]:
    """A character's ``lora`` field -> {name, weight, trigger}, or None when unset.
    The weight defaults to 0.8; a missing trigger follows the name convention
    (an explicit empty trigger means none)."""
    if not isinstance(value, dict):
        return None
    name = lora_base_name(value.get("name") or "")
    if not name:
        return None
    try:
        weight = float(value.get("weight") if value.get("weight") is not None else 0.8)
    except (TypeError, ValueError):
        weight = 0.8
    trigger = value.get("trigger")
    trigger = default_trigger(name) if trigger is None else str(trigger).strip()
    return {"name": name, "weight": weight, "trigger": trigger}


def resolve_loras(project: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """{lowercase name -> lora} from the global library; a project entry
    (``settings.characters[].lora``) wins, as for prompt blocks."""
    out = {}
    entries = _global_characters() + list((project.get("settings") or {}).get("characters") or [])
    for c in entries:
        name = (c.get("name") or "").strip() if isinstance(c, dict) else ""
        lora = normalize_lora(c.get("lora")) if name else None
        if lora:
            out[name.lower()] = lora
    return out


def _panel_loras(project: Dict[str, Any], panel: Dict[str, Any]):
    """[(LoraConfig, trigger)] for the characters on a panel, in panel order."""
    names = [str(n).strip().lower() for n in panel.get("characters") or [] if str(n).strip()]
    scale = MULTI_CHARACTER_LORA_SCALE if len(names) > 1 else 1.0
    library = resolve_loras(project) if names else {}
    out = []
    for name in names:
        lora = library.get(name)
        if lora and not any(l.name == lora["name"] for l, _ in out):
            out.append((LoraConfig(name=lora["name"], weight=round(lora["weight"] * scale, 3)), lora["trigger"]))
    return out


def conditioning_for_panel(project: Dict[str, Any],
                           panel: Dict[str, Any]) -> Dict[str, Any]:
    """LoRAs and trigger words for the characters on a panel, in panel order:
    ``{"loras": [LoraConfig], "triggers": [str]}``. Full weight on a
    one-character panel, 0.6 of it when the panel lists more than one."""
    pairs = _panel_loras(project, panel)
    triggers: List[str] = []
    for _, t in pairs:
        if t and t not in triggers:
            triggers.append(t)
    return {"loras": [l for l, _ in pairs], "triggers": triggers}


def merge_loras(base: Optional[List[LoraConfig]],
                panel: List[LoraConfig]) -> Optional[List[LoraConfig]]:
    """Request/global LoRAs plus the panel characters', deduplicated by name;
    a panel character's weight wins over the same LoRA in ``base``."""
    if not panel:
        return base
    merged: Dict[str, LoraConfig] = {}
    for l in list(base or []) + list(panel):
        if l.name:
            merged[lora_base_name(l.name).lower()] = LoraConfig(name=l.name, weight=l.weight)
    return list(merged.values()) or None


def apply_conditioning(prompt: str, base_loras: Optional[List[LoraConfig]],
                       project: Dict[str, Any], panel: Dict[str, Any],
                       sep: str = ", "):
    """Add a panel's character LoRAs and trigger words to a generation:
    returns ``(prompt, loras, injected)``. A LoRA the prompt already tags
    (``<lora:name:w>``, e.g. a converted comic panel's) and a trigger word it
    already contains are left as they are."""
    low = prompt.lower()
    injected = []
    panel_loras = []
    for l, trigger in _panel_loras(project, panel):
        if f"<lora:{l.name.lower()}:" in low:
            continue
        panel_loras.append(l)
        if trigger and trigger.lower() not in low:
            prompt = f"{prompt}{sep}{trigger}" if prompt else trigger
            low = prompt.lower()
        injected.append({"kind": "lora", "text": f"<lora:{l.name}:{l.weight}>",
                         "name": l.name, "weight": l.weight, "trigger": trigger})
    return prompt, merge_loras(base_loras, panel_loras), injected
