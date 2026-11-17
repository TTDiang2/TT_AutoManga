import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from urllib.parse import urlsplit
from pathlib import Path
import uvicorn
import json
import time

from .api import storyboard, prompt, assets, project, export, settings, layouts, archive, character_templates, characters, composer_templates, render, agent, comics, fonts
from .api import auth as auth_api
from .api import auth_google as auth_google_api
from .api import training as training_api
from .api import collections as collections_api
from .core import auth as auth_core
from .core.config import BASE_DIR, PROJECTS_DIR, ASSETS_DIR

logger = logging.getLogger(__name__)


ORPHAN_ASSET_MIN_AGE_S = 14 * 24 * 3600


def _asset_created(entry: dict) -> float:
    """Creation time of an asset: index created_at, else file mtime. An
    asset whose age can't be told counts as brand new (never deleted)."""
    created = entry.get("created_at")
    if created:
        try:
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            pass
    try:
        return Path(entry.get("path", "")).stat().st_mtime
    except OSError:
        return time.time()


def _cleanup_orphan_assets() -> None:
    """Remove asset files not referenced by any project (asset index aware).

    Safety rule: if any project.json fails to parse, abort the whole cleanup —
    deleting "orphans" we can't prove orphaned would destroy that project's
    assets.
    """
    if not ASSETS_DIR.exists():
        return

    referenced: set[str] = set()        # asset ids referenced via /api/assets/file/
    referenced_paths: set[str] = set()  # legacy absolute file paths

    for proj_dir in PROJECTS_DIR.iterdir():
        if not proj_dir.is_dir():
            continue
        meta_file = proj_dir / "project.json"
        if not meta_file.exists():
            # could be a save interrupted between mkdir and the first write —
            # its assets are unprovable orphans, so keep everything
            logger.warning(
                "orphan cleanup aborted: %s has no project.json; keeping all "
                "assets", proj_dir)
            return
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                proj = json.load(f)
        except Exception as e:
            logger.warning(
                "orphan cleanup aborted: %s is unreadable (%s); keeping all "
                "assets so the project can be repaired", meta_file, e)
            return
        try:
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
            # per-project character overrides may carry their own sheet
            for ch in (proj.get("settings") or {}).get("characters") or []:
                img = ch.get("image") if isinstance(ch, dict) else None
                if isinstance(img, str) and img.startswith("/api/assets/file/"):
                    referenced.add(img.rsplit("/", 1)[-1])
        except Exception as e:
            logger.warning(
                "orphan cleanup aborted: %s has unexpected content (%s); "
                "keeping all assets", meta_file, e)
            return

    # character sheets in the library (data/characters.json) are references
    # too; an unreadable library aborts the cleanup like a bad project.json
    from .api import characters as characters_mod
    try:
        with characters_mod.CHARACTERS_LOCK:
            library = characters_mod._load_characters()
        for ch in library:
            img = ch.get("image") if isinstance(ch, dict) else None
            if isinstance(img, str) and img.startswith("/api/assets/file/"):
                referenced.add(img.rsplit("/", 1)[-1])
    except Exception as e:
        logger.warning(
            "orphan cleanup aborted: %s is unreadable (%s); keeping all assets",
            characters_mod.CHARACTERS_FILE, e)
        return

    from .storage import asset_store as asset_store_mod
    asset_store = asset_store_mod.asset_store
    # Unreferenced is not the same as unwanted: unapplied variants, upscale
    # outputs, overlay/cover art not placed yet and /api/assets/file uploads
    # (the Comics converter caches those URLs) are all legitimately
    # unreferenced for a while. Only reclaim assets nobody used for weeks.
    cutoff = time.time() - ORPHAN_ASSET_MIN_AGE_S
    stale = [a for a in asset_store.ids()
             if a not in referenced
             and _asset_created(asset_store.get(a) or {}) < cutoff]
    removed = asset_store.remove_many(stale)   # one index.json flush

    # Legacy per-project dirs (pre-refactor uploads): same rule, same age gate.
    for item in ASSETS_DIR.iterdir():
        if not item.is_dir():
            continue
        for pf in item.rglob("*"):
            if pf.is_file() and str(pf.resolve()) not in referenced_paths \
                    and pf.name != "index.json" \
                    and pf.stat().st_mtime < cutoff:
                pf.unlink()
                removed += 1

    if removed > 0:
        logger.info("[Cleanup] Removed %d orphan asset file(s)", removed)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Disk-touching maintenance runs at server startup, not at import time,
    # so importing the app (tests, CLI helpers) never deletes files.
    _cleanup_orphan_assets()
    yield


