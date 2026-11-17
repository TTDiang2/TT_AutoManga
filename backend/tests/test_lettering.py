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
    assert pad > pad0 and pad >= eh   # tip is a full box height below the bubble
    tx, ty = pad + 0.25 * ew, pad + 2.0 * eh
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
    assert bbox[2] > pad + 200 + 10 and bbox[3] > pad + 100 + 10


def test_left_aligned_ink_starts_at_the_left():
    text = "A LONGER FIRST LINE\nSHORT"
    el = dict(bubbleType="narration", text=text)
    center, pad = bubbles.draw_bubble(_bubble(**el), 400, 120, 1.0)
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
])
def test_validation_rejects_bad_bubble_keys(bad):
    with pytest.raises(HTTPException):
        _validate_element_payload(bad, partial=True)
