"""Headless page rendering endpoints.

Used by the agent pipeline (preview/export) and by the frontend export path
(Phase 4) so both share one renderer.
"""
import asyncio
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
    scale = min(8.0, max(0.5, req.scale))
    # PIL work runs in a worker thread so rendering never blocks the loop
    png = await asyncio.to_thread(_render_png, req.page, scale)
    return Response(content=png, media_type="image/png")


def _render_png(page: dict, scale: float) -> bytes:
    img = render_page(page, scale, _resolver)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class RenderExportRequest(BaseModel):
    pages: List[dict]
    format: str = "pdf"
    scale: float = 2.0
    page_numbers: bool = False


@router.post("/export")
async def render_export(req: RenderExportRequest):
    if not req.pages:
        raise HTTPException(status_code=400, detail="No pages provided")
    scale = min(8.0, max(0.5, req.scale))
    try:
        payload = await asyncio.to_thread(
            export_pages_to_bytes, req.pages, req.format, scale,
            _resolver, req.page_numbers)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if req.format == "pdf":
        return Response(content=payload["pdf"], media_type="application/pdf",
                        headers={"Content-Disposition":
                                 'attachment; filename="manga.pdf"'})
    return Response(content=payload["zip"], media_type="application/zip",
                    headers={"Content-Disposition":
                             'attachment; filename="manga.zip"'})
