"""Agent orchestration API (/api/agent/*).

The machine-facing half of the pipeline: project/panel CRUD, image
generation (single + batch jobs), page assembly, element-level editing,
server-side preview and export. Contract documented in AGENTS.md (Phase 5)
and the plan docs.
"""
import asyncio
import base64
import io
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from PIL import Image

from ..assembly import build_page
from ..core.config import settings, is_masked_api_key
from ..core.openai_client import client as llm_client
from ..core.swarmui_client import swarm_client
from ..jobs import create_job, job_snapshot, run_job
from ..render import render_page
from ..render.export_service import export_pages
from ..render.resolve import make_resolver
from ..storage.asset_store import asset_store
from ..storage.manager import storage, InvalidProjectIdError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agent"])
_resolver = make_resolver(asset_store)

EXPORTS_DIR = None  # resolved lazily to reuse api.export's directory


def _exports_dir():
    global EXPORTS_DIR
    if EXPORTS_DIR is None:
        from .export import EXPORTS_DIR as d
        EXPORTS_DIR = d
    return EXPORTS_DIR


# ---------------------------------------------------------------------------
# Projects & panels
# ---------------------------------------------------------------------------

class CreateProjectRequest(BaseModel):
    name: str
    panels: List[Dict[str, Any]] = []


