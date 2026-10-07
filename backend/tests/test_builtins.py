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


def test_split_dialogue_ellipsis_runs():
    """…… must not split mid-ellipsis into a junk '…' bubble."""
    from backend.assembly import split_dialogue
    parts = split_dialogue("时辰点数，由我说了算……")
    assert parts == ["时辰点数，由我说了算……"], parts
    parts = split_dialogue("别过来！你走吧……就这样。")
    assert parts == ["别过来！", "你走吧……", "就这样。"], parts


def test_vertical_bubble_size_fits_text():
    """Vertical bubble width must scale with column count (no overflow)."""
    from backend.assembly import _make_bubble
    page = {"width": 600, "height": 900}
    slot = {"x": 51, "y": 2, "width": 47, "height": 31}
    long_b = _make_bubble("明日午时若不下雨我便砸了你这卦摊", slot, page, 0, {})
    short_b = _make_bubble("哼！", slot, page, 0, {})
    # long text -> wider (more columns); short text -> narrow single column
    assert long_b["width"] > short_b["width"] * 1.5, (long_b["width"], short_b["width"])
    assert long_b["width"] <= slot["width"] * 0.95
    assert short_b["width"] < 12  # single column + padding
    # text must fit inside the estimated columns at 1x pixels
    fs = 14
    col_cap = int((long_b["height"] / 100 * 900 - 20) // (fs * 1.3))
    assert -(-len(long_b["text"]) // col_cap) * fs * 1.3 + 20 <= \
        long_b["width"] / 100 * 600 + 1
