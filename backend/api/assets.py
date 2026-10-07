from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from ..core.swarmui_client import swarm_client
from ..core.config import settings, LoraConfig
from ..storage.manager import storage
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
    project = storage.load_project(project_id)
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
    if req.swarmui_address:
        swarm_client.update_address(req.swarmui_address)
    
    loras = None
    if swarmsettings.currentLoras:
        loras = [LoraConfig(name=l.get("name", ""), weight=l.get("weight", 1.0)) for l in swarmsettings.currentLoras if l.get("name")]
    
    try:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[Generate] REQ from frontend: prompt='{req.prompt}', negative_prompt='{req.negative_prompt}', seed={req.seed}, panel_id={req.panel_id}")
        logger.info(f"[Generate] Using settings: steps={swarmsettings.currentSteps}, cfg={swarmsettings.currentCfgScale}, model={swarmsettings.currentModel}, w={swarmsettings.currentWidth}, h={swarmsettings.currentHeight}")
        
        result = await swarm_client.generate_image(
            prompt=req.prompt,
            negative_prompt=req.negative_prompt,
            model=swarmsettings.currentModel or None,
            steps=swarmsettings.currentSteps,
            cfg_scale=swarmsettings.currentCfgScale,
            width=swarmsettings.currentWidth,
            height=swarmsettings.currentHeight,
            sampler_name=swarmsettings.currentSamplerName,
            loras=loras,
            seed=req.seed,
            remove_background=req.remove_background
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


@router.get("/swarmui/status/{task_id}")
async def check_swarmui_status(task_id: str):
    try:
        status = await swarm_client.get_task_status(task_id)
        return status
    except Exception as e:
        return {"progress": 0, "status": str(e)}


@router.get("/swarmui/test")
async def test_swarmui_connection():
    try:
        result = await swarm_client.check_connection()
        return result
    except Exception as e:
        return {"connected": False, "status": str(e)}
