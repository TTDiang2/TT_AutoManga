"""Server-side renderer tests (Phase 2).

Pixel assertions mirror the frontend semantics documented in the design doc
§6. Run: python -m pytest backend/tests/test_renderer.py -q
"""
import base64
import sys
from pathlib import Path

import pytest
from PIL import Image

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT.parent))

from backend.render import render_page  # noqa: E402
from backend.render.resolve import make_resolver  # noqa: E402
from backend.storage.asset_store import AssetStore  # noqa: E402
from backend.tests._fixtures import solid_png, solid_rgba_png, transparent_circle_png  # noqa: E402

RED = (230, 40, 40)
BLUE = (30, 60, 230)
GREEN_A50 = (0, 255, 0, 128)  # semi-transparent overlay source


@pytest.fixture
def resolver(tmp_path):
    store = AssetStore(tmp_path / "assets", tmp_path / "assets" / "index.json")
    return make_resolver(store)


def base_page(extra=None):
    els = [
        {"id": "red", "type": "image", "src": solid_png(RED),
         "x": 0, "y": 0, "width": 50, "height": 50,
         "rotation": 0, "zIndex": 0, "locked": False, "visible": True},
        {"id": "blue", "type": "image", "src": solid_png(BLUE),
         "x": 50, "y": 0, "width": 50, "height": 50,
         "rotation": 0, "zIndex": 1, "locked": False, "visible": True,
         "corners": {"tl": {"x": 30, "y": 0}, "tr": {"x": 100, "y": 10},
                     "br": {"x": 70, "y": 100}, "bl": {"x": 0, "y": 80}},
         "frameBorderWidth": 3},
        # breakout overlay: transparent-ish green, rotated, on top of everything
        {"id": "ov", "type": "page-image", "src": solid_rgba_png(GREEN_A50),
         "x": 25, "y": 25, "width": 50, "height": 50,
         "rotation": 10, "zIndex": 99, "locked": False, "visible": True,
         "frameBorderWidth": 0},
        {"id": "bub", "type": "bubble", "bubbleType": "speech",
         "text": "你好漫画", "direction": "vertical",
         "x": 5, "y": 60, "width": 40, "height": 15,
         "rotation": 0, "zIndex": 100, "locked": False, "visible": True,
         "backgroundColor": "#ffffff", "borderColor": "#000000",
         "fontSize": 12, "tailPosition": "bottom"},
        {"id": "txt", "type": "text", "content": "縦書きテスト",
         "direction": "vertical", "fontSize": 14, "fontFamily": "",
         "color": "#000000", "fontWeight": "normal", "textAlign": "center",
         "x": 60, "y": 60, "width": 35, "height": 8,
         "rotation": 0, "zIndex": 101, "locked": False, "visible": True},
        # must be skipped entirely
        {"id": "hidden", "type": "image", "src": solid_png(RED),
         "x": 0, "y": 0, "width": 100, "height": 100,
         "rotation": 0, "zIndex": 200, "locked": False, "visible": False},
        # empty slot renders nothing
        {"id": "slot", "type": "image-slot", "label": "1",
         "x": 0, "y": 85, "width": 30, "height": 10,
         "rotation": 0, "zIndex": 5, "locked": False, "visible": True},
    ]
    if extra:
        els.extend(extra)
    return {"id": "p1", "name": "test", "templateId": "", "width": 600,
            "height": 900, "order": 0, "elements": els}


def test_page_size_and_base_colors(resolver):
    img = render_page(base_page(), 1.0, resolver)
    assert img.size == (600, 900)
    # left half is red
    r, g, b = img.getpixel((120, 200))[:3]
    assert r > 200 and b < 80
    # right half, inside the deformed polygon, is blue
    r, g, b = img.getpixel((480, 60))[:3]
    assert b > 200 and r < 100


def test_corners_clip(resolver):
    img = render_page(base_page(), 1.0, resolver)
    # blue element local (98%, 98%) is outside its quad → white page shows
    assert img.getpixel((594, 441)) == (255, 255, 255)


def test_frame_border_drawn(resolver):
    img = render_page(base_page(), 1.0, resolver)
    # scan the top edge of the blue quad for a dark border pixel
    row = [img.getpixel((x, 10))[:3] for x in range(430, 560)]
    dark = [p for p in row if sum(p) < 250]
    assert dark, "expected a dark frame-border pixel along the quad edge"


