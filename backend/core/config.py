import os
import json
from pathlib import Path
from typing import Optional
from pydantic import BaseModel

# Project directories - go up from backend/core to root
BASE_DIR = Path(__file__).parent.parent.parent
DATA_DIR = BASE_DIR / "data"
PROJECTS_DIR = DATA_DIR / "projects"
ASSETS_DIR = DATA_DIR / "assets"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
PROJECTS_DIR.mkdir(exist_ok=True)
ASSETS_DIR.mkdir(exist_ok=True)

# Settings file path
SETTINGS_FILE = DATA_DIR / "settings.json"


class APIConfig(BaseModel):
    endpoint: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 4096
    thinking: bool = True
    storyboard_system_prompt: str = "You are a professional manga storyboard artist. Analyze the novel text and create detailed storyboard panels with scene descriptions, character dialogues, and panel compositions. Output JSON array with format: [{\"id\": \"panel_1\", \"scene\": \"description\", \"characters\": [\"char1\"], \"dialogue\": \"text\"}]"
    prompt_system_prompt: str = "You are an AI art prompt expert. Enhance scene descriptions into detailed, vivid prompts for AI image generation. Include lighting, atmosphere, composition, and style details."
    storyboardPresets: list = []
    promptPresets: list = []


class LoraConfig(BaseModel):
    name: str = ""
    weight: float = 1.0


class SwarmUIPreset(BaseModel):
    id: str = ""
    name: str = ""
    model: str = ""
    loras: list[LoraConfig] = []
    steps: int = 20
    cfgScale: float = 7.0
    width: int = 512
    height: int = 768
    samplerName: str = "Euler"
    promptSuffix: str = ""


class SwarmUIConfig(BaseModel):
    address: str = "http://127.0.0.1:7801"
    activePresetId: str = ""
    presets: list[SwarmUIPreset] = []
    currentModel: str = ""
    currentLoras: list[LoraConfig] = []
    currentSteps: int = 20
    currentCfgScale: float = 7.0
    currentWidth: int = 512
    currentHeight: int = 768
    currentSamplerName: str = "Euler"
    promptSuffix: str = ""


class DefaultSettings(BaseModel):
    detailLevel: int = 3
    autoSaveInterval: int = 60
    exportQuality: str = "high"


class AppSettings(BaseModel):
    api: APIConfig = APIConfig()
    swarmui: SwarmUIConfig = SwarmUIConfig()
    defaults: DefaultSettings = DefaultSettings()
    language: str = "en"


def load_settings() -> AppSettings:
    """Load settings from JSON file or return defaults."""
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("swarmui"):
                    suffix = data["swarmui"].pop("prompt_suffix", None)
                    if suffix is not None and not data["swarmui"].get("promptSuffix"):
                        data["swarmui"]["promptSuffix"] = suffix
                return AppSettings(**data)
        except Exception:
            pass
    return AppSettings()


def save_settings(settings: AppSettings) -> None:
    """Save settings to JSON file."""
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings.model_dump(), f, indent=2)


# Global settings instance
settings = load_settings()
