from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from ..core import config

router = APIRouter(prefix="/api/settings", tags=["settings"])


class APIConfigUpdate(BaseModel):
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    thinking: Optional[bool] = None
    storyboard_system_prompt: Optional[str] = None
    prompt_system_prompt: Optional[str] = None
    tags_system_prompt: Optional[str] = None
    storyboardPresets: Optional[list] = None
    promptPresets: Optional[list] = None


class LoraConfigUpdate(BaseModel):
    name: Optional[str] = None
    weight: Optional[float] = None


class SwarmUIConfigUpdate(BaseModel):
    address: Optional[str] = None
    activePresetId: Optional[str] = None
    presets: Optional[List[Dict[str, Any]]] = None
    currentModel: Optional[str] = None
    currentLoras: Optional[List[Dict[str, Any]]] = None
    currentSteps: Optional[int] = None
    currentCfgScale: Optional[float] = None
    currentWidth: Optional[int] = None
    currentHeight: Optional[int] = None
    currentSamplerName: Optional[str] = None
    promptSuffix: Optional[str] = None


class DefaultSettingsUpdate(BaseModel):
    detailLevel: Optional[int] = None
    autoSaveInterval: Optional[int] = None
    exportQuality: Optional[str] = None


class FullSettingsUpdate(BaseModel):
    api: Optional[APIConfigUpdate] = None
    swarmui: Optional[SwarmUIConfigUpdate] = None
    defaults: Optional[DefaultSettingsUpdate] = None
    language: Optional[str] = None


@router.get("/")
async def get_settings():
    return {
        "api": config.settings.api.model_dump(),
        "swarmui": config.settings.swarmui.model_dump(),
        "defaults": config.settings.defaults.model_dump(),
        "language": config.settings.language
    }


@router.post("/")
async def update_settings(update: FullSettingsUpdate):
    try:
        if update.api:
            if update.api.endpoint is not None:
                config.settings.api.endpoint = update.api.endpoint
            if update.api.api_key is not None:
                config.settings.api.api_key = update.api.api_key
            if update.api.model is not None:
                config.settings.api.model = update.api.model
            if update.api.temperature is not None:
                config.settings.api.temperature = update.api.temperature
            if update.api.max_tokens is not None:
                config.settings.api.max_tokens = update.api.max_tokens
            if update.api.thinking is not None:
                config.settings.api.thinking = update.api.thinking
            if update.api.storyboard_system_prompt is not None:
                config.settings.api.storyboard_system_prompt = update.api.storyboard_system_prompt
            if update.api.prompt_system_prompt is not None:
                config.settings.api.prompt_system_prompt = update.api.prompt_system_prompt
            if update.api.tags_system_prompt is not None:
                config.settings.api.tags_system_prompt = update.api.tags_system_prompt
            if update.api.storyboardPresets is not None:
                config.settings.api.storyboardPresets = update.api.storyboardPresets
            if update.api.promptPresets is not None:
                config.settings.api.promptPresets = update.api.promptPresets
        
        if update.swarmui:
            if update.swarmui.address is not None:
                config.settings.swarmui.address = update.swarmui.address
            if update.swarmui.activePresetId is not None:
                config.settings.swarmui.activePresetId = update.swarmui.activePresetId
            if update.swarmui.presets is not None:
                config.settings.swarmui.presets = update.swarmui.presets
            if update.swarmui.currentModel is not None:
                config.settings.swarmui.currentModel = update.swarmui.currentModel
            if update.swarmui.currentLoras is not None:
                config.settings.swarmui.currentLoras = update.swarmui.currentLoras
            if update.swarmui.currentSteps is not None:
                config.settings.swarmui.currentSteps = update.swarmui.currentSteps
            if update.swarmui.currentCfgScale is not None:
                config.settings.swarmui.currentCfgScale = update.swarmui.currentCfgScale
            if update.swarmui.currentWidth is not None:
                config.settings.swarmui.currentWidth = update.swarmui.currentWidth
            if update.swarmui.currentHeight is not None:
                config.settings.swarmui.currentHeight = update.swarmui.currentHeight
            if update.swarmui.currentSamplerName is not None:
                config.settings.swarmui.currentSamplerName = update.swarmui.currentSamplerName
            if update.swarmui.promptSuffix is not None:
                config.settings.swarmui.promptSuffix = update.swarmui.promptSuffix
        
        if update.defaults:
            if update.defaults.detailLevel is not None:
                config.settings.defaults.detailLevel = update.defaults.detailLevel
            if update.defaults.autoSaveInterval is not None:
                config.settings.defaults.autoSaveInterval = update.defaults.autoSaveInterval
            if update.defaults.exportQuality is not None:
                config.settings.defaults.exportQuality = update.defaults.exportQuality
        
        if update.language is not None:
            config.settings.language = update.language
        
        config.save_settings(config.settings)
        
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset")
async def reset_settings():
    try:
        config.settings = config.AppSettings()
        config.save_settings(config.settings)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