def _ensure_panel_ids(panels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Fill missing ids as panel_1..panel_n; never collide within the batch."""
    used = {p.get("id") for p in panels if p.get("id")}
    n = 0
    for p in panels:
        if not p.get("id"):
            n += 1
            while f"panel_{n}" in used:
                n += 1
            p["id"] = f"panel_{n}"
            used.add(p["id"])
    return panels


def _validate_panels(panels: List[Dict[str, Any]]) -> None:
    seen = set()
    for p in panels:
        pid = p.get("id")
        if pid:
            if pid in seen:
                raise HTTPException(status_code=400,
                                    detail=f"duplicate panel id: {pid}")
            seen.add(pid)
        if not (p.get("scene") or "").strip():
            raise HTTPException(status_code=400,
                                detail="every panel needs a non-empty scene")
        if p.get("shot") is not None and p["shot"] not in _SHOT_TAGS:
            raise HTTPException(
                status_code=400,
                detail=f"shot must be one of {sorted(_SHOT_TAGS)}")


def _project_stats(project: Dict[str, Any]) -> Dict[str, Any]:
    panels = project.get("panels", [])
    pages = project.get("composerPages", [])
    used_srcs = set()
    for page in pages:
        for el in page.get("elements", []):
            if el.get("type") in ("image", "page-image") and el.get("src"):
                used_srcs.add(el["src"])
    with_image = [p for p in panels if p.get("image")]
    return {
        "panels": len(panels),
        "panels_with_image": len(with_image),
        "pages": len(pages),
        "panels_missing_image": [p["id"] for p in panels if not p.get("image")],
        "panels_missing_page": [p["id"] for p in with_image
                                if p.get("image") not in used_srcs],
    }


def _load_or_404(project_id: str) -> Dict[str, Any]:
    try:
        project = storage.load_project(project_id)
    except InvalidProjectIdError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("/projects")
async def create_project(req: CreateProjectRequest):
    project = {"name": req.name or "untitled", "panels": req.panels,
               "settings": {}, "composerPages": []}
    _ensure_panel_ids(project["panels"])
    _validate_panels(project["panels"])
    saved = storage.save_project(project)
    return {"project": saved}


@router.get("/projects")
async def list_projects():
    out = []
    for p in storage.list_projects():
        out.append({"id": p.get("id"), "name": p.get("name"),
                    "updatedAt": p.get("updatedAt"),
                    "stats": _project_stats(p)})
    return {"projects": out}


@router.get("/projects/{project_id}")
async def get_project(project_id: str):
    project = _load_or_404(project_id)
    return {"project": project, "stats": _project_stats(project)}


class PutPanelsRequest(BaseModel):
    panels: List[Dict[str, Any]]


@router.put("/projects/{project_id}/panels")
async def put_panels(project_id: str, req: PutPanelsRequest):
    project = _load_or_404(project_id)
    _ensure_panel_ids(req.panels)
    _validate_panels(req.panels)
    project["panels"] = req.panels
    saved = storage.save_project(project)
    return {"success": True, "panels": saved["panels"]}


@router.patch("/projects/{project_id}/panels/{panel_id}")
async def patch_panel(project_id: str, panel_id: str, updates: Dict[str, Any]):
    project = _load_or_404(project_id)
    updates = dict(updates)
    if "id" in updates and updates["id"] != panel_id:
        raise HTTPException(status_code=400, detail="cannot change panel id")
    updates.pop("id", None)
    if updates.get("shot") is not None and updates["shot"] not in _SHOT_TAGS:
        raise HTTPException(
            status_code=400,
            detail=f"shot must be one of {sorted(_SHOT_TAGS)}")
    if "scene" in updates and not (updates["scene"] or "").strip():
        raise HTTPException(status_code=400, detail="scene cannot be empty")
    for panel in project.get("panels", []):
        if panel.get("id") == panel_id:
            panel.update(updates)
            saved = storage.save_project(project)
            target = next(p for p in saved["panels"] if p["id"] == panel_id)
            return {"success": True, "panel": target}
    raise HTTPException(status_code=404, detail="Panel not found")


class StoryboardRequest(BaseModel):
    project_id: str
    text: str
    detail_level: int = 3
    replace: bool = True
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None


@router.post("/storyboard")
async def agent_storyboard(req: StoryboardRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    project = _load_or_404(req.project_id)

    llm_client.reload_from_settings()
    if req.endpoint:
        llm_client.update_config(endpoint=req.endpoint)
    # skip the masked echo clients may send back from GET /api/settings/
    if req.api_key is not None and not is_masked_api_key(req.api_key):
        llm_client.update_config(api_key=req.api_key)
    if req.model:
        llm_client.update_config(model=req.model)

    result = await llm_client.generate_storyboard(req.text, req.detail_level)
    if result.get("error"):
        raise HTTPException(status_code=502,
                            detail=f"LLM: {result['error']}")
    panels = result.get("panels") or []
    if not panels:
        raise HTTPException(status_code=502, detail="LLM returned no panels")

    if not req.replace:
        for p in project.get("panels", []):
            panels.append(p)
    _ensure_panel_ids(panels)
    _validate_panels(panels)
    project["panels"] = panels
    saved = storage.save_project(project)
    return {"panels": saved["panels"]}


# ---------------------------------------------------------------------------
# Image generation (single + batch)
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    project_id: Optional[str] = None
    panel_id: Optional[str] = None
    prompt: str
    negative_prompt: str = ""
    width: Optional[int] = None
    height: Optional[int] = None
    steps: Optional[int] = None
    cfg_scale: Optional[float] = None
    seed: Optional[int] = None
    remove_background: bool = False
    variants: int = 1                  # 1-4
    apply_variant: int = 0             # which variant (0-based) binds to the panel
    apply_to_panel: bool = True
    kind: str = "panel"                # panel | overlay | character
    # --- per-request overrides (fall back to global settings) ---
    model: Optional[str] = None
    loras: Optional[List[Dict[str, Any]]] = None
    prompt_format: Optional[str] = None   # danbooru | prose | None (meta only)
    # --- img2img ---
    init_image: Optional[str] = None      # asset URL / data URL
    init_creativity: Optional[float] = None
    # --- automatic prompt injection (project style + character blocks) ---
    inject_characters: bool = True


def _ref_to_dataurl(ref: str) -> Optional[str]:
    """Load an image ref as a data URL. Only data: URLs and managed assets
    are accepted — an arbitrary filesystem path here would be an
    unauthenticated local-file read primitive."""
    try:
        if ref.startswith("data:"):
            return ref
        if ref.startswith("/api/assets/file/"):
            path = asset_store.path_for(ref.rsplit("/", 1)[-1])
            if not path:
                return None
            import base64 as b64mod
            mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
            return f"data:{mime};base64," + b64mod.b64encode(path.read_bytes()).decode()
        return None
    except Exception:
        return None


async def _do_generate(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Core single-request generation shared by /generate and /generate-batch."""
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("prompt is required")
    variants = max(1, min(4, int(payload.get("variants") or 1)))
    apply_variant = int(payload.get("apply_variant") or 0)
    if not (0 <= apply_variant < variants):
        raise ValueError(f"apply_variant must be 0-{variants - 1}")
    seed = payload.get("seed")
    swarm_settings = settings.swarmui

    # per-request overrides fall back to global settings
    model = payload.get("model") or swarm_settings.currentModel or None
    lora_payload = payload.get("loras")
    if lora_payload:
        from ..core.config import LoraConfig
        loras = [LoraConfig(name=l.get("name", ""), weight=l.get("weight", 1.0))
                 for l in lora_payload if l.get("name")]
    elif swarm_settings.currentLoras:
        # settings loras are LoraConfig models already (put_agent_settings
        # normalizes) — copy as-is, never dict-style .get() on them
        loras = [l for l in swarm_settings.currentLoras if l.name]
    else:
        loras = None

    init_dataurl = None
    if payload.get("init_image"):
        init_dataurl = _ref_to_dataurl(payload["init_image"])
        if init_dataurl is None:
            raise ValueError(f"init_image not found: {payload['init_image']}")

    # automatic injection: project style suffix + character blocks
    injected = []
    project = None
    if payload.get("project_id"):
        project = storage.load_project(payload["project_id"])
    if payload.get("inject_characters", True) and project:
        from ..prompting import blocks_for_panel, style_suffix
        style = style_suffix(project)
        if style:
            prompt = f"{prompt}, {style}" if prompt_format_is_tags(payload) else f"{prompt}。{style}"
            injected.append({"kind": "style", "text": style})
        panel = None
        if payload.get("panel_id"):
            panel = next((p for p in (project.get("panels") or [])
                          if p.get("id") == payload["panel_id"]), None)
        if panel:
            shot = panel.get("shot")
            if shot:
                extra = _SHOT_TAGS[shot][0 if prompt_format_is_tags(payload) else 1]
                prompt = f"{prompt}, {extra}" if prompt_format_is_tags(payload) else f"{prompt}。{extra}"
                injected.append({"kind": "shot", "text": extra})
            for block in blocks_for_panel(project, panel):
                prompt = f"{prompt}, {block}" if prompt_format_is_tags(payload) else f"{prompt}。{block}"
                injected.append({"kind": "character", "text": block})

    assets_out = []
    for v in range(variants):
        result = await swarm_client.generate_image(
            prompt=prompt,
            negative_prompt=payload.get("negative_prompt") or "",
            model=model,
            steps=payload.get("steps") or swarm_settings.currentSteps,
            cfg_scale=payload.get("cfg_scale") or swarm_settings.currentCfgScale,
            width=payload.get("width") or swarm_settings.currentWidth,
            height=payload.get("height") or swarm_settings.currentHeight,
            sampler_name=swarm_settings.currentSamplerName,
            loras=loras,
            seed=(seed + v) if seed is not None else None,
            remove_background=bool(payload.get("remove_background")),
            init_image=init_dataurl,
            init_creativity=payload.get("init_creativity"),
        )
        if not result.get("success"):
            raise RuntimeError(f"SwarmUI: {result.get('error', 'unknown error')}")
        img_bytes = base64.b64decode(result["image"].split(",", 1)[1])

        # transparent-background fallback when SwarmUI's remover is broken
        alpha_method = "swarmui"
        if payload.get("remove_background"):
            from ..render.alpha_fallback import ensure_alpha
            img_bytes, alpha_method = ensure_alpha(img_bytes)

        img = Image.open(io.BytesIO(img_bytes))
        has_alpha = (img.mode == "RGBA"
                     and img.getchannel("A").getextrema()[0] < 255)
        dataurl = "data:image/png;base64," + base64.b64encode(img_bytes).decode()
        entry = asset_store.save_dataurl(
            dataurl,
            project_id=payload.get("project_id") or None,
            kind=payload.get("kind") or "panel",
            meta={"prompt": prompt, "seed": (seed + v) if seed is not None else None,
                  "remove_background": bool(payload.get("remove_background")),
                  "alpha_method": alpha_method if payload.get("remove_background") else None,
                  "width": img.size[0], "height": img.size[1],
                  "has_alpha": has_alpha, "model": model,
                  "prompt_format": payload.get("prompt_format"),
                  "injected": injected},
        )
        assets_out.append({
            "asset_id": entry["asset_id"],
            "url": asset_store.url_for(entry["asset_id"]),
            "width": img.size[0], "height": img.size[1],
            "has_alpha": has_alpha,
            "alpha_method": alpha_method if payload.get("remove_background") else None,
        })

    applied = False
    if payload.get("apply_to_panel", True) and payload.get("panel_id") \
            and payload.get("project_id"):
        panel = next((p for p in (project or {}).get("panels", [])
                      if p.get("id") == payload["panel_id"]), None) \
            if project else None
        if panel is None:
            raise ValueError(f"panel {payload['panel_id']} not found in "
                             f"project {payload['project_id']}")
        from .assets import _save_panel_image
        _save_panel_image(payload["project_id"], payload["panel_id"],
                          assets_out[apply_variant]["url"])
        applied = True
    return {"assets": assets_out, "applied": applied,
            "model": model, "injected": injected}


# camera-shot descriptors injected into prompts when a panel declares a shot
_SHOT_TAGS = {
    "wide": ("wide shot, scenic view, full scenery", "全景远景，展现完整环境"),
    "medium": ("medium shot, waist up", "中景，半身构图"),
    "close-up": ("close-up, face focus", "近景特写，聚焦面部"),
    "extreme-close-up": ("extreme close-up, macro detail", "极致特写，放大细节"),
    "splash": ("splash illustration, dramatic composition, dynamic angle",
               "整页大画面，戏剧性构图，充满张力"),
}


def prompt_format_is_tags(payload: Dict[str, Any]) -> bool:
    """Injection separator: danbooru-style prompts join with ', ', prose joins
    with '。'. Unspecified formats default to the tag style."""
    return (payload.get("prompt_format") or "danbooru") != "prose"


@router.post("/generate")
async def agent_generate(req: GenerateRequest):
    logger.info("agent/generate prompt_len=%d variants=%d rm_bg=%s panel=%s",
                len(req.prompt), req.variants, req.remove_background,
                req.panel_id)
    try:
        return await _do_generate(req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


class GenerateBatchRequest(BaseModel):
    project_id: Optional[str] = None
    concurrency: int = 1
    jobs: List[GenerateRequest]


# Strong references to running batch jobs (asyncio GC protection)
_background_tasks = set()


@router.post("/generate-batch")
async def agent_generate_batch(req: GenerateBatchRequest):
    if not req.jobs:
        raise HTTPException(status_code=400, detail="No jobs provided")
    payloads = []
    for j in req.jobs:
        p = j.model_dump()
        if req.project_id and not p.get("project_id"):
            p["project_id"] = req.project_id
        payloads.append(p)
    job = create_job(payloads, req.concurrency)
    task = asyncio.create_task(run_job(job.id, _do_generate))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=202,
                        content={"job_id": job.id, "total": job.total})


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    snap = job_snapshot(job_id)
    if not snap:
        raise HTTPException(status_code=404, detail="Job not found")
    return snap


@router.get("/models")
async def list_models():
    """Installed SwarmUI models with architecture metadata, for per-request
    model selection. See the prompt-format guide in AGENTS.md."""
    models = await swarm_client.list_models()
    if not models:
        return {"models": [], "error": "SwarmUI unreachable or no models found"}
    return {"models": models}


@router.get("/templates")
async def list_templates():
    """All build-page templates (builtin + dynamic presets), so agents can
    discover slot counts instead of relying on the AGENTS.md list."""
    from ..composer_builtins import TEMPLATES, DYNAMIC_TEMPLATES

    def brief(t: dict, dynamic: bool) -> dict:
        return {"id": t["id"], "name": t["name"],
                "nameZh": t.get("nameZh", ""),
                "width": t.get("width", 600), "height": t.get("height", 900),
                "slots": sum(1 for e in t["elements"]
                             if e.get("type") == "image-slot"),
                "dynamic": dynamic}

    return {
        "templates": [brief(t, False) for t in TEMPLATES]
                      + [brief(t, True) for t in DYNAMIC_TEMPLATES],
        "other_kinds": {
            "rows": '{"kind":"rows","rows":[2,3]} — n columns per row',
            "custom": '{"kind":"custom","elements":[...],"width":600,"height":900}',
            "user": '{"kind":"user","id":...} — list via GET /api/composer-templates',
        },
    }


@router.get("/assets/{asset_id}")
async def get_asset(asset_id: str):
    """Generation-time metadata for one asset (prompt, seed, model, alpha
    method...) — the agent's memory when it needs to reproduce or tweak."""
    entry = asset_store.get(asset_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Asset not found")
    return {"asset": entry,
            "url": asset_store.url_for(asset_id),
            "file_exists": Path(entry.get("path", "")).is_file()}


def _swarm_view() -> Dict[str, Any]:
    sw = settings.swarmui
    return {"address": sw.address,
            "currentModel": sw.currentModel,
            "currentSteps": sw.currentSteps,
            "currentCfgScale": sw.currentCfgScale,
            "currentWidth": sw.currentWidth,
            "currentHeight": sw.currentHeight,
            "currentSamplerName": sw.currentSamplerName,
            "promptSuffix": sw.promptSuffix,
            "currentLoras": [l.model_dump() for l in sw.currentLoras]}


@router.get("/settings")
async def get_agent_settings():
    """Effective generation defaults /generate falls back to."""
    return {"swarmui": _swarm_view()}


class AgentSettingsUpdate(BaseModel):
    currentModel: Optional[str] = None
    currentSteps: Optional[int] = None
    currentCfgScale: Optional[float] = None
    currentWidth: Optional[int] = None
    currentHeight: Optional[int] = None
    currentSamplerName: Optional[str] = None
    promptSuffix: Optional[str] = None
    currentLoras: Optional[List[Dict[str, Any]]] = None


_INT_RANGES = {"currentSteps": (1, 150),
               "currentWidth": (64, 4096),
               "currentHeight": (64, 4096)}


@router.put("/settings")
async def put_agent_settings(req: AgentSettingsUpdate):
    """Update generation defaults (same fields the UI Settings tab edits).
    Takes effect on the next /generate call and persists to settings.json."""
    data = req.model_dump(exclude_none=True)
    for field, (lo, hi) in _INT_RANGES.items():
        if field in data and not (lo <= data[field] <= hi):
            raise HTTPException(status_code=400,
                                detail=f"{field} must be {lo}-{hi}")
    if "currentWidth" in data and data["currentWidth"] % 8:
        raise HTTPException(status_code=400,
                            detail="currentWidth must be a multiple of 8")
    if "currentHeight" in data and data["currentHeight"] % 8:
        raise HTTPException(status_code=400,
                            detail="currentHeight must be a multiple of 8")
    if "currentCfgScale" in data and not (0 <= data["currentCfgScale"] <= 30):
        raise HTTPException(status_code=400,
                            detail="currentCfgScale must be 0-30")
    if "currentLoras" in data:
        for l in data["currentLoras"]:
            if not isinstance(l.get("name"), str) or not l["name"].strip():
                raise HTTPException(status_code=400,
                                    detail="each lora needs a non-empty name")
            w = l.get("weight", 1.0)
            if not isinstance(w, (int, float)) or not (0 <= w <= 2):
                raise HTTPException(status_code=400,
                                    detail="lora weight must be 0-2")

    sw = settings.swarmui
    for k, v in data.items():
        if k == "currentLoras":
            from ..core.config import LoraConfig
            setattr(sw, k, [LoraConfig(name=l["name"],
                                       weight=float(l.get("weight", 1.0)))
                            for l in v])
        else:
            setattr(sw, k, v)

    from ..core.config import save_settings
    save_settings(settings)
    return {"success": True, "swarmui": _swarm_view()}


class ProjectSettingsUpdate(BaseModel):
    style: Optional[str] = None
    characters: Optional[List[Dict[str, Any]]] = None   # [{name, prompt_block}]
    bible: Optional[str] = None   # free-text story bible: worldview, recap,
                                  # established locations/props — for the
                                  # agent's own continuity across chapters


@router.put("/projects/{project_id}/settings")
async def put_project_settings(project_id: str, req: ProjectSettingsUpdate):
    """Project-level style profile (appended to every panel prompt) and
    character prompt blocks (injected for panels listing that character)."""
    project = _load_or_404(project_id)
    cfg = project.setdefault("settings", {})
    if req.style is not None:
        cfg["style"] = req.style.strip()
    if req.bible is not None:
        cfg["bible"] = req.bible.strip()
    if req.characters is not None:
        for c in req.characters:
            if not isinstance(c.get("name"), str) or not c["name"].strip()                     or not isinstance(c.get("prompt_block"), str) or not c["prompt_block"].strip():
                raise HTTPException(status_code=400,
                                    detail="each character needs name and prompt_block")
        cfg["characters"] = req.characters
    saved = storage.save_project(project)
    return {"success": True, "settings": saved.get("settings", {})}


@router.get("/projects/{project_id}/characters")
async def get_project_characters(project_id: str):
    """Effective character prompt blocks (project entries override the global
    character library) — what /generate would inject for each name."""
    project = _load_or_404(project_id)
    from ..prompting import resolve_blocks
    return {"blocks": resolve_blocks(project)}


# ---------------------------------------------------------------------------
# Page assembly
# ---------------------------------------------------------------------------

class BuildPageRequest(BaseModel):
    template: dict
    name: Optional[str] = None
    panel_ids: List[str] = []
    reading: str = "rtl"            # rtl | ltr
    bubbles: dict = {}              # {mode: auto|none, fontSize, vertical}
    dynamic: bool = False           # slant/deform frames for a cinematic feel
    dry_run: bool = False


@router.post("/projects/{project_id}/pages")
async def build_page_endpoint(project_id: str, req: BuildPageRequest):
    project = _load_or_404(project_id)
    try:
        page, warnings = build_page(req.model_dump(exclude={"dry_run"}),
                                    project)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    saved = False
    if not req.dry_run:
        pages = project.setdefault("composerPages", [])
        page["order"] = len(pages)
        pages.append(page)
        storage.save_project(project)
        saved = True
    return {"page": page, "warnings": warnings, "saved": saved}


@router.get("/projects/{project_id}/pages/{page_id}")
async def get_page(project_id: str, page_id: str):
    project = _load_or_404(project_id)
    return {"page": _find_page(project, page_id)}


@router.delete("/projects/{project_id}/pages/{page_id}")
async def delete_page(project_id: str, page_id: str):
    project = _load_or_404(project_id)
    pages = project.get("composerPages", [])
    for i, page in enumerate(pages):
        if page.get("id") == page_id:
            pages.pop(i)
            for j, q in enumerate(pages):   # keep order contiguous
                q["order"] = j
            storage.save_project(project)
            return {"success": True, "pages_remaining": len(pages)}
    raise HTTPException(status_code=404, detail="Page not found")


# exact slot-count match preferred, next larger accepted (extra slots stay
# empty placeholders and render nothing)
_PLAN_TEMPLATES = {1: "hero-splash", 2: "manga-2h", 3: "manga-3", 4: "manga-4",
                   5: "dyn-5-mix", 6: "manga-6", 8: "manga-8"}


def _plan_template(count: int) -> str:
    if count in _PLAN_TEMPLATES:
        return _PLAN_TEMPLATES[count]
    larger = [n for n in _PLAN_TEMPLATES if n > count]
    return _PLAN_TEMPLATES[min(larger)] if larger else "manga-8"


class PlanPagesRequest(BaseModel):
    panels_per_page: int = 4         # 1-8
    splash_panel_ids: List[str] = [] # forced solo splash pages
    only_with_image: bool = True     # skip panels that have no art yet
    reading: str = "rtl"
    bubbles: dict = {}
    dynamic: bool = False
    apply: bool = False              # execute the plan with build_page


@router.post("/projects/{project_id}/plan-pages")
async def plan_pages(project_id: str, req: PlanPagesRequest):
    """Heuristic pagination: chunk panels into pages (page = the narrative
    unit of manga), splash panels get a solo page, template picked by slot
    count. Pure planning unless apply=true."""
    project = _load_or_404(project_id)
    ppp = max(1, min(8, req.panels_per_page))
    splash = set(req.splash_panel_ids)

    chosen = [p for p in project.get("panels", [])
              if not req.only_with_image or p.get("image")]
    groups: List[List[str]] = []
    group: List[str] = []
    for p in chosen:
        pid = p.get("id")
        if p.get("shot") == "splash" or pid in splash:
            if group:
                groups.append(group)
                group = []
            groups.append([pid])
        else:
            group.append(pid)
            if len(group) >= ppp:
                groups.append(group)
                group = []
    if group:
        groups.append(group)

    plan = [{"index": i + 1, "name": f"p{i + 1}",
             "panel_ids": g,
             "template": {"kind": "builtin", "id": _plan_template(len(g))}}
            for i, g in enumerate(groups)]

    pages_added = 0
    if req.apply and plan:
        for entry in plan:
            page, _warnings = build_page(
                {"template": entry["template"], "name": entry["name"],
                 "panel_ids": entry["panel_ids"], "reading": req.reading,
                 "bubbles": req.bubbles, "dynamic": req.dynamic},
                project)
            pages = project.setdefault("composerPages", [])
            page["order"] = len(pages)
            pages.append(page)
            entry["page_id"] = page["id"]
            pages_added += 1
        storage.save_project(project)
    return {"plan": plan, "applied": req.apply, "pages_added": pages_added}


class CoverRequest(BaseModel):
    title: str
    subtitle: Optional[str] = None
    asset_url: Optional[str] = None    # /api/assets/file/... or data: URL
    panel_id: Optional[str] = None     # reuse an existing panel's image
    title_color: str = "#ffffff"
    font_size: int = 64


@router.post("/projects/{project_id}/cover")
async def build_cover(project_id: str, req: CoverRequest):
    """Assemble a cover page (full-bleed art + outlined title) and insert it
    as page 1. Generate the art first via /generate kind=\"cover\"."""
    if not req.title.strip():
        raise HTTPException(status_code=400, detail="title is required")
    project = _load_or_404(project_id)
    src = None
    if req.asset_url:
        if not (req.asset_url.startswith("/api/assets/file/")
                or req.asset_url.startswith("data:")):
            raise HTTPException(status_code=400,
                                detail="asset_url must be an asset URL or data: URL")
        src = req.asset_url
    elif req.panel_id:
        panel = next((p for p in project.get("panels", [])
                      if p.get("id") == req.panel_id), None)
        if panel is None:
            raise HTTPException(status_code=404, detail="Panel not found")
        src = panel.get("image")
        if not src:
            raise HTTPException(status_code=400,
                                detail="panel has no image to use as cover art")
    else:
        raise HTTPException(status_code=400,
                            detail="asset_url or panel_id is required")

    els: List[Dict[str, Any]] = [{
        "id": uuid.uuid4().hex, "type": "image", "src": src,
        "x": 0, "y": 0, "width": 100, "height": 100, "rotation": 0,
        "zIndex": 0, "locked": False, "visible": True, "frameBorderWidth": 0,
    }, {
        "id": uuid.uuid4().hex, "type": "text", "content": req.title.strip(),
        "x": 8, "y": 6, "width": 84, "height": 16, "rotation": 0,
        "zIndex": 1, "locked": False, "visible": True,
        "fontSize": req.font_size, "fontFamily": "", "color": req.title_color,
        "direction": "horizontal", "fontWeight": "bold", "textAlign": "center",
        "strokeWidth": 6, "strokeColor": "#000000",
    }]
    if req.subtitle and req.subtitle.strip():
        els.append({
            "id": uuid.uuid4().hex, "type": "text",
            "content": req.subtitle.strip(),
            "x": 12, "y": 23, "width": 76, "height": 8, "rotation": 0,
            "zIndex": 2, "locked": False, "visible": True,
            "fontSize": max(12, int(req.font_size * 0.4)), "fontFamily": "",
            "color": req.title_color, "direction": "horizontal",
            "fontWeight": "normal", "textAlign": "center",
            "strokeWidth": 3, "strokeColor": "#000000",
        })
    page = {"id": uuid.uuid4().hex, "name": "cover", "templateId": "cover",
            "width": 600, "height": 900, "order": 0, "elements": els}
    pages = project.setdefault("composerPages", [])
    for p in pages:
        p["order"] = p.get("order", 0) + 1
    pages.insert(0, page)
    storage.save_project(project)
    return {"page": page}


# curated onomatopoeia for the SFX text tool (zh / ja / en)
_SFX_PRESETS = [
    {"word": "轰", "meaning": "爆炸、引擎"}, {"word": "砰", "meaning": "撞击"},
    {"word": "咔嚓", "meaning": "断裂、快门"}, {"word": "咚", "meaning": "重击、心跳"},
    {"word": "唰", "meaning": "快速掠过"}, {"word": "啪", "meaning": "拍击"},
    {"word": "哗啦", "meaning": "水流、散落"}, {"word": "扑通", "meaning": "落水"},
    {"word": "滴答", "meaning": "钟表"}, {"word": "嘶", "meaning": "撕裂、嘶鸣"},
    {"word": "ざっ", "meaning": "斩击"}, {"word": "どん", "meaning": "轰响"},
    {"word": "ごごご", "meaning": "轰鸣渐进"}, {"word": "ドキッ", "meaning": "心跳"},
    {"word": "BOOM", "meaning": "explosion"}, {"word": "WHOOSH", "meaning": "fast movement"},
    {"word": "CRACK", "meaning": "impact"}, {"word": "THUD", "meaning": "heavy hit"},
]


@router.get("/sfx-presets")
async def sfx_presets():
    return {"presets": _SFX_PRESETS,
            "default_style": {"fontSize": 48, "rotation": -8,
                              "strokeWidth": 4, "strokeColor": "#000000",
                              "color": "#ffffff", "fontWeight": "bold",
                              "textAlign": "center"}}


class ReorderPagesRequest(BaseModel):
    page_ids: List[str]    # full desired order; must be a permutation


@router.put("/projects/{project_id}/pages/order")
async def reorder_pages(project_id: str, req: ReorderPagesRequest):
    project = _load_or_404(project_id)
    pages = project.setdefault("composerPages", [])
    existing = [p.get("id") for p in pages]
    if sorted(req.page_ids) != sorted(existing):
        raise HTTPException(
            status_code=400,
            detail="page_ids must be a permutation of the existing page ids")
    by_id = {p["id"]: p for p in pages}
    ordered = [by_id[pid] for pid in req.page_ids]
    for i, p in enumerate(ordered):
        p["order"] = i
    project["composerPages"] = ordered
    storage.save_project(project)
    return {"success": True,
            "pages": [{"id": p["id"], "order": p["order"]} for p in ordered]}


# ---------------------------------------------------------------------------
# Element-level CRUD
# ---------------------------------------------------------------------------

_ALLOWED_TYPES = {"image-slot", "image", "page-image", "text", "bubble"}


def _validate_element_payload(el: Dict[str, Any], partial: bool = False) -> None:
    if not partial or "type" in el:
        if el.get("type") not in _ALLOWED_TYPES:
            raise HTTPException(status_code=400,
                                detail=f"type must be one of {sorted(_ALLOWED_TYPES)}")
    for key in ("x", "y", "width", "height"):
        if key in el:
            v = el[key]
            if not isinstance(v, (int, float)) or not (0 <= v <= 100):
                raise HTTPException(status_code=400,
                                    detail=f"{key} must be a number in 0-100")
    if "width" in el and el["width"] <= 0:
        raise HTTPException(status_code=400, detail="width must be > 0")
    if "height" in el and el["height"] <= 0:
        raise HTTPException(status_code=400, detail="height must be > 0")
    if "strokeWidth" in el and el["strokeWidth"] is not None:
        v = el["strokeWidth"]
        if not isinstance(v, (int, float)) or not (0 <= v <= 20):
            raise HTTPException(status_code=400,
                                detail="strokeWidth must be a number in 0-20")
    if "strokeColor" in el and el["strokeColor"] is not None:
        if not isinstance(el["strokeColor"], str):
            raise HTTPException(status_code=400,
                                detail="strokeColor must be a string")
    if "corners" in el and el["corners"] is not None:
        c = el["corners"]
        if not isinstance(c, dict) or set(c.keys()) != {"tl", "tr", "br", "bl"}:
            raise HTTPException(status_code=400,
                                detail="corners needs tl/tr/br/bl")
        for k, pt in c.items():
            if not isinstance(pt, dict) \
                    or not isinstance(pt.get("x"), (int, float)) \
                    or not isinstance(pt.get("y"), (int, float)):
                raise HTTPException(status_code=400,
                                    detail=f"corners.{k} needs numeric x/y")


def _find_page(project: Dict[str, Any], page_id: str) -> Dict[str, Any]:
    for page in project.get("composerPages", []):
        if page.get("id") == page_id:
            return page
    raise HTTPException(status_code=404, detail="Page not found")


@router.post("/projects/{project_id}/pages/{page_id}/elements")
async def add_element(project_id: str, page_id: str, el: Dict[str, Any]):
    project = _load_or_404(project_id)
    page = _find_page(project, page_id)
    el = dict(el)
    _validate_element_payload(el)
    el.setdefault("id", uuid.uuid4().hex)
    if any(e.get("id") == el["id"] for e in page["elements"]):
        raise HTTPException(status_code=400, detail="element id already exists")
    el.setdefault("rotation", 0)
    el.setdefault("locked", False)
    el.setdefault("visible", True)
    if "zIndex" not in el:
        el["zIndex"] = max((e.get("zIndex", 0) for e in page["elements"]),
                           default=0) + 1
    if el["type"] == "page-image":
        el.setdefault("frameBorderWidth", 0)   # breakout overlays have no border
    page["elements"].append(el)
    storage.save_project(project)
    return {"success": True, "element": el}


@router.patch("/projects/{project_id}/pages/{page_id}/elements/{element_id}")
async def patch_element(project_id: str, page_id: str, element_id: str,
                        updates: Dict[str, Any]):
    project = _load_or_404(project_id)
    page = _find_page(project, page_id)
    updates = dict(updates)
    if "id" in updates and updates["id"] != element_id:
        raise HTTPException(status_code=400, detail="cannot change element id")
    if "type" in updates:
        raise HTTPException(status_code=400,
                            detail="cannot change element type; delete and re-add")
    updates.pop("id", None)
    _validate_element_payload(updates, partial=True)
    for el in page["elements"]:
        if el.get("id") == element_id:
            el.update(updates)
            storage.save_project(project)
            return {"success": True, "element": el}
    raise HTTPException(status_code=404, detail="Element not found")


@router.delete("/projects/{project_id}/pages/{page_id}/elements/{element_id}")
async def delete_element(project_id: str, page_id: str, element_id: str):
    project = _load_or_404(project_id)
    page = _find_page(project, page_id)
    for el in page["elements"]:
        if el.get("id") == element_id:
            page["elements"].remove(el)
            storage.save_project(project)
            return {"success": True}
    raise HTTPException(status_code=404, detail="Element not found")


# ---------------------------------------------------------------------------
# Preview & export
# ---------------------------------------------------------------------------

@router.get("/projects/{project_id}/pages/{page_id}/preview.png")
async def page_preview(project_id: str, page_id: str, scale: float = 2.0):
    project = _load_or_404(project_id)
    page = _find_page(project, page_id)
    scale = min(4.0, max(0.5, scale))
    img = render_page(page, scale, _resolver)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


class AgentExportRequest(BaseModel):
    project_id: str
    format: str = "both"       # pdf | zip | both
    scale: float = 2.0
    page_numbers: bool = False # stamp page numbers (cover stays unnumbered)


@router.post("/export")
async def agent_export(req: AgentExportRequest):
    project = _load_or_404(req.project_id)
    pages = project.get("composerPages") or []
    if not pages:
        raise HTTPException(status_code=400,
                            detail="project has no composer pages; build pages first")
    if req.format not in ("pdf", "zip", "both"):
        raise HTTPException(status_code=400, detail="format must be pdf|zip|both")
    fmt = req.format
    base_name = f"manga_{req.project_id[:8]}_{time.strftime('%Y%m%d_%H%M%S')}"
    result = export_pages(pages, fmt, min(4.0, max(0.5, req.scale)),
                          _resolver, _exports_dir(), base_name,
                          page_numbers=req.page_numbers)
    logger.info("agent/export project=%s fmt=%s base=%s", req.project_id, fmt,
                base_name)
    return result
