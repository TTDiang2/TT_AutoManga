from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import uvicorn
import shutil
import json

from .api import storyboard, prompt, assets, project, export, settings, layouts, archive, character_templates, characters, composer_templates
from .core.config import BASE_DIR, PROJECTS_DIR, ASSETS_DIR


def _cleanup_orphan_assets() -> None:
    """Remove orphan asset files not referenced by any project."""
    if not ASSETS_DIR.exists():
        return

    referenced_paths: set[str] = set()

    for proj_dir in PROJECTS_DIR.iterdir():
        if not proj_dir.is_dir():
            continue
        meta_file = proj_dir / "project.json"
        if not meta_file.exists():
            continue
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                proj = json.load(f)
            for panel in proj.get("panels", []):
                img = panel.get("image")
                if img and not img.startswith("data:") and Path(img).exists():
                    referenced_paths.add(str(Path(img).resolve()))
        except Exception:
            pass

    total_deleted = 0
    total_size = 0

    for item in ASSETS_DIR.iterdir():
        if not item.is_dir():
            continue
        if item.name == "default":
            for pf in item.rglob("*"):
                if pf.is_file():
                    total_size += pf.stat().st_size
                    pf.unlink()
                    total_deleted += 1
            for pf in list(item.rglob("*")):
                pass
            shutil.rmtree(item)
        else:
            for pf in item.rglob("*"):
                if pf.is_file() and str(pf.resolve()) not in referenced_paths:
                    total_size += pf.stat().st_size
                    pf.unlink()
                    total_deleted += 1
            for d in sorted(item.rglob("*"), key=lambda x: str(x)):
                if not any(True for _ in d.iterdir()) and d != item and d != ASSETS_DIR:
                    try:
                        d.rmdir()
                    except Exception:
                        pass

    if total_deleted > 0:
        print(f"[Cleanup] Removed {total_deleted} orphan files ({total_size / 1024 / 1024:.1f} MB)")


_cleanup_orphan_assets()

app = FastAPI(title="AutoManga API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(storyboard.router)
app.include_router(prompt.router)
app.include_router(assets.router)
app.include_router(project.router)
app.include_router(export.router)
app.include_router(settings.router)
app.include_router(layouts.router)
app.include_router(archive.router)
app.include_router(character_templates.router)
app.include_router(characters.router)
app.include_router(composer_templates.router)


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}


frontend_dir = BASE_DIR / "frontend" / "dist"

if frontend_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dir / "assets")), name="assets")


@app.get("/")
async def serve_frontend():
    if frontend_dir.exists():
        return FileResponse(str(frontend_dir / "index.html"))
    return {"error": "Frontend not found"}


@app.get("/{path:path}")
async def serve_frontend_paths(path: str):
    if frontend_dir.exists():
        file_path = frontend_dir / path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(frontend_dir / "index.html"))
    return {"error": "Frontend not found"}


if __name__ == "__main__":
    import sys
    import logging
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5180

    # Enable our app loggers. Uvicorn's default log_config disables
    # pre-existing loggers (`disable_existing_loggers=True`), which silently
    # silences anything outside uvicorn.* namespaces. Attach an explicit
    # StreamHandler to the root logger and re-enable ours.
    app_handler = logging.StreamHandler()
    app_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s")
    )
    logging.getLogger().addHandler(app_handler)
    logging.getLogger().setLevel(logging.INFO)
    for name in ("backend.api.prompt", "backend.api.storyboard", "backend.api.assets",
                 "backend.api.export", "backend.api.characters", "backend.core.openai_client",
                 "backend.core.swarmui_client"):
        logging.getLogger(name).setLevel(logging.INFO)
        logging.getLogger(name).propagate = True

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
