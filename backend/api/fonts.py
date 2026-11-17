"""User fonts (data/fonts/) for the browser, so the Composer shows text in
the same fonts the server renderer uses.

A font's family is its file name up to the first "-", lower-cased:
title-bebas.ttf → "title", default-letter-bold.ttf → "default". The server
renderer matches a requested family by substring of the file name, so an
element with fontFamily "title" renders with title-bebas.ttf in both places;
"default" is what unnamed text (all bubbles) uses (render/fonts.py).
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..render.fonts import _USER_FONT_DIR

router = APIRouter(prefix="/api/fonts", tags=["fonts"])

_TYPES = {".ttf": "font/ttf", ".otf": "font/otf", ".ttc": "font/collection"}


def _fonts():
    if not _USER_FONT_DIR.exists():
        return {}
    return {f.name: f for f in sorted(_USER_FONT_DIR.iterdir())
            if f.is_file() and f.suffix.lower() in _TYPES}


@router.get("")
async def list_fonts():
    return {"fonts": [{"family": name.split("-")[0].rsplit(".", 1)[0].lower(),
                       "file": name, "url": f"/api/fonts/file/{name}"}
                      for name in _fonts()]}


@router.get("/file/{name}")
async def font_file(name: str):
    path = _fonts().get(name)   # only files in the listing: no path from the request reaches the disk
    if not path:
        raise HTTPException(status_code=404, detail="font not found")
    return FileResponse(path, media_type=_TYPES[path.suffix.lower()],
                        headers={"Cache-Control": "max-age=3600"})
