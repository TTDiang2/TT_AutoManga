from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from ..core.openai_client import client
from ..core.config import settings

router = APIRouter(prefix="/api/storyboard", tags=["storyboard"])


class GenerateRequest(BaseModel):
    text: str
    detail_level: int = 3
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    thinking: Optional[bool] = None


class PanelUpdate(BaseModel):
    id: str
    scene: Optional[str] = None
    characters: Optional[List[str]] = None
    dialogue: Optional[str] = None
    order: Optional[int] = None


@router.post("/generate")
async def generate_storyboard(req: GenerateRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    
    client.reload_from_settings()
    
    if req.endpoint:
        client.update_config(endpoint=req.endpoint)
    if req.api_key is not None:
        client.update_config(api_key=req.api_key)
    if req.model:
        client.update_config(model=req.model)
    if req.temperature is not None:
        client.update_config(temperature=req.temperature)
    if req.thinking is not None:
        client.update_config(thinking=req.thinking)
    
    try:
        result = await client.generate_storyboard(req.text, req.detail_level)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update-panel")
async def update_panel(update: PanelUpdate):
    return {"success": True, "panel": update}
