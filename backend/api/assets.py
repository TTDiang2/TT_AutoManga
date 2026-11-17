import asyncio
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from ..core.swarmui_client import swarm_client
from ..core.config import settings, LoraConfig
from ..storage.manager import storage, InvalidProjectIdError
from ..storage.asset_store import asset_store

router = APIRouter(prefix="/api/assets", tags=["assets"])


class GenerateImageRequest(BaseModel):
    prompt: str
    negative_prompt: str = ""
    seed: Optional[int] = None
    panel_id: str
    project_id: str
    swarmui_address: Optional[str] = None
    remove_background: bool = False


class SwarmUISettingsRequest(BaseModel):
    model: Optional[str] = None
    preset: Optional[str] = None
    loras: Optional[List[Dict[str, Any]]] = None
    steps: Optional[int] = None
    cfg_scale: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    sampler_name: Optional[str] = None


class UploadRequest(BaseModel):
    project_id: str
    panel_id: str


def _save_panel_image(project_id: str, panel_id: str, image_data: str) -> str:
    """Store panel image reference; returns the final ref (asset URL or original)."""
    try:
        project = storage.load_project(project_id)
    except InvalidProjectIdError:
        return image_data
    if not project:
        return image_data
    if image_data.startswith("data:"):
        # Persist embedded payloads as asset files; keep project.json lean.
        entry = asset_store.save_dataurl(
            image_data,
            project_id=project_id or None,
            kind="panel",
        )
        image_data = asset_store.url_for(entry["asset_id"])
    for panel in project.get("panels", []):
        if panel.get("id") == panel_id:
            panel["image"] = image_data
            break
    storage.save_project(project)
    return image_data


