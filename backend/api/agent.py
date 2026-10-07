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
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from PIL import Image

from ..assembly import build_page
from ..core.config import settings
from ..core.openai_client import client as llm_client
from ..core.swarmui_client import swarm_client
from ..jobs import create_job, job_snapshot, run_job
from ..render import render_page
from ..render.export_service import export_pages
from ..render.resolve import make_resolver
from ..storage.asset_store import asset_store
from ..storage.manager import storage

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
    project = storage.load_project(project_id)
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
    if req.api_key is not None:
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
    apply_to_panel: bool = True
    kind: str = "panel"                # panel | overlay | character


async def _do_generate(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Core single-request generation shared by /generate and /generate-batch."""
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("prompt is required")
    variants = max(1, min(4, int(payload.get("variants") or 1)))
    seed = payload.get("seed")
    swarm_settings = settings.swarmui
    loras = None
    if swarm_settings.currentLoras:
        from ..core.config import LoraConfig
        loras = [LoraConfig(name=l.get("name", ""), weight=l.get("weight", 1.0))
                 for l in swarm_settings.currentLoras if l.get("name")]

    assets_out = []
    for v in range(variants):
        result = await swarm_client.generate_image(
            prompt=prompt,
            negative_prompt=payload.get("negative_prompt") or "",
            model=swarm_settings.currentModel or None,
            steps=payload.get("steps") or swarm_settings.currentSteps,
            cfg_scale=payload.get("cfg_scale") or swarm_settings.currentCfgScale,
            width=payload.get("width") or swarm_settings.currentWidth,
            height=payload.get("height") or swarm_settings.currentHeight,
            sampler_name=swarm_settings.currentSamplerName,
            loras=loras,
            seed=(seed + v) if seed is not None else None,
            remove_background=bool(payload.get("remove_background")),
        )
        if not result.get("success"):
            raise RuntimeError(f"SwarmUI: {result.get('error', 'unknown error')}")
        img_bytes = base64.b64decode(result["image"].split(",", 1)[1])
        entry = asset_store.save_dataurl(
            result["image"],
            project_id=payload.get("project_id") or None,
            kind=payload.get("kind") or "panel",
            meta={"prompt": prompt, "seed": (seed + v) if seed is not None else None,
                  "remove_background": bool(payload.get("remove_background"))},
        )
        img = Image.open(io.BytesIO(img_bytes))
        has_alpha = (img.mode == "RGBA"
                     and img.getchannel("A").getextrema()[0] < 255)
        assets_out.append({
            "asset_id": entry["asset_id"],
            "url": asset_store.url_for(entry["asset_id"]),
            "width": img.size[0], "height": img.size[1],
            "has_alpha": has_alpha,
        })

    applied = False
    if payload.get("apply_to_panel", True) and payload.get("panel_id") \
            and payload.get("project_id"):
        from .assets import _save_panel_image
        _save_panel_image(payload["project_id"], payload["panel_id"],
                          assets_out[0]["url"])
        applied = True
    return {"assets": assets_out, "applied": applied}


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
    asyncio.create_task(run_job(job.id, _do_generate))
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=202,
                        content={"job_id": job.id, "total": job.total})


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    snap = job_snapshot(job_id)
    if not snap:
        raise HTTPException(status_code=404, detail="Job not found")
    return snap


# ---------------------------------------------------------------------------
# Page assembly
# ---------------------------------------------------------------------------

class BuildPageRequest(BaseModel):
    template: dict
    name: Optional[str] = None
    panel_ids: List[str] = []
    reading: str = "rtl"            # rtl | ltr
    bubbles: dict = {}              # {mode: auto|none, fontSize, vertical}
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
    # type is immutable (changing it in place would leave inconsistent fields)
    updates.pop("id", None)
    updates.pop("type", None)
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


@router.post("/export")
async def agent_export(req: AgentExportRequest):
    project = _load_or_404(req.project_id)
    pages = project.get("composerPages") or []
    if not pages:
        raise HTTPException(status_code=400,
                            detail="project has no composer pages; build pages first")
    fmt = req.format if req.format in ("pdf", "zip", "both") else "both"
    base_name = f"manga_{req.project_id[:8]}_{time.strftime('%Y%m%d_%H%M%S')}"
    result = export_pages(pages, fmt, min(4.0, max(0.5, req.scale)),
                          _resolver, _exports_dir(), base_name)
    logger.info("agent/export project=%s fmt=%s base=%s", req.project_id, fmt,
                base_name)
    return result
