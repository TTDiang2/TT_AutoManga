"""Collections API (/api/collections/*): projects grouped as the episodes of
a series, and whole-collection export.

Data lives in backend/storage/collections.py (data/collections.json). The
export runs as a background thread (one at a time) rendering one page at a
time; poll GET /api/collections/exports/{job_id} for progress. Contract in
AGENTS.md ("Collections").
"""
import logging
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..content_rating import project_rating
from ..render import collection_export
from ..render.resolve import make_resolver
from ..storage import collections as store
from ..storage.asset_store import asset_store
from ..storage.manager import storage, InvalidProjectIdError
from .project import project_cover_src

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/collections", tags=["collections"])
_resolver = make_resolver(asset_store)


def _exports_dir():
    from . import export as export_api   # read at call time (tests patch it)
    return export_api.EXPORTS_DIR


def _summaries(cols: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    projects = {p.get("id"): p for p in storage.list_projects()}
    out = []
    for c in cols:
        episodes, missing = [], []
        for pid in c.get("projectIds") or []:
            p = projects.get(pid)
            if p is None:
                missing.append(pid)
                continue
            pages = p.get("composerPages") or []
            episodes.append({"id": pid, "name": p.get("name") or pid,
                             "pages": len(pages),
                             "firstPageId": pages[0].get("id") if pages else None,
                             "cover": project_cover_src(p),
                             "contentRating": project_rating(p),
                             "updatedAt": p.get("updatedAt")})
        if missing:
            logger.warning("collection %s lists missing project(s): %s",
                           c.get("id"), ", ".join(missing))
        cover = None
        chosen = c.get("cover") or {}
        if chosen.get("projectId") in projects:
            cover = project_cover_src(projects[chosen["projectId"]], chosen.get("pageId"))
        if cover is None:
            cover = next((e["cover"] for e in episodes if e["cover"]), None)
        out.append({**c, "episodes": episodes, "missing": missing,
                    "pages": sum(e["pages"] for e in episodes),
                    # an uncut-edition collection is stored mature (auto-group)
                    "mature": bool(c.get("mature")) or any(e["contentRating"] == "mature" for e in episodes),
                    "coverUrl": cover})
    return out


def _or_404(cid: str) -> Dict[str, Any]:
    col = store.get_collection(cid)
    if col is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    return col


@router.get("")
async def list_collections():
    return {"collections": _summaries(store.list_collections())}


class CreateCollectionRequest(BaseModel):
    name: str
    description: Optional[str] = None
    projectIds: List[str] = []


@router.post("")
async def create_collection(req: CreateCollectionRequest):
    try:
        col = store.create_collection(req.name, req.projectIds, req.description)
    except store.CollectionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"collection": _summaries([col])[0]}


@router.post("/auto-group")
async def auto_group():
    """Group projects named "<Title> — <Subtitle>" (or sharing a name) into
    auto collections; manual collections are never touched."""
    result = store.auto_group(storage.list_projects())
    logger.info("collections auto-group: %d created, %d updated, %d skipped",
                len(result["created"]), len(result["updated"]),
                len(result["skipped"]))
    return {**result, "collections": _summaries(store.list_collections())}


# ---------------------------------------------------------------- export jobs

_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = threading.Lock()
_MAX_JOBS = 20


def _job_view(job: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in job.items() if not k.startswith("_")}


