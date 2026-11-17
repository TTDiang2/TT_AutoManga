"""Lettering fidelity: pointed tails (tailTip), textAlign, *emphasis* markup
and per-glyph font fallback. Direct render-function tests, no HTTP app."""
import json
import math
from pathlib import Path

import pytest
from fastapi import HTTPException
from PIL import Image, ImageChops

from backend.api.agent import _validate_element_payload
from backend.render import bubbles
from backend.render.fonts import get_font_chain
from backend.render.tails import tail_geometry

FIXTURE = Path(__file__).parent / "fixtures" / "tail_cases.json"


def _bubble(**kw):
    el = {"bubbleType": "speech", "text": "HI", "direction": "horizontal",
          "fontSize": 14, "backgroundColor": "#ffffff", "borderColor": "#000000",
          "tailPosition": "none"}
    el.update(kw)
    return el


def _dark(img: Image.Image):
    """Bounding box of dark (ink) pixels."""
    a = img.convert("RGBA")
    mask = Image.eval(a.convert("L"), lambda v: 255 if v < 100 else 0)
    mask = ImageChops.multiply(mask, a.getchannel("A").point(lambda v: 255 if v > 128 else 0))
    return mask.getbbox()


def test_tail_fixture_matches_python():
    for c in json.loads(FIXTURE.read_text())["cases"]:
        g = tail_geometry(c["bubbleType"], c["w"], c["h"], tuple(c["tip"]), c["inset"])
        exp = c["expect"]
        if exp is None:
            assert g is None
            continue
        assert g["kind"] == exp["kind"]
        if g["kind"] == "wedge":
            for k in ("p1", "p2", "ctrl", "tip"):
                assert all(abs(a - b) < 1e-4 for a, b in zip(g[k], exp[k])), (c, k)
        else:
            for got, want in zip(g["circles"], exp["circles"]):
                assert all(abs(a - b) < 1e-4 for a, b in zip(got, want))


def test_tail_tip_ink_at_projected_tip_and_pad_grows():
    ew, eh = 200, 100
    plain, pad0 = bubbles.draw_bubble(_bubble(), ew, eh, 1.0)
    img, pad = bubbles.draw_bubble(_bubble(tailTip={"x": 0.25, "y": 2.0}), ew, eh, 1.0)
    assert pad.bottom > pad0.bottom and pad.bottom >= eh   # tip is a full box height below
    # only the side the tail sticks out of grows
    assert (pad.left, pad.top, pad.right) == (pad0.left, pad0.top, pad0.right)
    assert img.size == (pad.left + ew + pad.right, pad.top + eh + pad.bottom)
    tx, ty = pad.left + 0.25 * ew, pad.top + 2.0 * eh
    bbox = _dark(img)
    assert bbox is not None
    # the lowest ink is the tip, within a few px of where it was projected
    assert abs(bbox[3] - ty) <= 4
    near = img.crop((int(tx) - 6, int(ty) - 12, int(tx) + 6, int(ty) + 2))
    assert _dark(near) is not None


def test_tail_tip_inside_body_draws_no_tail():
    a, _ = bubbles.draw_bubble(_bubble(), 200, 100, 1.0)
    b, _ = bubbles.draw_bubble(_bubble(tailTip={"x": 0.5, "y": 0.5}), 200, 100, 1.0)
    assert a.tobytes() == b.tobytes()


def test_thought_tail_is_circles_toward_tip():
    img, pad = bubbles.draw_bubble(_bubble(bubbleType="thought",
                                           tailTip={"x": 1.5, "y": 1.5}), 200, 100, 1.0)
    bbox = _dark(img)
    assert bbox[2] > pad.left + 200 + 10 and bbox[3] > pad.top + 100 + 10