# No public /docs, /redoc or /openapi.json: the schema is served at
# /api/openapi.json, behind the login gate (local callers pass).
app = FastAPI(title="AutoManga API", version="1.0.0", lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)

def _finite(value):
    """Non-finite floats (NaN/Infinity echoed back as a validation error's
    input) as strings: JSONResponse refuses to encode them."""
    import math
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {k: _finite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite(v) for v in value]
    return value


@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422,
                        content={"detail": _finite(jsonable_encoder(exc.errors()))})


# No CORS middleware: the backend serves the UI itself (same origin) and the
# vite dev server proxies /api. Anything else — including a malicious page in
# the user's browser — gets no cross-origin access to the API.

_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}
_LOOPBACK_NAMES = {"localhost", "127.0.0.1", "::1"}


def _cross_origin(request: Request) -> bool:
    """A mutating request whose Origin host differs from Host (CSRF). The
    vite dev server (localhost:5173 proxying to :5180) is allowed for local
    requests."""
    origin = request.headers.get("origin")
    if origin is None:
        return False
    try:
        parts = urlsplit(origin)
        origin_host, origin_name = parts.netloc.lower(), (parts.hostname or "")
    except ValueError:
        return True
    if origin_host and origin_host == request.headers.get("host", "").lower():
        return False
    return not (auth_core.is_local(request) and origin_name in _LOOPBACK_NAMES)


@app.middleware("http")
async def auth_gate(request: Request, call_next):
    """Login gate for /api (see backend/core/auth.py). The SPA shell and
    /assets are public; local callers (loopback, no forwarding headers) pass;
    everyone else needs a valid am_session cookie. Every request (SPA
    included) must carry an allowed Host: DNS rebinding guard."""
    if not auth_core.host_allowed(request):
        return JSONResponse({"detail": "unknown Host header; add it to "
                                       "settings auth.allowedHosts"},
                            status_code=400)
    path = request.url.path
    if not (path == "/api" or path.startswith("/api/")):
        return await call_next(request)
    if request.method in _MUTATING and _cross_origin(request):
        return JSONResponse({"detail": "cross-origin request refused"},
                            status_code=403)
    if (request.method, path.rstrip("/") or "/") in auth_api.PUBLIC_PATHS \
            or path == "/api/health" or auth_core.is_local(request):
        return await call_next(request)
    data = auth_core.load_auth()
    if data is None:
        return JSONResponse({"detail": "login is not configured on this server"},
                            status_code=503)
    # a Google session (claims["email"]) ends once its address is no longer allowed
    claims = auth_core.check_session(request.cookies.get(auth_core.COOKIE_NAME), data)
    if claims is None:
        return JSONResponse({"detail": "authentication required"},
                            status_code=401)
    response = await call_next(request)
    if auth_core.needs_refresh(claims) and \
            auth_core.COOKIE_NAME not in response.headers.get("set-cookie", ""):
        auth_core.set_session_cookie(response, request, data,   # rolling refresh
                                     email=claims.get("email"))
    return response


app.include_router(auth_api.router)
app.include_router(auth_google_api.router)
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
app.include_router(comics.router)
app.include_router(fonts.router)
app.include_router(training_api.router)
app.include_router(collections_api.router)


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}


@app.get("/api/openapi.json", include_in_schema=False)
async def openapi_schema():
    """The machine-readable API schema (gated like the rest of /api)."""
    return app.openapi()


frontend_dir = BASE_DIR / "frontend" / "dist"
frontend_root = frontend_dir.resolve()  # containment anchor for the catch-all


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
        # path may contain ../ or URL-encoded %2e%2e segments; serve only
        # files that resolve inside frontend/dist.
        file_path = (frontend_dir / path).resolve()
        if file_path.is_relative_to(frontend_root) \
                and file_path.exists() and file_path.is_file():
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
                 "backend.api.export", "backend.api.characters", "backend.api.agent",
                 "backend.core.openai_client", "backend.core.swarmui_client"):
        logging.getLogger(name).setLevel(logging.INFO)
        logging.getLogger(name).propagate = True

    # Loopback by default; set AUTOMANGA_HOST=0.0.0.0 to serve the LAN.
    import os
    host = os.environ.get("AUTOMANGA_HOST", "127.0.0.1")
    os.environ["AUTOMANGA_PORT"] = str(port)   # the comics converter calls back here
    uvicorn.run(app, host=host, port=port, log_level="info")
