"""Page assembly for the agent pipeline: template → page, slot filling,
auto dialogue bubbles. Deterministic, no LLM calls (the agent writes the
story; this module only lays it out)."""
import re
import uuid
from typing import Any, Dict, List, Tuple

ROW_BUCKET = 5.0    # % of page height; slots whose y falls in the same
                    # bucket are treated as one row for reading order


def split_dialogue(text: str, max_bubbles: int = 3) -> List[str]:
    """Split a panel's dialogue into bubble lines by newline and sentence
    punctuation, capped at max_bubbles (overflow merges into the last).
    Ellipsis runs (……/...) only break at the END of the run."""
    if not text or not text.strip():
        return []
    raw = [s.strip() for s in re.split(r"[\n]+", text) if s.strip()]
    out: List[str] = []
    for seg in raw:
        parts = [p for p in re.split(r"(?<=[。！？!?])(?!…)|(?<=…)(?!…)", seg)
                 if p.strip()]
        out.extend(parts)
    if len(out) > max_bubbles:
        out = out[: max_bubbles - 1] + ["".join(out[max_bubbles - 1:])]
    return out


def classify_bubble(text: str) -> str:
    if text.endswith(("！", "!")):
        return "shout"
    if "…" in text or "..." in text or text.startswith(("（", "(")):
        return "whisper"
    return "speech"


def build_page(spec: dict, project: dict) -> Tuple[dict, List[str]]:
    """spec: {template, name, panel_ids, reading, bubbles, dynamic}.
    Returns (page, warnings); does not persist."""
    warnings: List[str] = []
    elements, width, height = _resolve_template(spec.get("template") or {}, warnings)
    page = {"id": uuid.uuid4().hex, "name": spec.get("name") or "page",
            "templateId": (spec.get("template") or {}).get("id", ""),
            "width": width, "height": height, "order": 0, "elements": elements}
    for i, el in enumerate(page["elements"]):
        el.setdefault("id", uuid.uuid4().hex)
        el["zIndex"] = i
        el.setdefault("locked", False)
        el.setdefault("visible", True)

    panels = {p.get("id"): p for p in project.get("panels", [])}
    reading = spec.get("reading", "rtl")
    panel_ids = spec.get("panel_ids") or []

    # --- fill slots in reading order ---
    slots = [e for e in page["elements"] if e.get("type") == "image-slot"]
    slots.sort(key=lambda e: (round(e["y"] / ROW_BUCKET),
                              e["x"] if reading == "ltr" else -e["x"]))

    if spec.get("dynamic"):
        _apply_dynamic_corners([e for e in page["elements"]
                                if e.get("type") == "image-slot"])

    if len(panel_ids) > len(slots):
        warnings.append(f"{len(panel_ids) - len(slots)} panel(s) not placed: "
                        f"template has only {len(slots)} slots")
    for slot, pid in zip(slots, panel_ids):
        panel = panels.get(pid)
        if not panel:
            warnings.append(f"panel {pid} not found")
            continue
        if not panel.get("image"):
            warnings.append(f"panel {pid} has no image; slot kept empty")
            continue
        slot["type"] = "image"
        slot["src"] = panel["image"]

    # --- auto bubbles ---
    if (spec.get("bubbles") or {}).get("mode", "auto") != "none":
        z = max((e.get("zIndex", 0) for e in page["elements"]), default=0) + 1
        for slot, pid in zip(slots, panel_ids):
            panel = panels.get(pid)
            if not panel:
                continue
            for j, line in enumerate(split_dialogue(panel.get("dialogue") or "")):
                el = _make_bubble(line, slot, page, j,
                                  (spec.get("bubbles") or {}))
                if el:
                    el["zIndex"] = z
                    z += 1
                    page["elements"].append(el)
    return page, warnings


