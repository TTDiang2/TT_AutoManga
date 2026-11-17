from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from ..core.openai_client import client

router = APIRouter(prefix="/api/storyboard", tags=["storyboard"])


class GenerateRequest(BaseModel):
    text: str
    detail_level: int = 3
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    thinking: Optional[bool] = None


@router.post("/generate")
async def generate_storyboard(req: GenerateRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    
    # a request-local client: the frontend echoes the masked key from GET
    # /api/settings/; only a freshly typed key overrides the stored one, and
    # the stored key never goes to an endpoint other than the stored one
    llm = client.for_request(req.endpoint, req.api_key, model=req.model,
                             temperature=req.temperature, thinking=req.thinking)

    try:
        result = await llm.generate_storyboard(req.text, req.detail_level)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
