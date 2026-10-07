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


def _slot_c(x, y, w, h, label, corners) -> dict:
    s = _slot(x, y, w, h, label)
    s["corners"] = corners
    return s


def _c(tl, tr, br, bl) -> dict:
    return {"tl": {"x": tl[0], "y": tl[1]}, "tr": {"x": tr[0], "y": tr[1]},
            "br": {"x": br[0], "y": br[1]}, "bl": {"x": bl[0], "y": bl[1]}}


# Dynamic layouts: mixed sizes and slanted (quadrilateral) frames for a more
# cinematic page. Backend-only presets for the agent pipeline (the frontend
# keeps its own copy of TEMPLATES).
DYNAMIC_TEMPLATES: List[dict] = [
    {"id": "dyn-2-slant", "name": "Dynamic 2 Slant", "nameZh": "动态·2格斜切",
     "width": 600, "height": 900, "elements": [
         _slot_c(2, 2, 96, 44, "1", _c((0, 0), (100, 0), (100, 90), (0, 100))),
         _slot_c(2, 48, 47, 50, "2", _c((0, 6), (100, 0), (100, 100), (0, 100))),
         _slot_c(51, 48, 47, 50, "3", _c((0, 0), (100, 6), (100, 100), (0, 94)))]},
    {"id": "dyn-3-diag", "name": "Dynamic 3 Diagonal", "nameZh": "动态·斜阶3+1",
     "width": 600, "height": 900, "elements": [
         _slot_c(2, 2, 30, 28, "1", _c((0, 0), (100, 6), (94, 100), (0, 90))),
         _slot_c(34, 18, 30, 28, "2", _c((6, 8), (100, 0), (100, 92), (8, 100))),
         _slot_c(66, 34, 32, 28, "3", _c((8, 4), (100, 0), (100, 100), (0, 96))),
         _slot_c(2, 64, 96, 34, "4", _c((0, 0), (100, 0), (100, 96), (0, 100)))]},
    {"id": "dyn-hero-3", "name": "Dynamic Hero 3", "nameZh": "动态·主格+3",
     "width": 600, "height": 900, "elements": [
         _slot_c(2, 2, 60, 96, "1", _c((0, 4), (97, 0), (100, 96), (3, 100))),
         _slot_c(66, 2, 32, 30, "2", _c((0, 0), (100, 5), (100, 100), (5, 94))),
         _slot_c(66, 35, 32, 30, "3", _c((5, 5), (100, 0), (100, 95), (0, 100))),
         _slot_c(66, 68, 32, 30, "4", _c((0, 6), (96, 0), (100, 100), (0, 94)))]},
    {"id": "dyn-5-mix", "name": "Dynamic 5 Mix", "nameZh": "动态·5格混排",
     "width": 600, "height": 900, "elements": [
         _slot_c(2, 2, 96, 26, "1", _c((0, 0), (100, 0), (100, 92), (0, 100))),
         _slot_c(2, 31, 57, 34, "2", _c((0, 8), (100, 0), (100, 100), (0, 100))),
         _slot_c(61, 31, 37, 34, "3", _c((0, 0), (100, 8), (100, 100), (6, 96))),
         _slot_c(2, 68, 46, 30, "4", _c((0, 0), (100, 7), (98, 100), (0, 96))),
         _slot_c(50, 68, 48, 30, "5", _c((4, 7), (100, 0), (100, 100), (0, 96)))]},
]


def get_template(template_id: str) -> Optional[dict]:
    """Return a deep-ish copy of the template (fresh element dicts)."""
    t = _BY_ID.get(template_id)
    if not t:
        t = next((t for t in DYNAMIC_TEMPLATES if t["id"] == template_id), None)
    if not t:
        return None
    return {**t, "elements": [dict(e) for e in t["elements"]]}


def list_template_ids() -> List[str]:
    return [t["id"] for t in TEMPLATES] + [t["id"] for t in DYNAMIC_TEMPLATES]
