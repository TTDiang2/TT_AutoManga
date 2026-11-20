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

A character with a sheet (``image``) and ``refWeight`` > 0 also guides its
SOLO panels through SwarmUI's IP-Adapter: ``reference_for_panel`` returns
the sheet as a data URL plus the weight, and ``ipadapter_args`` turns that
into ``generate_image`` keywords (preset, weight type and end step from
settings.swarmui.ipadapterPreset / ipadapterWeightType / ipadapterEnd).
A missing or 0 refWeight is off — the reference is an explicit opt-in.
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


# tags that claim a picture shows one person: wrong in a block injected into a
# panel with several characters ("1boy, solo" + "1girl, solo" makes the model
# merge the two people into one)
_SOLO_TAGS = {"solo", "solo focus"}


def _without_solo(block: str) -> str:
    parts = [p.strip() for p in block.split(",")]
    kept = [p for p in parts if p.lower() not in _SOLO_TAGS]
    return ", ".join(p for p in kept if p) if len(kept) != len(parts) else block


def blocks_for_panel(project: Dict[str, Any], panel: Dict[str, Any]) -> List[str]:
    """Prompt blocks for the characters listed on a panel, in panel order.
    On a panel with several characters, ``solo`` tags are dropped from them."""
    blocks = resolve_blocks(project)
    names = [str(n).strip() for n in panel.get("characters") or [] if str(n).strip()]
    several = len({n.lower() for n in names}) > 1
    out = []
    for name in names:
        block = blocks.get(name.lower())
        if block:
            block = _without_solo(block) if several else block
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


def normalize_ref_weight(value: Any) -> float:
    """A character's ``refWeight`` -> 0..1 (missing, invalid or <= 0: 0 = off)."""
    try:
        w = float(value)
    except (TypeError, ValueError):
        return 0.0
    if w != w or w <= 0:   # NaN or off
        return 0.0
    return round(min(w, 1.0), 3)


def _image_dataurl(ref: Any) -> Optional[str]:
    """A sheet ref as a data URL: data: URLs as they are, managed assets
    (/api/assets/file/<id>) read from the asset store; nothing else (an
    arbitrary path would be a local-file read)."""
    ref = str(ref or "")
    if ref.startswith("data:"):
        return ref
    if ref.startswith("/api/assets/file/"):
        try:
            import base64
            from .storage.asset_store import asset_store
            path = asset_store.path_for(ref.rsplit("/", 1)[-1])
            if not path:
                return None
            mime = {".png": "image/png", ".webp": "image/webp",
                    ".gif": "image/gif"}.get(path.suffix.lower(), "image/jpeg")
            return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()
        except Exception as e:
            logging.getLogger(__name__).debug("sheet asset unreadable: %s", e)
    return None


def resolve_refs(project: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """{lowercase name -> {"image": ref, "weight": w}} for characters with a
    sheet and refWeight > 0. A project entry (``settings.characters[]``)
    overrides the library's ``refWeight`` / ``image`` when it sets them."""
    out: Dict[str, Dict[str, Any]] = {}
    entries = _global_characters() + list((project.get("settings") or {}).get("characters") or [])
    for c in entries:
        if not isinstance(c, dict):
            continue
        name = (c.get("name") or "").strip().lower()
        if not name:
            continue
        cur = dict(out.get(name) or {})
        if c.get("image"):
            cur["image"] = c["image"]
        if "refWeight" in c:
            cur["weight"] = normalize_ref_weight(c.get("refWeight"))
        out[name] = cur
    return {k: v for k, v in out.items() if v.get("image") and v.get("weight", 0) > 0}


def reference_for_panel(project: Dict[str, Any],
                        panel: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The character sheet guiding a SOLO panel: ``{"name", "image" (data
    URL), "weight"}``, or None (no or several characters, refWeight off, or
    the sheet can't be read). Several people would get one blended face."""
    names = [str(n).strip() for n in panel.get("characters") or [] if str(n).strip()]
    if len({n.lower() for n in names}) != 1:
        return None
    ref = resolve_refs(project).get(names[0].lower())
    image = _image_dataurl(ref["image"]) if ref else None
    if not image:
        return None
    return {"name": names[0], "image": image, "weight": ref["weight"]}


def ipadapter_args(reference: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """``generate_image`` keywords for a panel reference ({} when none)."""
    if not reference:
        return {}
    from .core.config import settings
    preset = (settings.swarmui.ipadapterPreset or "").strip()
    if not preset or preset == "None":
        return {}
    out = {"prompt_images": [reference["image"]], "ipadapter": preset,
           "ipadapter_weight": reference["weight"]}
    if settings.swarmui.ipadapterWeightType:
        out["ipadapter_weight_type"] = settings.swarmui.ipadapterWeightType
    if settings.swarmui.ipadapterEnd and 0 < settings.swarmui.ipadapterEnd < 1:
        out["ipadapter_end"] = settings.swarmui.ipadapterEnd
    return out


def conditioning_for_panel(project: Dict[str, Any],
                           panel: Dict[str, Any]) -> Dict[str, Any]:
    """LoRAs, trigger words and the sheet reference for the characters on a
    panel, in panel order: ``{"loras": [LoraConfig], "triggers": [str],
    "reference": {name, image, weight} | None}``. Full LoRA weight on a
    one-character panel, 0.6 of it when the panel lists more than one; the
    reference only on one-character panels."""
    pairs = _panel_loras(project, panel)
    triggers: List[str] = []
    for _, t in pairs:
        if t and t not in triggers:
            triggers.append(t)
    return {"loras": [l for l, _ in pairs], "triggers": triggers,
            "reference": reference_for_panel(project, panel)}


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