def test_left_aligned_ink_starts_at_the_left():
    text = "A LONGER FIRST LINE\nSHORT"
    el = dict(bubbleType="narration", text=text)
    center, p = bubbles.draw_bubble(_bubble(**el), 400, 120, 1.0)
    pad = p.left            # narration: the same margin on every side
    left, _ = bubbles.draw_bubble(_bubble(textAlign="left", **el), 400, 120, 1.0)
    # look inside the box only (skip the 2px frame)
    inner = (pad + 6, pad + 6, pad + 394, pad + 114)
    lb, cb = _dark(left.crop(inner)), _dark(center.crop(inner))
    assert lb[0] < 10            # text starts at the padded left edge
    assert cb[0] > lb[0] + 40    # centred text started well to the right
    # the short second line starts where the first does
    row2 = (pad + 6, pad + 62, pad + 394, pad + 114)
    assert abs(_dark(left.crop(row2))[0] - lb[0]) <= 3


def test_note_glyph_falls_back_instead_of_notdef():
    chain = get_font_chain(40)
    assert chain.font_for("♪") is not None
    note, _ = bubbles.draw_bubble(_bubble(text="♪"), 200, 100, 1.0)
    tofu, _ = bubbles.draw_bubble(_bubble(text="\U000F0000"), 200, 100, 1.0)  # no font has it
    assert note.tobytes() != tofu.tobytes()
    if chain.covers(0x266A) and chain.font_for("♪") is not chain.primary:
        assert len(chain.runs("A♪B")) == 3


def test_emphasis_markup_changes_rendering_and_is_opt_in():
    star, _ = bubbles.draw_bubble(_bubble(text="*A*", markup="stars"), 200, 100, 1.0)
    plain, _ = bubbles.draw_bubble(_bubble(text="A"), 200, 100, 1.0)
    literal, _ = bubbles.draw_bubble(_bubble(text="*A*"), 200, 100, 1.0)
    assert star.tobytes() != plain.tobytes()      # sheared, not upright
    assert star.tobytes() != literal.tobytes()    # stars are not drawn
    # emphasis keeps the ink about where the plain letter is (no stars' width)
    sb, pb = _dark(star), _dark(plain)
    assert abs((sb[0] + sb[2]) / 2 - (pb[0] + pb[2]) / 2) < 8


def test_parse_stars():
    assert bubbles.parse_stars("a *bc* d") == ("a bc d", [False, False, True, True, False, False])
    assert bubbles.parse_stars("5 * 3")[0] == "5 * 3"


def test_rotated_bubble_with_tail_renders_via_page():
    from backend.render.renderer import render_page
    page = {"width": 300, "height": 300, "elements": [
        {"id": "b", "type": "bubble", "x": 30, "y": 10, "width": 40, "height": 20,
         "rotation": 20, "zIndex": 1, "visible": True, **_bubble(tailTip={"x": 0.2, "y": 3})}]}
    img = render_page(page, 1.0)
    assert _dark(img)[3] > 150    # the tail reaches far below the body


def test_validation_accepts_new_bubble_keys():
    _validate_element_payload({"type": "bubble", "tailTip": {"x": -0.4, "y": 2.5},
                               "textAlign": "left", "markup": "stars"})
    _validate_element_payload({"tailTip": None, "markup": None}, partial=True)
    _validate_element_payload({"textAlign": "justify"}, partial=True)   # text elements


@pytest.mark.parametrize("bad", [
    {"tailTip": {"x": 1}}, {"tailTip": {"x": "1", "y": 0}}, {"tailTip": [0, 1]},
    {"tailTip": {"x": 0, "y": math.inf}}, {"textAlign": "middle"}, {"markup": "html"},
    {"tailTip": {"x": 0, "y": 3.5}}, {"tailTip": {"x": -2.5, "y": 0}}, {"tailTip": {"x": 0, "y": 20}},
])
def test_validation_rejects_bad_bubble_keys(bad):
    with pytest.raises(HTTPException):
        _validate_element_payload(bad, partial=True)


