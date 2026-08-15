from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import logging
from ..core.openai_client import client

router = APIRouter(prefix="/api/prompt", tags=["prompt"])

logger = logging.getLogger(__name__)


class EnhanceRequest(BaseModel):
    scene_description: str
    mode: str = "turbo"
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None


class BatchEnhanceRequest(BaseModel):
    scenes: List[str]
    mode: str = "turbo"
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None


@router.post("/enhance")
async def enhance_prompt(req: EnhanceRequest):
    if not req.scene_description.strip():
        raise HTTPException(status_code=400, detail="Scene description cannot be empty")
    
    client.reload_from_settings()
    
    if req.endpoint:
        client.update_config(endpoint=req.endpoint)
    if req.api_key is not None:
        client.update_config(api_key=req.api_key)
    if req.model:
        client.update_config(model=req.model)
    
    logger.info(
        "prompt/enhance mode=%s model=%s endpoint=%s scene_len=%d",
        req.mode,
        req.model or client.model,
        req.endpoint or client.endpoint,
        len(req.scene_description),
    )
    
    try:
        result = await client.enhance_prompt(req.scene_description, req.mode)
        logger.info(
            "prompt/enhance OK mode=%s out_len=%d",
            req.mode,
            len(result.get("enhanced_prompt") or ""),
        )
        return result
    except Exception as e:
        logger.exception("prompt/enhance failed mode=%s: %s", req.mode, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch-enhance")
async def batch_enhance_prompts(req: BatchEnhanceRequest):
    if not req.scenes:
        raise HTTPException(status_code=400, detail="No scenes provided")
    
    client.reload_from_settings()
    
    if req.endpoint:
        client.update_config(endpoint=req.endpoint)
    if req.api_key is not None:
        client.update_config(api_key=req.api_key)
    if req.model:
        client.update_config(model=req.model)
    
    logger.info(
        "prompt/batch-enhance mode=%s model=%s endpoint=%s count=%d",
        req.mode,
        req.model or client.model,
        req.endpoint or client.endpoint,
        len(req.scenes),
    )
    
    results = []
    for scene in req.scenes:
        try:
            result = await client.enhance_prompt(scene, req.mode)
            results.append(result)
        except Exception as e:
            logger.exception("prompt/batch-enhance item failed: %s", e)
            results.append({"error": str(e)})
    
    logger.info("prompt/batch-enhance OK returned=%d", len(results))
    return {"results": results}
