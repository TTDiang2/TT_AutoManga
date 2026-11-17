import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Project directories - go up from backend/core to root
BASE_DIR = Path(__file__).parent.parent.parent
# AUTOMANGA_DATA_DIR relocates DATA_DIR-derived state (settings, projects,
# assets, auth, comics run) for a throwaway test instance. A few modules
# (export, archive, templates, characters) still build data/ paths of their
# own. Default: the repo's data/ directory.
DATA_DIR = Path(os.environ["AUTOMANGA_DATA_DIR"]).expanduser() \
    if os.environ.get("AUTOMANGA_DATA_DIR") else BASE_DIR / "data"
PROJECTS_DIR = DATA_DIR / "projects"
ASSETS_DIR = DATA_DIR / "assets"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
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
    tags_system_prompt: str = "You are an AI prompt tag specialist. Convert scene descriptions into comma-separated Danbooru-style tags suitable for SDXL image generation. Use quality and style tags, and add (1.0) weight to important elements. Output only the tags."
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


class AuthConfig(BaseModel):
    # The reverse proxy (Caddy on gate) whose X-Forwarded-For / -Proto we
    # believe. Requests it relays are never treated as local. Edit
    # data/settings.json to change; empty disables proxy trust.
    trustedProxy: str = "192.168.1.11"


class AppSettings(BaseModel):
    api: APIConfig = APIConfig()
    swarmui: SwarmUIConfig = SwarmUIConfig()
    defaults: DefaultSettings = DefaultSettings()
    auth: AuthConfig = AuthConfig()
    language: str = "en"


def mask_api_key(key: str) -> str:
    """Masked form returned to clients: never the full key, shows last 4."""
    if not key:
        return ""
    return "****" + key[-4:] if len(key) > 4 else "****"


def is_masked_api_key(value: str) -> bool:
    """True for values produced by mask_api_key — clients echo them back
    verbatim when they don't retype the key; such echoes must not overwrite
    the stored key."""
    return bool(value) and value.startswith("****")


def atomic_write_json(path: Path, data, **dump_kwargs) -> None:
    """Write JSON to a temp file in the same dir, then os.replace it over
    ``path`` — a crash mid-write can never leave a truncated file behind."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.",
                               suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, **dump_kwargs)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _backup_corrupt(file: Path) -> None:
    """Copy an unreadable JSON file aside so the next save can't destroy it."""
    try:
        shutil.copy2(file, file.with_name(file.name + ".corrupt"))
    except OSError as e:
        logger.warning("could not back up corrupt %s: %s", file, e)


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
        except Exception as e:
            logger.warning(
                "settings.json unreadable (%s); backed up to settings.json.corrupt "
                "and falling back to defaults", e)
            _backup_corrupt(SETTINGS_FILE)
    return AppSettings()


def save_settings(settings: AppSettings) -> None:
    """Save settings to JSON file."""
    atomic_write_json(SETTINGS_FILE, settings.model_dump(), indent=2)


def reset_settings_in_place(target: AppSettings) -> None:
    """Restore defaults by mutating ``target`` — other modules imported the
    settings object itself (``from .config import settings``), so rebinding
    config.settings would leave them reading the stale one."""
    fresh = AppSettings()
    for name in AppSettings.model_fields:
        setattr(target, name, getattr(fresh, name))


# Global settings instance
settings = load_settings()