def test_far_tail_tip_is_clamped_and_bounded():
    """A huge tailTip is clamped to TIP_LIMIT box sizes beyond the box, and
    only that side's margin grows; the local image stays under the cap."""
    ew, eh = 200, 100
    far, pf = bubbles.draw_bubble(_bubble(tailTip={"x": 0.5, "y": 1e6}), ew, eh, 1.0)
    edge, pe = bubbles.draw_bubble(_bubble(tailTip={"x": 0.5, "y": bubbles.TIP_MAX}), ew, eh, 1.0)
    assert far.tobytes() == edge.tobytes() and pf == pe
    assert pf.bottom <= (bubbles.TIP_MAX - 1) * eh + 10 and pf.top < 30
    big, pb = bubbles.draw_bubble(_bubble(tailTip={"x": -2, "y": 3}), 3000, 3000, 1.0)
    assert big.width * big.height <= bubbles.MAX_LOCAL_PIXELS


@pytest.mark.parametrize("size", [(0, 0), (1, 1), (3, 40), (40, 2), (4, 4)])
def test_tiny_bubbles_draw_nothing(size):
    assert bubbles.draw_bubble(_bubble(tailTip={"x": 0.5, "y": 2}), *size, 1.0) is None
    assert bubbles.draw_bubble(_bubble(bubbleType="shout"), *size, 1.0) is None


def test_tiny_bubble_on_a_page_renders():
    from backend.render.renderer import render_page
    page = {"width": 300, "height": 300, "elements": [
        {"id": "b", "type": "bubble", "x": 10, "y": 10, "width": 0.5, "height": 0.5,
         "rotation": 0, "zIndex": 1, "visible": True, **_bubble(tailTip={"x": 0.2, "y": 3})}]}
    render_page(page, 1.0)


def test_saved_pages_get_tail_tips_clamped(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.storage import manager as mgr
    monkeypatch.setattr(mgr, "PROJECTS_DIR", tmp_path)
    c = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))
    page = {"id": "pg", "elements": [
        {"id": "b", "type": "bubble", "tailTip": {"x": 50, "y": -40}},
        {"id": "c", "type": "bubble", "tailTip": {"x": "nan", "y": 1}}]}
    r = c.post("/api/projects/save", json={"id": "p1", "name": "p", "composerPages": [page]})
    assert r.status_code == 200, r.text
    els = r.json()["project"]["composerPages"][0]["elements"]
    assert els[0]["tailTip"] == {"x": bubbles.TIP_MAX, "y": bubbles.TIP_MIN}
    assert "tailTip" not in els[1]
    r = c.put("/api/projects/p1/composer-pages", json={"pages": [page]})
    assert r.status_code == 200, r.text
    stored = mgr.storage.load_project("p1")["composerPages"][0]["elements"]
    assert stored[0]["tailTip"] == {"x": bubbles.TIP_MAX, "y": bubbles.TIP_MIN}


def test_font_caches_are_bounded_and_shrink_in_whole_pixels(monkeypatch):
    from backend.render import fonts
    monkeypatch.setattr(fonts, "_cache", fonts._LRU(8))
    monkeypatch.setattr(fonts, "_chain_cache", fonts._LRU(4))
    for px in range(6, 60):
        fonts.get_font_chain(px + 0.37)
    assert len(fonts._cache) <= 8 and len(fonts._chain_cache) <= 4
    a = fonts.get_font_chain(30)
    assert fonts.get_font_chain(30.2) is a            # same whole-pixel key
    sizes = []
    real = bubbles._styled

    def spy(fs, bold):
        sizes.append(fs)
        return real(fs, bold)
    monkeypatch.setattr(bubbles, "_styled", spy)
    bubbles.draw_bubble(_bubble(text="A VERY LONG LINE " * 30, fontSize=40), 200, 100, 1.0)
    assert all(float(s).is_integer() for s in sizes[1:])
    assert sizes[1:] == sorted(sizes[1:], reverse=True)