@router.get("/exports/{job_id}")
async def get_export(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Export job not found")
        return _job_view(job)


class CollectionExportRequest(BaseModel):
    format: str = "pdf"             # pdf | zip | both
    scale: float = 2.0
    pageNumbers: bool = False       # continuous across the collection, cover exempt
    episodeTitlePages: bool = True  # generated title page before each episode
    cover: bool = False             # generated collection cover as page 1


def _run_export(job: Dict[str, Any], col: Dict[str, Any], episodes, req: CollectionExportRequest,
                scale: float, base_name: str) -> None:
    def progress(done: int, total: int) -> None:
        with _jobs_lock:
            job["done"], job["total"] = done, total
    try:
        result = collection_export.export_collection(
            col, episodes, req.format, scale, _resolver, _exports_dir(), base_name,
            page_numbers=req.pageNumbers,
            episode_title_pages=req.episodeTitlePages,
            cover=req.cover, progress=progress)
        with _jobs_lock:
            job["status"] = "done"
            job["done"] = result["pages"]
            for k in ("pdf", "zip"):
                if k in result:
                    job[k] = {"url": result[k]["url"],
                              "name": result[k]["url"].rsplit("/", 1)[-1]}
        logger.info("collection export %s done: %s (%d pages)", job["id"],
                    base_name, result["pages"])
    except Exception as e:
        logger.exception("collection export %s failed", job["id"])
        with _jobs_lock:
            job["status"] = "error"
            job["error"] = str(e) or e.__class__.__name__
    finally:
        with _jobs_lock:
            job["finishedAt"] = time.time()


@router.post("/{collection_id}/export")
async def export_collection(collection_id: str, req: CollectionExportRequest):
    col = _or_404(collection_id)
    if req.format not in ("pdf", "zip", "both"):
        raise HTTPException(status_code=400, detail="format must be pdf|zip|both")

    def load(pid: str):
        try:
            return storage.load_project(pid)
        except InvalidProjectIdError:
            return None
    episodes, warnings = collection_export.plan_episodes(col, load)
    if not episodes:
        raise HTTPException(status_code=400,
                            detail="collection has no episodes with pages to export")
    scale = min(8.0, max(0.5, req.scale))   # same bounds as /api/agent/export
    with _jobs_lock:
        if any(j["status"] == "running" for j in _jobs.values()):
            return JSONResponse(status_code=409, content={
                "detail": "another collection export is running"})
        finished = sorted((j for j in _jobs.values() if j["status"] != "running"),
                          key=lambda j: j.get("finishedAt") or 0)
        for j in finished[:max(0, len(_jobs) - _MAX_JOBS + 1)]:
            _jobs.pop(j["id"], None)
        base_name = f"collection_{col['id'][:8]}_{time.strftime('%Y%m%d_%H%M%S')}"
        job = {"id": uuid.uuid4().hex, "collectionId": col["id"],
               "status": "running", "done": 0,
               "total": collection_export.page_total(
                   episodes, req.cover, req.episodeTitlePages),
               "error": None, "warnings": warnings, "pdf": None, "zip": None,
               "format": req.format, "createdAt": time.time(), "finishedAt": None}
        _jobs[job["id"]] = job
    threading.Thread(target=_run_export, name=f"collection-export-{job['id'][:8]}",
                     args=(job, col, episodes, req, scale, base_name),
                     daemon=True).start()
    logger.info("collection export %s started: collection=%s fmt=%s pages=%d",
                job["id"], col["id"], req.format, job["total"])
    return JSONResponse(status_code=202, content=_job_view(job))


# ---------------------------------------------------------------- one collection

@router.get("/{collection_id}")
async def get_collection(collection_id: str):
    return {"collection": _summaries([_or_404(collection_id)])[0]}


class UpdateCollectionRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    projectIds: Optional[List[str]] = None   # full new order
    cover: Optional[Dict[str, Any]] = None   # {projectId, pageId}; send null to clear


@router.patch("/{collection_id}")
async def update_collection(collection_id: str, req: UpdateCollectionRequest):
    changes = req.model_dump(exclude_unset=True)
    try:
        col = store.update_collection(collection_id, changes)
    except store.CollectionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if col is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    return {"collection": _summaries([col])[0]}


@router.delete("/{collection_id}")
async def delete_collection(collection_id: str):
    """Delete the collection only; its projects are untouched."""
    if not store.delete_collection(collection_id):
        raise HTTPException(status_code=404, detail="Collection not found")
    return {"success": True}
