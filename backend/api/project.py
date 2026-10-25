from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from ..storage.manager import storage, InvalidProjectIdError

router = APIRouter(prefix="/api/projects", tags=["projects"])


class Project(BaseModel):
    id: Optional[str] = None
    name: str
    panels: List[Dict[str, Any]] = []
    settings: Dict[str, Any] = {}
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None
    composerPages: List[Dict[str, Any]] = []


@router.get("/")
async def list_projects():
    try:
        projects = storage.list_projects()
        return {"projects": projects}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/save")
async def save_project(project: Project):
    try:
        data = project.model_dump()
        # Data-loss guard: the composer autosave historically posted
        # panels: [] / settings: {detailLevel} for projects whose storyboard
        # was written by the agent API, wiping them on disk. When a save
        # carries an empty panel list while the stored project has panels,
        # the sender is not managing the storyboard — keep the stored one.
        # (A UI user deleting every panel goes through the storyboard store,
        # which sends the real list; the empty-list case is legacy clients.)
        existing = storage.load_project(project.id) if project.id else None
        if not data.get("panels") and existing and existing.get("panels"):
            data["panels"] = existing["panels"]
        if existing:
            # settings are independent keys (UI edits detailLevel, the agent
            # writes style/characters/locations/bible): merge, never replace
            data["settings"] = {**existing.get("settings", {}),
                                **(data.get("settings") or {})}
        result = storage.save_project(data)
        return {"success": True, "project": result}
    except InvalidProjectIdError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/load/{project_id}")
async def load_project(project_id: str):
    try:
        project = storage.load_project(project_id)
        if project:
            return {"project": project}
        raise HTTPException(status_code=404, detail="Project not found")
    except InvalidProjectIdError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/covers")
async def list_project_covers():
    try:
        projects = storage.list_projects()
        covers = {}
        for proj in projects:
            if proj.get("composerPages"):
                first_page = proj["composerPages"][0]
                for el in first_page.get("elements", []):
                    if el.get("type") == "image" and el.get("src"):
                        covers[proj["id"]] = el["src"]
                        break
        return {"covers": covers}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{project_id}/migrate-assets")
async def migrate_project_assets(project_id: str):
    try:
        project = storage.load_project(project_id)
    except InvalidProjectIdError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    saved = storage.save_project(project)   # save_project normalizes embedded images
    return {"success": True, "project": saved}


@router.delete("/delete/{project_id}")
async def delete_project(project_id: str):
    try:
        success = storage.delete_project(project_id)
        if success:
            return {"success": True}
        raise HTTPException(status_code=404, detail="Project not found")
    except InvalidProjectIdError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
