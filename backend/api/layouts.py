from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path
import json
import logging

router = APIRouter(prefix="/api/layouts", tags=["layouts"])

LAYOUTS_FILE = Path(__file__).parent.parent.parent / "data" / "layouts.json"

LAYOUTS_FILE.parent.mkdir(parents=True, exist_ok=True)

DEFAULT_LAYOUTS = [
    {"id": "single", "name": "Single Panel", "canvas": {"width": 600, "height": 900}, "panels": [{"id": "p1", "x": 0, "y": 0, "width": 100, "height": 100}], "is_preset": True},
    {"id": "double-v", "name": "2 Panel (Vertical)", "canvas": {"width": 600, "height": 900}, "panels": [{"id": "p1", "x": 0, "y": 0, "width": 50, "height": 100}, {"id": "p2", "x": 50, "y": 0, "width": 50, "height": 100}], "is_preset": True},
    {"id": "double-h", "name": "2 Panel (Horizontal)", "canvas": {"width": 600, "height": 900}, "panels": [{"id": "p1", "x": 0, "y": 0, "width": 100, "height": 50}, {"id": "p2", "x": 0, "y": 50, "width": 100, "height": 50}], "is_preset": True},
    {"id": "triple", "name": "3 Panel", "canvas": {"width": 600, "height": 900}, "panels": [{"id": "p1", "x": 0, "y": 0, "width": 100, "height": 34}, {"id": "p2", "x": 0, "y": 34, "width": 50, "height": 33}, {"id": "p3", "x": 50, "y": 34, "width": 50, "height": 33}], "is_preset": True},
    {"id": "quad", "name": "4 Panel Grid", "canvas": {"width": 600, "height": 900}, "panels": [{"id": "p1", "x": 0, "y": 0, "width": 50, "height": 50}, {"id": "p2", "x": 50, "y": 0, "width": 50, "height": 50}, {"id": "p3", "x": 0, "y": 50, "width": 50, "height": 50}, {"id": "p4", "x": 50, "y": 50, "width": 50, "height": 50}], "is_preset": True},
    {"id": "manga", "name": "Manga (R-L)", "canvas": {"width": 600, "height": 900}, "panels": [{"id": "p1", "x": 50, "y": 0, "width": 50, "height": 50}, {"id": "p2", "x": 0, "y": 0, "width": 50, "height": 50}, {"id": "p3", "x": 50, "y": 50, "width": 50, "height": 50}, {"id": "p4", "x": 0, "y": 50, "width": 50, "height": 34}, {"id": "p5", "x": 0, "y": 84, "width": 100, "height": 16}], "is_preset": True},
    {"id": "5-vertical", "name": "5 Panel (Vertical)", "canvas": {"width": 600, "height": 900}, "panels": [{"id": "p1", "x": 0, "y": 0, "width": 100, "height": 20}, {"id": "p2", "x": 0, "y": 20, "width": 100, "height": 20}, {"id": "p3", "x": 0, "y": 40, "width": 100, "height": 20}, {"id": "p4", "x": 0, "y": 60, "width": 100, "height": 20}, {"id": "p5", "x": 0, "y": 80, "width": 100, "height": 20}], "is_preset": True},
    {"id": "5-manga", "name": "5 Panel Manga", "canvas": {"width": 600, "height": 900}, "panels": [{"id": "p1", "x": 0, "y": 0, "width": 50, "height": 50}, {"id": "p2", "x": 50, "y": 0, "width": 50, "height": 50}, {"id": "p3", "x": 0, "y": 50, "width": 33, "height": 50}, {"id": "p4", "x": 33, "y": 50, "width": 34, "height": 50}, {"id": "p5", "x": 67, "y": 50, "width": 33, "height": 50}], "is_preset": True},
    {"id": "6-grid", "name": "6 Panel Grid", "canvas": {"width": 600, "height": 900}, "panels": [{"id": "p1", "x": 0, "y": 0, "width": 33, "height": 33}, {"id": "p2", "x": 33, "y": 0, "width": 34, "height": 33}, {"id": "p3", "x": 67, "y": 0, "width": 33, "height": 33}, {"id": "p4", "x": 0, "y": 33, "width": 33, "height": 34}, {"id": "p5", "x": 33, "y": 33, "width": 34, "height": 34}, {"id": "p6", "x": 67, "y": 33, "width": 33, "height": 34}], "is_preset": True},
    {"id": "6-manga-classic", "name": "6 Manga Classic", "canvas": {"width": 600, "height": 900}, "panels": [{"id": "p1", "x": 0, "y": 0, "width": 50, "height": 33}, {"id": "p2", "x": 50, "y": 0, "width": 50, "height": 33}, {"id": "p3", "x": 0, "y": 33, "width": 50, "height": 33}, {"id": "p4", "x": 50, "y": 33, "width": 50, "height": 33}, {"id": "p5", "x": 0, "y": 66, "width": 50, "height": 34}, {"id": "p6", "x": 50, "y": 66, "width": 50, "height": 34}], "is_preset": True},
    {"id": "6-manga-tategae", "name": "6 Manga Tategae", "canvas": {"width": 600, "height": 900}, "panels": [{"id": "p1", "x": 0, "y": 0, "width": 100, "height": 16}, {"id": "p2", "x": 0, "y": 16, "width": 100, "height": 16}, {"id": "p3", "x": 0, "y": 32, "width": 100, "height": 16}, {"id": "p4", "x": 0, "y": 48, "width": 100, "height": 16}, {"id": "p5", "x": 0, "y": 64, "width": 100, "height": 16}, {"id": "p6", "x": 0, "y": 80, "width": 100, "height": 20}], "is_preset": True},
    {"id": "7-manga", "name": "7 Panel Manga", "canvas": {"width": 600, "height": 900}, "panels": [{"id": "p1", "x": 0, "y": 0, "width": 50, "height": 40}, {"id": "p2", "x": 50, "y": 0, "width": 50, "height": 40}, {"id": "p3", "x": 0, "y": 40, "width": 33, "height": 30}, {"id": "p4", "x": 33, "y": 40, "width": 34, "height": 30}, {"id": "p5", "x": 67, "y": 40, "width": 33, "height": 30}, {"id": "p6", "x": 0, "y": 70, "width": 50, "height": 30}, {"id": "p7", "x": 50, "y": 70, "width": 50, "height": 30}], "is_preset": True},
    {"id": "8-grid", "name": "8 Panel Grid", "canvas": {"width": 600, "height": 900}, "panels": [{"id": "p1", "x": 0, "y": 0, "width": 25, "height": 25}, {"id": "p2", "x": 25, "y": 0, "width": 25, "height": 25}, {"id": "p3", "x": 50, "y": 0, "width": 25, "height": 25}, {"id": "p4", "x": 75, "y": 0, "width": 25, "height": 25}, {"id": "p5", "x": 0, "y": 25, "width": 25, "height": 25}, {"id": "p6", "x": 25, "y": 25, "width": 25, "height": 25}, {"id": "p7", "x": 50, "y": 25, "width": 25, "height": 25}, {"id": "p8", "x": 75, "y": 25, "width": 25, "height": 25}], "is_preset": True},
    {"id": "8-manga", "name": "8 Manga Layout", "canvas": {"width": 600, "height": 900}, "panels": [{"id": "p1", "x": 0, "y": 0, "width": 66, "height": 40}, {"id": "p2", "x": 66, "y": 0, "width": 34, "height": 40}, {"id": "p3", "x": 0, "y": 40, "width": 33, "height": 20}, {"id": "p4", "x": 33, "y": 40, "width": 33, "height": 20}, {"id": "p5", "x": 66, "y": 40, "width": 34, "height": 20}, {"id": "p6", "x": 0, "y": 60, "width": 50, "height": 20}, {"id": "p7", "x": 50, "y": 60, "width": 50, "height": 20}, {"id": "p8", "x": 0, "y": 80, "width": 100, "height": 20}], "is_preset": True},
    {"id": "album-3x3", "name": "Album 3×3", "canvas": {"width": 600, "height": 900}, "panels": [{"id": "p1", "x": 0, "y": 0, "width": 33, "height": 33}, {"id": "p2", "x": 33, "y": 0, "width": 34, "height": 33}, {"id": "p3", "x": 66, "y": 0, "width": 34, "height": 33}, {"id": "p4", "x": 0, "y": 33, "width": 33, "height": 34}, {"id": "p5", "x": 33, "y": 33, "width": 34, "height": 34}, {"id": "p6", "x": 66, "y": 33, "width": 34, "height": 34}, {"id": "p7", "x": 0, "y": 67, "width": 33, "height": 33}, {"id": "p8", "x": 33, "y": 67, "width": 34, "height": 33}, {"id": "p9", "x": 66, "y": 67, "width": 34, "height": 33}], "is_preset": True},
    {"id": "album-2x3", "name": "Album 2×3", "canvas": {"width": 600, "height": 900}, "panels": [{"id": "p1", "x": 0, "y": 0, "width": 50, "height": 33}, {"id": "p2", "x": 50, "y": 0, "width": 50, "height": 33}, {"id": "p3", "x": 0, "y": 33, "width": 50, "height": 34}, {"id": "p4", "x": 50, "y": 33, "width": 50, "height": 34}, {"id": "p5", "x": 0, "y": 67, "width": 50, "height": 33}, {"id": "p6", "x": 50, "y": 67, "width": 50, "height": 33}], "is_preset": True},
    {"id": "album-4x4", "name": "Album 4×4", "canvas": {"width": 600, "height": 900}, "panels": [{"id": "p1", "x": 0, "y": 0, "width": 25, "height": 25}, {"id": "p2", "x": 25, "y": 0, "width": 25, "height": 25}, {"id": "p3", "x": 50, "y": 0, "width": 25, "height": 25}, {"id": "p4", "x": 75, "y": 0, "width": 25, "height": 25}, {"id": "p5", "x": 0, "y": 25, "width": 25, "height": 25}, {"id": "p6", "x": 25, "y": 25, "width": 25, "height": 25}, {"id": "p7", "x": 50, "y": 25, "width": 25, "height": 25}, {"id": "p8", "x": 75, "y": 25, "width": 25, "height": 25}, {"id": "p9", "x": 0, "y": 50, "width": 25, "height": 25}, {"id": "p10", "x": 25, "y": 50, "width": 25, "height": 25}, {"id": "p11", "x": 50, "y": 50, "width": 25, "height": 25}, {"id": "p12", "x": 75, "y": 50, "width": 25, "height": 25}, {"id": "p13", "x": 0, "y": 75, "width": 25, "height": 25}, {"id": "p14", "x": 25, "y": 75, "width": 25, "height": 25}, {"id": "p15", "x": 50, "y": 75, "width": 25, "height": 25}, {"id": "p16", "x": 75, "y": 75, "width": 25, "height": 25}], "is_preset": True},
    {"id": "album-1large-2small", "name": "Album 1+2", "canvas": {"width": 600, "height": 900}, "panels": [{"id": "p1", "x": 0, "y": 0, "width": 66, "height": 100}, {"id": "p2", "x": 66, "y": 0, "width": 34, "height": 50}, {"id": "p3", "x": 66, "y": 50, "width": 34, "height": 50}], "is_preset": True},
    {"id": "album-2large-4small", "name": "Album 2+4", "canvas": {"width": 600, "height": 900}, "panels": [{"id": "p1", "x": 0, "y": 0, "width": 50, "height": 50}, {"id": "p2", "x": 50, "y": 0, "width": 50, "height": 50}, {"id": "p3", "x": 0, "y": 50, "width": 25, "height": 25}, {"id": "p4", "x": 25, "y": 50, "width": 25, "height": 25}, {"id": "p5", "x": 50, "y": 50, "width": 25, "height": 25}, {"id": "p6", "x": 75, "y": 50, "width": 25, "height": 25}], "is_preset": True},
    {"id": "album-mosaic", "name": "Album Mosaic", "canvas": {"width": 600, "height": 900}, "panels": [{"id": "p1", "x": 0, "y": 0, "width": 50, "height": 40}, {"id": "p2", "x": 50, "y": 0, "width": 50, "height": 40}, {"id": "p3", "x": 0, "y": 40, "width": 33, "height": 30}, {"id": "p4", "x": 33, "y": 40, "width": 34, "height": 30}, {"id": "p5", "x": 67, "y": 40, "width": 33, "height": 30}, {"id": "p6", "x": 0, "y": 70, "width": 25, "height": 30}, {"id": "p7", "x": 25, "y": 70, "width": 50, "height": 30}, {"id": "p8", "x": 75, "y": 70, "width": 25, "height": 30}], "is_preset": True},
    {"id": "album-1vertical-3horizontal", "name": "Album 1+3 Strip", "canvas": {"width": 600, "height": 900}, "panels": [{"id": "p1", "x": 0, "y": 0, "width": 25, "height": 100}, {"id": "p2", "x": 25, "y": 0, "width": 75, "height": 25}, {"id": "p3", "x": 25, "y": 25, "width": 75, "height": 25}, {"id": "p4", "x": 25, "y": 50, "width": 75, "height": 25}, {"id": "p5", "x": 25, "y": 75, "width": 75, "height": 25}], "is_preset": True},
    {"id": "splash-page", "name": "Splash Page", "canvas": {"width": 600, "height": 900}, "panels": [{"id": "p1", "x": 0, "y": 0, "width": 100, "height": 100}], "is_preset": True},
    {"id": "splash-2strip", "name": "Splash + 2 Strip", "canvas": {"width": 600, "height": 900}, "panels": [{"id": "p1", "x": 0, "y": 0, "width": 100, "height": 60}, {"id": "p2", "x": 0, "y": 60, "width": 50, "height": 20}, {"id": "p3", "x": 50, "y": 60, "width": 50, "height": 20}], "is_preset": True},
    {"id": "splash-3strip", "name": "Splash + 3 Strip", "canvas": {"width": 600, "height": 900}, "panels": [{"id": "p1", "x": 0, "y": 0, "width": 100, "height": 60}, {"id": "p2", "x": 0, "y": 60, "width": 33, "height": 20}, {"id": "p3", "x": 33, "y": 60, "width": 34, "height": 20}, {"id": "p4", "x": 67, "y": 60, "width": 33, "height": 20}], "is_preset": True},
    {"id": "2-1-2", "name": "2-1-2 Layout", "canvas": {"width": 600, "height": 900}, "panels": [{"id": "p1", "x": 0, "y": 0, "width": 25, "height": 100}, {"id": "p2", "x": 25, "y": 0, "width": 50, "height": 50}, {"id": "p3", "x": 25, "y": 50, "width": 50, "height": 50}, {"id": "p4", "x": 75, "y": 0, "width": 25, "height": 100}], "is_preset": True},
    {"id": "magazine", "name": "Magazine", "canvas": {"width": 600, "height": 900}, "panels": [{"id": "p1", "x": 0, "y": 0, "width": 60, "height": 60}, {"id": "p2", "x": 60, "y": 0, "width": 40, "height": 30}, {"id": "p3", "x": 60, "y": 30, "width": 40, "height": 30}, {"id": "p4", "x": 0, "y": 60, "width": 40, "height": 40}, {"id": "p5", "x": 40, "y": 60, "width": 60, "height": 20}, {"id": "p6", "x": 40, "y": 80, "width": 60, "height": 20}], "is_preset": True},
]