def _apply_dynamic_corners(slots: List[dict]) -> None:
    """Give the page a cinematic feel: slanted quadrilateral frames on all
    but the largest slot, cycling deterministic corner patterns (no RNG so
    rebuilds are reproducible). The hero (largest area, ties broken by page
    element order) stays rectangular."""
    if not slots:
        return
    patterns = [
        {"tl": (0, 4), "tr": (100, 0), "br": (100, 96), "bl": (0, 100)},
        {"tl": (0, 0), "tr": (97, 5), "br": (100, 100), "bl": (3, 95)},
        {"tl": (5, 0), "tr": (100, 6), "br": (95, 100), "bl": (0, 94)},
        {"tl": (0, 6), "tr": (100, 2), "br": (98, 100), "bl": (0, 100)},
    ]
    hero = max(slots, key=lambda e: e["width"] * e["height"])
    n = 0
    for slot in slots:
        if slot is hero or slot.get("corners"):
            continue
        p = patterns[n % len(patterns)]
        n += 1
        slot["corners"] = {k: {"x": v[0], "y": v[1]} for k, v in p.items()}


def _make_bubble(text: str, slot: dict, page: dict, seq: int,
                 opts: dict) -> dict:
    fs = opts.get("fontSize", 14)
    pad = 10
    fw, fh = slot["width"], slot["height"]
    vertical = bool(opts.get("vertical", True))
    if vertical:
        # Vertical layout: columns of chars run top-to-bottom, right-to-left.
        # Size so the text fits ~3 columns of balanced length.
        n_cols_target = 3
        chars_per_col = max(2, -(-len(text) // n_cols_target))
        bh_px = min(chars_per_col * fs * 1.3 + 2 * pad,
                    fh * page["height"] * 0.9)
        col_cap = max(1, int((bh_px - 2 * pad) // (fs * 1.3)))
        n_cols = max(1, -(-len(text) // col_cap))
        bw_px = n_cols * fs * 1.3 + 2 * pad
    else:
        # Horizontal: rows of chars sized by bubble width.
        bw_px = min(fw * page["width"] * 0.8, 0.30 * page["width"])
        cpl = max(4, int((bw_px - 2 * pad) / max(1.0, fs)))
        n_lines = -(-len(text) // cpl)                 # ceil
        bh_px = n_lines * fs * 1.4 + 2 * pad
    bw = min(bw_px / page["width"] * 100, fw * 0.95)
    bh = min(bh_px / page["height"] * 100, 40.0)
    x = slot["x"] + fw * 0.05 + (seq % 2) * (bw + 1.0)
    y = slot["y"] + fh * 0.04 + seq * (bh + 2.0)
    x = max(1.0, min(x, 99.0 - bw))
    y = max(1.0, min(y, 99.0 - bh))
    # tailPosition quirk (frontend parity): 'top' renders a triangle BELOW the
    # bubble's bottom edge pointing down — toward the character in the panel.
    return {"id": uuid.uuid4().hex, "type": "bubble",
            "bubbleType": classify_bubble(text), "text": text,
            "direction": "vertical" if vertical else "horizontal",
            "fontSize": fs, "backgroundColor": "#ffffff", "borderColor": "#000000",
            "tailPosition": "top",
            "x": round(x, 2), "y": round(y, 2),
            "width": round(bw, 2), "height": round(bh, 2),
            "rotation": 0, "locked": False, "visible": True}


def _resolve_template(ref: dict, warnings: List[str]) -> Tuple[List[dict], int, int]:
    kind = ref.get("kind", "builtin")
    if kind == "builtin":
        from .composer_builtins import get_template
        t = get_template(ref.get("id", ""))
        if not t:
            raise ValueError(f"builtin template not found: {ref.get('id')}")
        return [dict(e) for e in t["elements"]], t["width"], t["height"]
    if kind == "user":
        from .api.composer_templates import _load
        t = next((x for x in _load() if x.get("id") == ref.get("id")), None)
        if not t:
            raise ValueError(f"user template not found: {ref.get('id')}")
        return [dict(e) for e in t["elements"]], t.get("width", 600), t.get("height", 900)
    if kind == "rows":
        from .composer_builtins import gen_rows
        els = gen_rows(ref.get("rows", [1]), ref.get("margin", 2), ref.get("gap", 2))
        return els, 600, 900
    if kind == "custom":
        return [dict(e) for e in ref.get("elements", [])], \
            ref.get("width", 600), ref.get("height", 900)
    raise ValueError(f"unknown template kind: {kind}")
