from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from ..core.openai_client import client

router = APIRouter(prefix="/api/prompt", tags=["prompt"])


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
    
    if req.endpoint:
        client.update_config(endpoint=req.endpoint)
    if req.api_key is not None:
        client.update_config(api_key=req.api_key)
    if req.model:
        client.update_config(model=req.model)
    
    try:
        result = await client.enhance_prompt(req.scene_description, req.mode)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch-enhance")
async def batch_enhance_prompts(req: BatchEnhanceRequest):
    if not req.scenes:
        raise HTTPException(status_code=400, detail="No scenes provided")
    
    if req.endpoint:
        client.update_config(endpoint=req.endpoint)
    if req.api_key is not None:
        client.update_config(api_key=req.api_key)
    if req.model:
        client.update_config(model=req.model)
    
    results = []
    for scene in req.scenes:
        try:
            result = await client.enhance_prompt(scene, req.mode)
            results.append(result)
        except Exception as e:
            results.append({"error": str(e)})
    
    return {"results": results}
