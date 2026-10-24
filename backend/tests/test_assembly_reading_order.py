"""Contract tests for page assembly reading order (AGENTS.md §2: reading
defaults to rtl — page assembly fills slots right-to-left, top-to-bottom)."""
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT.parent))

from backend.assembly import build_page  # noqa: E402


def _project():
    return {
        "panels": [
            {"id": "panel_1", "scene": "first", "dialogue": "one",
             "image": "/api/assets/file/a1"},
            {"id": "panel_2", "scene": "second", "dialogue": "two",
             "image": "/api/assets/file/a2"},
            {"id": "panel_3", "scene": "third", "dialogue": "three",
             "image": "/api/assets/file/a3"},
        ]
    }


def _page_images(page):
    return {e["src"]: e for e in page["elements"] if e.get("type") == "image"}


def test_manga_2h_default_is_rtl():
    """Default reading order must be rtl: panel_1 takes the RIGHT slot."""
    page, warnings = build_page(
        {"template": {"kind": "builtin", "id": "manga-2h"},
         "panel_ids": ["panel_1", "panel_2"]},
        _project())
    assert warnings == []
    imgs = _page_images(page)
    assert len(imgs) == 2
    assert imgs["/api/assets/file/a1"]["x"] > imgs["/api/assets/file/a2"]["x"], \
        "rtl default: panel_1 must land in the right-hand slot"


def test_manga_2h_explicit_ltr():
    page, warnings = build_page(
        {"template": {"kind": "builtin", "id": "manga-2h"},
         "panel_ids": ["panel_1", "panel_2"], "reading": "ltr"},
        _project())
    assert warnings == []
    imgs = _page_images(page)
    assert imgs["/api/assets/file/a1"]["x"] < imgs["/api/assets/file/a2"]["x"], \
        "ltr: panel_1 must land in the left-hand slot"


def test_row_before_column_order():
    """A slot in an upper row is filled before any slot in a lower row,
    regardless of x position (manga-3 = 1 wide + 2 below)."""
    page, _ = build_page(
        {"template": {"kind": "builtin", "id": "manga-3"},
         "panel_ids": ["panel_1", "panel_2", "panel_3"]},
        _project())
    imgs = _page_images(page)
    top = imgs["/api/assets/file/a1"]
    assert top["y"] < imgs["/api/assets/file/a2"]["y"]
    assert top["y"] < imgs["/api/assets/file/a3"]["y"]
    # rtl within the second row
    assert imgs["/api/assets/file/a2"]["x"] > imgs["/api/assets/file/a3"]["x"]


def test_bubbles_follow_their_panel():
    """Auto bubbles attach above frames in zIndex and exist per dialogue."""
    page, _ = build_page(
        {"template": {"kind": "builtin", "id": "manga-2h"},
         "panel_ids": ["panel_1", "panel_2"]},
        _project())
    bubbles = [e for e in page["elements"] if e.get("type") == "bubble"]
    frames = [e for e in page["elements"] if e.get("type") == "image"]
    assert len(bubbles) == 2
    assert all(b["zIndex"] > max(f.get("zIndex", 0) for f in frames)
               for b in bubbles)