@router.get("/file/{asset_id}")
async def get_asset_file(asset_id: str):
    path = asset_store.path_for(asset_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    suffix = path.suffix.lstrip(".").lower()
    media = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
             "webp": "image/webp"}.get(suffix, "application/octet-stream")
    return FileResponse(
        str(path),
        media_type=media,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.post("/file")
async def register_asset(
    file: UploadFile = File(...),
    kind: str = Form("upload"),
    project_id: Optional[str] = Form(None),
):
    """Register arbitrary image bytes as a reusable asset (e.g. agent-side
    post-processing output) without binding it to a panel."""
    try:
        contents = await file.read()
        ext = (file.content_type or "image/png").split("/")[-1]
        entry = asset_store.save_bytes(contents, ext=ext,
                                       project_id=project_id or None, kind=kind)
        return JSONResponse({
            "success": True,
            "asset_id": entry["asset_id"],
            "url": asset_store.url_for(entry["asset_id"]),
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload/{project_id}/{panel_id}")
async def upload_image(project_id: str, panel_id: str, file: UploadFile = File(...)):
    try:
        contents = await file.read()
        ext = (file.content_type or "image/png").split("/")[-1]
        entry = asset_store.save_bytes(contents, ext=ext, project_id=project_id, kind="upload")
        url = asset_store.url_for(entry["asset_id"])
        _save_panel_image(project_id, panel_id, url)
        return JSONResponse({
            "success": True,
            "image": url,
            "asset_id": entry["asset_id"],
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/swarmui/generate")
async def generate_with_swarmui(req: GenerateImageRequest):
    swarmsettings = settings.swarmui
    override = None
    if req.swarmui_address:
        # one-shot override: http(s) on loopback / the LAN only (no SSRF to
        # arbitrary hosts); the configured address itself is always fine
        from ..core.swarmui_client import _normalize_address, check_override_address
        if _normalize_address(req.swarmui_address) == swarm_client.address:
            override = swarm_client.address
        else:
            try:
                override = await asyncio.to_thread(check_override_address, req.swarmui_address)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

    loras = None
    if swarmsettings.currentLoras:
        loras = [l for l in swarmsettings.currentLoras if l.name]
    prompt = req.prompt
    # the panel characters' trained LoRAs + trigger words (global LoRAs stay;
    # a panel character's weight wins for the same LoRA)
    project = None
    try:
        project = storage.load_project(req.project_id) if req.project_id else None
    except InvalidProjectIdError:
        project = None
    panel = next((p for p in (project or {}).get("panels") or []
                  if p.get("id") == req.panel_id), None) if project else None
    ref_kwargs: Dict[str, Any] = {}
    if panel:
        from ..prompting import apply_conditioning, ipadapter_args, reference_for_panel
        prompt, loras, _ = apply_conditioning(prompt, loras, project, panel)
        # a solo panel's character sheet (refWeight > 0) guides it via IP-Adapter
        ref_kwargs = ipadapter_args(reference_for_panel(project, panel))

    try:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[Generate] REQ from frontend: prompt='{req.prompt}', negative_prompt='{req.negative_prompt}', seed={req.seed}, panel_id={req.panel_id}")
        logger.info(f"[Generate] Using settings: steps={swarmsettings.currentSteps}, cfg={swarmsettings.currentCfgScale}, model={swarmsettings.currentModel}, w={swarmsettings.currentWidth}, h={swarmsettings.currentHeight}")
        
        result = await swarm_client.generate_image(
            prompt=prompt,
            negative_prompt=req.negative_prompt,
            model=swarmsettings.currentModel or None,
            steps=swarmsettings.currentSteps,
            cfg_scale=swarmsettings.currentCfgScale,
            width=swarmsettings.currentWidth,
            height=swarmsettings.currentHeight,
            sampler_name=swarmsettings.currentSamplerName,
            loras=loras,
            seed=req.seed,
            remove_background=req.remove_background,
            # one-shot override: never rewrites the shared client's address
            address=override,
            **ref_kwargs,
        )
        
        if result.get("success"):
            # Persist as asset file and hand the URL back so the frontend
            # store does not re-embed a dataURL (which would duplicate assets
            # on the next autosave normalization).
            ref = _save_panel_image(req.project_id, req.panel_id, result["image"])
            result["image"] = ref
            result["asset_id"] = ref.rsplit("/", 1)[-1] if ref.startswith("/api/assets/file/") else None
            result["path"] = ref

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/swarmui/models")
async def get_swarmui_models():
    try:
        models = await swarm_client.get_models()
        return {"models": models}
    except Exception as e:
        return {"models": [], "error": str(e)}


@router.get("/swarmui/loras")
async def get_swarmui_loras():
    """Installed LoRAs for the Characters tab: [{name, trigger, architecture}],
    the name as SwarmUI's <lora:> tag wants it (relative to Models/Lora, no
    extension), the trigger from the model's metadata or the name convention."""
    from ..prompting import default_trigger, lora_base_name
    try:
        files = await swarm_client.list_models(subtype="LoRA")
    except Exception as e:
        return {"loras": [], "error": str(e)}
    out = []
    for f in files:
        name = lora_base_name(f.get("name") or "")
        if not name:
            continue
        trigger = (f.get("trigger_phrase") or "").strip() or default_trigger(name)
        out.append({"name": name, "trigger": trigger, "architecture": f.get("architecture") or ""})
    return {"loras": out}


@router.get("/swarmui/test")
async def test_swarmui_connection():
    try:
        result = await swarm_client.check_connection()
        return result
    except Exception as e:
        return {"connected": False, "status": str(e)}


# SwarmUI's optional features, probed at most once a minute (the Characters
# tab asks on every mount; the backend list rarely changes)
_FEATURES_TTL = 60.0
_features_cache: Dict[str, Any] = {"at": 0.0, "address": None, "value": None}


@router.get("/swarmui/features")
async def get_swarmui_features():
    """``{"ipadapter": bool, "presets": [str], "preset": str}``: whether a
    running SwarmUI backend has the IP-Adapter nodes (character-sheet
    references), its "Use IP-Adapter" presets and the configured one."""
    import time
    now = time.monotonic()
    address = swarm_client.address
    cached = _features_cache["value"]
    if cached is None or _features_cache["address"] != address or now - _features_cache["at"] > _FEATURES_TTL:
        try:
            cached = await swarm_client.ipadapter_features()
        except Exception:
            cached = {"ipadapter": False, "presets": []}
        _features_cache.update(at=now, address=address, value=cached)
    return {**cached, "preset": settings.swarmui.ipadapterPreset}
