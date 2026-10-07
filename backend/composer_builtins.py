"""Built-in composer templates, transcribed from
frontend/src/store/composerStore.ts (TEMPLATES + genRows).

The frontend keeps its own copy; this module is the backend source of truth
for the agent pipeline. A test asserts the id set matches the frontend file.

Element shape mirrors the frontend's ComposerTemplate.elements: image-slots
with percentage x/y/width/height, rotation and a numeric label. zIndex /
locked / visible / id are added by the assembly layer (build_page).
"""
from typing import List, Optional


def gen_rows(rows: List[int], margin: float = 2.0, gap: float = 2.0,
             label_start: int = 1) -> List[dict]:
    """Port of genRows(): each number = column count of that row."""
    n = len(rows)
    row_h = (100 - 2 * margin - (n - 1) * gap) / n
    out, idx, y = [], label_start, margin
    for cols in rows:
        col_w = (100 - 2 * margin - (cols - 1) * gap) / cols
        x = margin
        for _ in range(cols):
            out.append({"type": "image-slot",
                        "x": round(x, 2), "y": round(y, 2),
                        "width": round(col_w, 2), "height": round(row_h, 2),
                        "rotation": 0, "label": str(idx)})
            x += col_w + gap
            idx += 1
        y += row_h + gap
    return out


def _slot(x, y, w, h, label) -> dict:
    return {"type": "image-slot", "x": x, "y": y, "width": w, "height": h,
            "rotation": 0, "label": label}


TEMPLATES: List[dict] = [
    {"id": "blank", "name": "Blank", "nameZh": "空白页",
     "width": 600, "height": 900, "elements": []},
    {"id": "manga-2v", "name": "Manga 2V", "nameZh": "漫画 2竖",
     "width": 600, "height": 900, "elements": gen_rows([1, 1])},
    {"id": "manga-2h", "name": "Manga 2H", "nameZh": "漫画 2横",
     "width": 600, "height": 900, "elements": gen_rows([2])},
    {"id": "manga-3", "name": "Manga 3", "nameZh": "漫画 3格",
     "width": 600, "height": 900, "elements": gen_rows([1, 2])},
    {"id": "manga-4", "name": "Manga 4", "nameZh": "漫画 4格",
     "width": 600, "height": 900, "elements": gen_rows([2, 2])},
    {"id": "manga-6", "name": "Manga 6", "nameZh": "漫画 6格",
     "width": 600, "height": 900, "elements": gen_rows([2, 2, 2])},
    {"id": "manga-8", "name": "Manga 8", "nameZh": "漫画 8格",
     "width": 600, "height": 900, "elements": gen_rows([4, 4])},
    {"id": "grid-12", "name": "Grid 1+2", "nameZh": "1+2 布局",
     "width": 600, "height": 900, "elements": gen_rows([1, 2])},
    {"id": "grid-21", "name": "Grid 2+1", "nameZh": "2+1 布局",
     "width": 600, "height": 900, "elements": gen_rows([2, 1])},
    {"id": "grid-23", "name": "Grid 2+3", "nameZh": "2+3 布局",
     "width": 600, "height": 900, "elements": gen_rows([2, 3])},
    {"id": "grid-32", "name": "Grid 3+2", "nameZh": "3+2 布局",
     "width": 600, "height": 900, "elements": gen_rows([3, 2])},
    {"id": "grid-232", "name": "Grid 2+3+2", "nameZh": "2+3+2 布局",
     "width": 600, "height": 900, "elements": gen_rows([2, 3, 2])},
    {"id": "grid-323", "name": "Grid 3+2+3", "nameZh": "3+2+3 布局",
     "width": 600, "height": 900, "elements": gen_rows([3, 2, 3])},
    {"id": "grid-223", "name": "Grid 2+2+3", "nameZh": "2+2+3 布局",
     "width": 600, "height": 900, "elements": gen_rows([2, 2, 3])},
    {"id": "hero-br-4", "name": "Hero BR", "nameZh": "强调·右下大",
     "width": 600, "height": 900, "elements": [
         _slot(2, 2, 30, 47, "1"), _slot(34, 2, 30, 47, "2"),
         _slot(2, 51, 30, 47, "3"), _slot(34, 51, 64, 47, "4")]},
    {"id": "hero-br-wide", "name": "Hero BR Wide", "nameZh": "强调·右下宽",
     "width": 600, "height": 900, "elements": [
         _slot(2, 2, 96, 30, "1"), _slot(2, 34, 30, 64, "2"),
         _slot(34, 34, 64, 64, "3")]},
    {"id": "hero-splash", "name": "Hero Splash", "nameZh": "强调·大特写",
     "width": 600, "height": 900, "elements": [
         _slot(2, 2, 30, 30, "1"), _slot(34, 2, 30, 30, "2"),
         _slot(66, 2, 32, 30, "3"), _slot(2, 34, 30, 64, "4"),
         _slot(34, 34, 64, 64, "5")]},
    {"id": "photo-full", "name": "Photo Full", "nameZh": "写真全幅",
     "width": 600, "height": 900, "elements": gen_rows([1])},
    {"id": "photo-grid-4", "name": "Photo Grid 4", "nameZh": "写真 4格",
     "width": 600, "height": 900, "elements": gen_rows([2, 2])},
    {"id": "photo-grid-9", "name": "Photo Grid 9", "nameZh": "写真 9格",
     "width": 600, "height": 900, "elements": gen_rows([3, 3, 3])},
]

_BY_ID = {t["id"]: t for t in TEMPLATES}


def get_template(template_id: str) -> Optional[dict]:
    """Return a deep-ish copy of the template (fresh element dicts)."""
    t = _BY_ID.get(template_id)
    if not t:
        return None
    return {**t, "elements": [dict(e) for e in t["elements"]]}


def list_template_ids() -> List[str]:
    return [t["id"] for t in TEMPLATES]
