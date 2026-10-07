"""Asset store + project-save normalization tests (Phase 1).

Run: python -m pytest backend/tests/test_asset_store.py -q
"""
import base64
import json
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT.parent))

from backend.storage import asset_store as mod  # noqa: E402

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest.fixture
def store(tmp_path, monkeypatch):
    s = mod.AssetStore(tmp_path / "assets", tmp_path / "assets" / "index.json")
    monkeypatch.setattr(mod, "asset_store", s)
    return s


def test_save_and_fetch(store):
    e = store.save_bytes(PNG_1PX, kind="panel", project_id="p1")
    assert store.get(e["asset_id"])["kind"] == "panel"
    assert store.path_for(e["asset_id"]).read_bytes() == PNG_1PX


def test_save_dataurl_roundtrip(store):
    e = store.save_dataurl("data:image/png;base64," + base64.b64encode(PNG_1PX).decode())
    assert e["path"].endswith(".png")
    assert store.path_for(e["asset_id"]).read_bytes() == PNG_1PX


def test_url_for(store):
    e = store.save_bytes(PNG_1PX)
    assert store.url_for(e["asset_id"]) == f"/api/assets/file/{e['asset_id']}"


def test_remove(store):
    e = store.save_bytes(PNG_1PX)
    asset_id = e["asset_id"]
    assert store.remove(asset_id) is True
    assert store.get(asset_id) is None
    assert store.path_for(asset_id) is None


def test_missing_asset_returns_none(store):
    assert store.get("nonexistent") is None
    assert store.path_for("nonexistent") is None


def test_project_save_normalizes(tmp_path, monkeypatch, store):
    from backend.storage import manager as mgr
    (tmp_path / "projects").mkdir()
    monkeypatch.setattr(mgr, "PROJECTS_DIR", tmp_path / "projects")
    proj = {"name": "t", "panels": [{"id": "p1", "scene": "s", "characters": [],
            "dialogue": "", "prompt": {}, "layers": [],
            "image": "data:image/png;base64," + base64.b64encode(PNG_1PX).decode()}],
            "settings": {}, "composerPages": []}
    saved = mgr.storage.save_project(proj)
    assert saved["panels"][0]["image"].startswith("/api/assets/file/")
    assert "data:" not in json.dumps(saved)
    # the asset file must exist on disk and be tracked by the store
    asset_id = saved["panels"][0]["image"].rsplit("/", 1)[-1]
    assert mod.asset_store.path_for(asset_id) is not None


def test_project_save_normalizes_composer_elements(tmp_path, monkeypatch, store):
    from backend.storage import manager as mgr
    (tmp_path / "projects").mkdir()
    monkeypatch.setattr(mgr, "PROJECTS_DIR", tmp_path / "projects")
    dataurl = "data:image/png;base64," + base64.b64encode(PNG_1PX).decode()
    proj = {"name": "t", "panels": [], "settings": {},
            "composerPages": [{"id": "pg", "name": "p", "templateId": "", "width": 600,
                               "height": 900, "order": 0,
                               "elements": [
                                   {"id": "e1", "type": "image", "x": 0, "y": 0,
                                    "width": 50, "height": 50, "rotation": 0,
                                    "zIndex": 0, "locked": False, "visible": True,
                                    "src": dataurl, "originalSrc": dataurl}]}]}
    saved = mgr.storage.save_project(proj)
    el = saved["composerPages"][0]["elements"][0]
    assert el["src"].startswith("/api/assets/file/")
    assert el["originalSrc"].startswith("/api/assets/file/")
    assert "data:" not in json.dumps(saved)


def test_cleanup_removes_orphan_assets(tmp_path, monkeypatch, store):
    """Assets not referenced by any project must be purged from the index."""
    import backend.main as main_mod
    (tmp_path / "projects").mkdir()
    monkeypatch.setattr(main_mod, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(main_mod, "ASSETS_DIR", tmp_path / "assets")
    # one referenced asset + one orphan
    kept = mod.asset_store.save_bytes(PNG_1PX, kind="panel")
    orphan = mod.asset_store.save_bytes(PNG_1PX, kind="panel")
    proj_dir = tmp_path / "projects" / "proj1"
    proj_dir.mkdir()
    (proj_dir / "project.json").write_text(json.dumps({
        "id": "proj1", "name": "x", "panels": [
            {"id": "p1", "scene": "s", "characters": [], "dialogue": "",
             "prompt": {}, "layers": [],
             "image": mod.asset_store.url_for(kept["asset_id"])}],
        "settings": {}, "composerPages": []}), encoding="utf-8")
    main_mod._cleanup_orphan_assets()
    assert mod.asset_store.get(kept["asset_id"]) is not None
    assert mod.asset_store.get(orphan["asset_id"]) is None