def test_page_image_alpha_composite(resolver):
    img = render_page(base_page(), 1.0, resolver)
    # over red background: blend of green(0,255,0)@~0.5 over (230,40,40)
    r, g, b = img.getpixel((250, 400))[:3]
    assert g > 100 and r < 190, (r, g, b)
    # over blue background
    r, g, b = img.getpixel((400, 350))[:3]
    assert g > 100 and b > 100 and r < 60, (r, g, b)
    # outside the overlay: stays pure red
    r, g, b = img.getpixel((60, 80))[:3]
    assert r > 200 and g < 100


def test_bubble_white_fill_dark_border_and_vertical_text(resolver):
    img = render_page(base_page(), 1.0, resolver)
    # inside the ellipse, off the text column → white fill
    r, g, b = img.getpixel((60, 607))[:3]
    assert (r, g, b) == (255, 255, 255)
    # ellipse border: dark pixels along the horizontal center line
    row = [img.getpixel((x, 607))[:3] for x in range(32, 268)]
    assert any(sum(p) < 250 for p in row), "no dark border on bubble"
    # vertical text column near the right side of the bubble
    col = [img.getpixel((x, y))[:3] for x in range(240, 262) for y in range(560, 660)]
    assert any(sum(p) < 250 for p in col), "no dark vertical text in bubble"


def test_vertical_text_element_renders(resolver):
    img = render_page(base_page(), 1.0, resolver)
    col = [img.getpixel((x, y))[:3] for x in range(455, 476) for y in range(515, 635)]
    assert any(sum(p) < 250 for p in col), "no dark vertical CJK text found"


def test_hidden_and_slot_render_nothing(resolver):
    img = render_page(base_page(), 1.0, resolver)
    # bottom-right corner: hidden full-page image must NOT paint it
    assert img.getpixel((595, 890)) == (255, 255, 255)


def test_scale_multiplies_output(resolver):
    img = render_page(base_page(), 2.0, resolver)
    assert img.size == (1200, 1800)


def test_missing_src_renders_nothing(resolver):
    page = base_page()
    page["elements"].append(
        {"id": "broken", "type": "image", "src": "/api/assets/file/does-not-exist",
         "x": 0, "y": 0, "width": 100, "height": 100,
         "rotation": 0, "zIndex": 300, "locked": False, "visible": True})
    img = render_page(page, 1.0, resolver)  # must not raise
    assert img.getpixel((595, 890)) == (255, 255, 255)


def test_dataurl_resolution(resolver):
    img = render_page(base_page(), 1.0, resolver)  # all srcs are data URLs
    assert img.getpixel((120, 200))[0] > 200


def test_asset_url_resolution(tmp_path):
    store = AssetStore(tmp_path / "assets", tmp_path / "assets" / "index.json")
    entry = store.save_dataurl(solid_png(RED))
    page = {"id": "p", "name": "p", "templateId": "", "width": 600, "height": 900,
            "order": 0, "elements": [
                {"id": "a", "type": "image", "src": store.url_for(entry["asset_id"]),
                 "x": 10, "y": 10, "width": 50, "height": 50,
                 "rotation": 0, "zIndex": 0, "locked": False, "visible": True}]}
    img = render_page(page, 1.0, make_resolver(store))
    assert img.getpixel((200, 200))[0] > 200


def test_rotation_moves_content(resolver):
    # a red half-page image rotated ~90° about ITS OWN center (300,150)
    # becomes a vertical band x 150-450
    page = {"id": "p", "name": "p", "templateId": "", "width": 600, "height": 600,
            "order": 0, "elements": [
                {"id": "r", "type": "image", "src": solid_png(RED),
                 "x": 0, "y": 0, "width": 100, "height": 50,
                 "rotation": 90, "zIndex": 0, "locked": False, "visible": True}]}
    img = render_page(page, 1.0, resolver)
    assert img.getpixel((300, 100))[:3] != (255, 255, 255)
    assert img.getpixel((100, 100))[:3] == (255, 255, 255)
    assert img.getpixel((500, 100))[:3] == (255, 255, 255)
