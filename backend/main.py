from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import uvicorn
import json

from .api import storyboard, prompt, assets, project, export, settings, layouts, archive, character_templates, characters, composer_templates, render, agent
from .core.config import BASE_DIR, PROJECTS_DIR, ASSETS_DIR


def _cleanup_orphan_assets() -> None:
    """Remove asset files not referenced by any project (asset index aware)."""
    if not ASSETS_DIR.exists():
        return

    referenced: set[str] = set()        # asset ids referenced via /api/assets/file/
    referenced_paths: set[str] = set()  # legacy absolute file paths

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
                if img and not img.startswith("data:"):
                    if img.startswith("/api/assets/file/"):
                        referenced.add(img.rsplit("/", 1)[-1])
                    elif not img.startswith("/api/") and Path(img).exists():
                        referenced_paths.add(str(Path(img).resolve()))
            for page in proj.get("composerPages", []):
                for el in page.get("elements", []):
                    for key in ("src", "originalSrc"):
                        v = el.get(key)
                        if not v or v.startswith("data:"):
                            continue
                        if v.startswith("/api/assets/file/"):
                            referenced.add(v.rsplit("/", 1)[-1])
                        elif not v.startswith("/api/") and Path(v).exists():
                            referenced_paths.add(str(Path(v).resolve()))
        except Exception:
            pass

    from .storage.asset_store import asset_store
    removed = 0
    for asset_id in list(asset_store.ids()):
        if asset_id not in referenced:
            if asset_store.remove(asset_id):
                removed += 1

    # Legacy per-project dirs (pre-refactor uploads): same rule as before.
    for item in ASSETS_DIR.iterdir():
        if not item.is_dir():
            continue
        for pf in item.rglob("*"):
            if pf.is_file() and str(pf.resolve()) not in referenced_paths \
                    and pf.name != "index.json":
                pf.unlink()
                removed += 1

    if removed > 0:
        print(f"[Cleanup] Removed {removed} orphan asset file(s)")


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
app.include_router(render.router)
app.include_router(agent.router)


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