class PanelDefinition(BaseModel):
    id: str
    x: float
    y: float
    width: float
    height: float


class CanvasDefinition(BaseModel):
    width: int
    height: int


class LayoutDefinition(BaseModel):
    id: str
    name: str
    canvas: CanvasDefinition
    panels: List[PanelDefinition]
    is_preset: bool = False


def load_layouts() -> List[dict]:
    if LAYOUTS_FILE.exists():
        try:
            with open(LAYOUTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.warning("layouts file unreadable (%s); using built-in layouts", e)
    return [l for l in DEFAULT_LAYOUTS]


def save_layouts(layouts: List[dict]) -> None:
    with open(LAYOUTS_FILE, "w", encoding="utf-8") as f:
        json.dump(layouts, f, indent=2)


@router.get("/")
async def get_layouts():
    return load_layouts()


@router.post("/")
async def create_layout(layout: LayoutDefinition):
    layouts = load_layouts()
    if any(l["id"] == layout.id for l in layouts):
        raise HTTPException(status_code=400, detail="Layout ID already exists")
    layouts.append(layout.model_dump())
    save_layouts(layouts)
    return {"success": True, "id": layout.id}


@router.put("/{layout_id}")
async def update_layout(layout_id: str, layout: LayoutDefinition):
    layouts = load_layouts()
    for i, l in enumerate(layouts):
        if l["id"] == layout_id:
            if l.get("is_preset"):
                raise HTTPException(status_code=400, detail="Cannot modify preset layouts")
            layouts[i] = layout.model_dump()
            save_layouts(layouts)
            return {"success": True}
    raise HTTPException(status_code=404, detail="Layout not found")


@router.delete("/{layout_id}")
async def delete_layout(layout_id: str):
    layouts = load_layouts()
    for l in layouts:
        if l["id"] == layout_id:
            if l.get("is_preset"):
                raise HTTPException(status_code=400, detail="Cannot delete preset layouts")
            layouts.remove(l)
            save_layouts(layouts)
            return {"success": True}
    raise HTTPException(status_code=404, detail="Layout not found")
