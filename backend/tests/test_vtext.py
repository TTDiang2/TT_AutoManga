"""Native CJK vertical typesetting + lettering discipline rules."""
import math

from backend.assembly import _apply_dynamic_corners, _make_bubble, classify_bubble
from backend.render.vtext import CHAR_ADV, COL_ADV, layout_vertical, to_vertical_punctuation


# ---------------------------------------------------------------- balancing

def test_columns_balanced_no_orphans():
    # 10 glyphs, capacity 4 -> 3 columns of [4, 3, 3], not [4, 4, 2]... and
    # never a 1-2 glyph orphan column when a balanced split exists
    pos, ext = layout_vertical("一二三四五六七八九十", 200, 200, 10, 20)
    heights = [round(y1 - y0, 5) for _, _, y0, y1 in ext]
    assert max(heights) - min(heights) <= CHAR_ADV * 20 * 1.01 + 1e-6
    assert min(heights) >= 3 * CHAR_ADV * 20 - 1e-6


def test_single_glyph_line():
    pos, ext = layout_vertical("好", 100, 100, 10, 20)
    assert len(pos) == 1 and len(ext) == 1
    assert abs(ext[0][2] - (100 - CHAR_ADV * 20) / 2) < 1e-6  # centered


def test_capacity_respects_box_height():
    # tall box -> fewer columns; the whole line can sit in one column
    n = 12
    fs = 20.0
    tall_h = int((n + 2) * fs * CHAR_ADV) + 40
    _, ext_tall = layout_vertical("字" * n, 200, tall_h, 10, fs)
    assert len(ext_tall) == 1
    short_h = 110  # (110-20)//21.2 == 4 glyphs per column
    capacity = int((short_h - 2 * 10) // (fs * CHAR_ADV))
    _, ext_short = layout_vertical("字" * n, 200, short_h, 10, fs)
    assert len(ext_short) == math.ceil(n / capacity)


def test_first_column_takes_remainder():
    # right-to-left reading: the FIRST (rightmost) column is the longest
    pos, ext = layout_vertical("一二三四五", 200, 4 * 21.2, 10, 20)
    xs = [x0 for x0, _, _, _ in ext]
    rightmost = max(range(len(ext)), key=lambda i: xs[i])
    leftmost = min(range(len(ext)), key=lambda i: xs[i])
    h_right = ext[rightmost][3] - ext[rightmost][2]
    h_left = ext[leftmost][3] - ext[leftmost][2]
    assert h_right >= h_left


# ------------------------------------------------------- vertical punctuation

def test_punctuation_maps_to_vertical_forms():
    out = to_vertical_punctuation("你好，世界！")
    assert "，" not in out and "！" not in out
    assert "\uFE10" in out and "\uFE15" in out


def test_punctuation_mapping_skipped_when_font_lacks_forms(monkeypatch):
    import backend.render.vtext as vt

    class FakeFont:
        path = "fake-no-forms.ttf"

    # stub a cmap that covers plain CJK but none of the U+FE10 forms
    monkeypatch.setitem(vt._cmap_cache, "fake-no-forms.ttf", {0x4F60: 1})
    out = vt.to_vertical_punctuation("你好，世界！", FakeFont())
    assert "，" in out and "\uFE10" not in out


def test_punctuation_maps_with_real_resolved_font():
    # regression for the P0 the review caught: maketrans().values() are strs,
    # cmap keys are ints — the mapping silently never applied with a font
    from backend.render.fonts import get_font
    font = get_font(20)   # msyh.ttc on this host — carries U+FE10 block
    out = to_vertical_punctuation("你好，世界！……", font)
    assert "\uFE10" in out and "\uFE15" in out and "\uFE19" in out


# --------------------------------------------------- lettering discipline

def test_classify_bubble_always_speech():
    assert classify_bubble("饶命！！") == "speech"
    assert classify_bubble("还我命来——！") == "speech"
    assert classify_bubble("（内心独白）……") == "speech"


def test_make_bubble_metrics_match_vtext():
    page = {"width": 600, "height": 900}
    slot = {"x": 2, "y": 2, "width": 47, "height": 47}
    text = "每日一尾金色鲤鱼"          # 8 glyphs
    el = _make_bubble(text, slot, page, 0, {}, shot=None)
    assert el["bubbleType"] == "speech" and el["direction"] == "vertical"
    fs = el["fontSize"]
    # box must hold ceil(8/3)=3 glyphs per column at the shared metrics
    inner_h = el["height"] / 100 * page["height"] - 2 * 10
    capacity = int(inner_h // (fs * CHAR_ADV))
    assert capacity >= 3
    # width fits the estimated column count
    n_cols = max(1, math.ceil(len(text) / capacity))
    inner_w = el["width"] / 100 * page["width"] - 2 * 10
    assert inner_w >= n_cols * fs * COL_ADV * 0.98


def test_dynamic_corners_one_uniform_gesture():
    slots = [
        {"x": 2, "y": 2, "width": 96, "height": 44, "type": "image-slot"},   # hero
        {"x": 2, "y": 48, "width": 47, "height": 50, "type": "image-slot"},
        {"x": 51, "y": 48, "width": 47, "height": 50, "type": "image-slot"},
    ]
    _apply_dynamic_corners(slots)
    assert "corners" not in slots[0]                      # hero untouched
    assert slots[1]["corners"] == slots[2]["corners"]     # one shared pattern
    c = slots[1]["corners"]
    assert abs(c["tl"]["x"] - (100 - c["tr"]["x"])) < 1e-9  # symmetric inset
    assert c["br"]["y"] == c["bl"]["y"] == 100              # bottom stays put
    assert 0 < c["tl"]["x"] < 50 and 50 < c["tr"]["x"] < 100
