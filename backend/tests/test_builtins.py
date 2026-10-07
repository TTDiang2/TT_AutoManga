"""Built-in composer template parity with the frontend source of truth."""
import re
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT.parent))

from backend.composer_builtins import (  # noqa: E402
    TEMPLATES, get_template, gen_rows, list_template_ids,
)

FRONTEND_STORE = (BACKEND_ROOT.parent / "frontend" / "src" / "store"
                  / "composerStore.ts")

# ids transcribed from frontend/src/store/composerStore.ts TEMPLATES (L65-226)
FRONTEND_IDS = [
    "blank", "manga-2v", "manga-2h", "manga-3", "manga-4", "manga-6",
    "manga-8", "grid-12", "grid-21", "grid-23", "grid-32", "grid-232",
    "grid-323", "grid-223", "hero-br-4", "hero-br-wide", "hero-splash",
    "photo-full", "photo-grid-4", "photo-grid-9",
]


def test_id_set_matches_frontend():
    assert sorted(list_template_ids()) == sorted(FRONTEND_IDS)


def test_frontend_source_still_has_these_ids():
    """Guard against frontend template drift: every backend id must appear
    in the frontend source, and vice versa."""
    src = FRONTEND_STORE.read_text(encoding="utf-8")
    m = re.search(r"const TEMPLATES: ComposerTemplate\[\] = \[", src)
    assert m, "TEMPLATES block not found in composerStore.ts"
    block = src[m.start():src.find("export { TEMPLATES }")]
    fe_ids = set(re.findall(r"id: '([a-z0-9-]+)'", block))
    assert fe_ids == set(FRONTEND_IDS)


def test_get_template_returns_copy():
    t1 = get_template("manga-4")
    t1["elements"][0]["x"] = 999
    t2 = get_template("manga-4")
    assert t2["elements"][0]["x"] != 999


def test_manga4_geometry():
    t = get_template("manga-4")
    assert t["width"] == 600 and t["height"] == 900
    assert len(t["elements"]) == 4
    s = t["elements"][0]
    # genRows([2,2], margin 2, gap 2): row_h = 47, col_w = 47
    assert s["x"] == 2 and s["y"] == 2 and s["width"] == 47 and s["height"] == 47
    last = t["elements"][3]
    assert last["x"] == 51 and last["y"] == 51


def test_gen_rows_counts():
    assert len(gen_rows([2, 3])) == 5
    assert len(gen_rows([1])) == 1
    assert [int(e["label"]) for e in gen_rows([2, 3])] == [1, 2, 3, 4, 5]


def test_blank_template_empty():
    assert get_template("blank")["elements"] == []
