"""Headless page rendering endpoints.

Used by the agent pipeline (preview/export) and by the frontend export path
(Phase 4) so both share one renderer.
"""
import io
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from typing import List
from ..render import render_page
from ..render.export_service import export_pages_to_bytes
from ..render.resolve import make_resolver
from ..storage.asset_store import asset_store

router = APIRouter(prefix="/api/render", tags=["render"])
_resolver = make_resolver(asset_store)


class RenderPageRequest(BaseModel):
    page: dict
    scale: float = 2.0


@router.post("/page")
async def render_page_png(req: RenderPageRequest):
    scale = min(4.0, max(0.5, req.scale))
    img = render_page(req.page, scale, _resolver)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


class RenderExportRequest(BaseModel):
    pages: List[dict]
    format: str = "pdf"
    scale: float = 2.0


@router.post("/export")
async def render_export(req: RenderExportRequest):
    if not req.pages:
        raise HTTPException(status_code=400, detail="No pages provided")
    scale = min(4.0, max(0.5, req.scale))
    try:
        payload = export_pages_to_bytes(req.pages, req.format, scale, _resolver)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if req.format == "pdf":
        return Response(content=payload["pdf"], media_type="application/pdf",
                        headers={"Content-Disposition":
                                 'attachment; filename="manga.pdf"'})
    buf = io.BytesIO(payload["zip"])
    return Response(content=buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition":
                             'attachment; filename="manga.zip"'})
