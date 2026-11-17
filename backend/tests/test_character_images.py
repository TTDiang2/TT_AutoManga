"""Character sheets as assets instead of data URLs in data/characters.json:
POST /api/characters/migrate-images, the startup orphan cleanup counting
library (and per-project) character images as references, and panel
references reading asset URLs.

Run: python -m pytest backend/tests/test_character_images.py -q
"""
import base64
import json
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT.parent))

from backend.tests._fixtures import solid_png  # noqa: E402

SHEET = solid_png((10, 20, 30))          # a data:image/png;base64 URL


@pytest.fixture
def env(tmp_path, monkeypatch):
    import backend.api.characters as chars_mod
    import backend.main as main_mod
    import backend.prompting as prompting
    from backend.storage import asset_store as astore_mod
    store = astore_mod.AssetStore(tmp_path / "assets", tmp_path / "assets" / "index.json")
    monkeypatch.setattr(astore_mod, "asset_store", store)
    chars = tmp_path / "characters.json"
    monkeypatch.setattr(chars_mod, "CHARACTERS_FILE", chars)
    monkeypatch.setattr(prompting, "_CHARACTERS_FILE", chars)
    (tmp_path / "projects").mkdir()
    monkeypatch.setattr(main_mod, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(main_mod, "ASSETS_DIR", tmp_path / "assets")
    return store, chars, tmp_path


@pytest.fixture
def client(env):
    from fastapi.testclient import TestClient
    from backend.main import app
    return TestClient(app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1")


def _write(chars, items):
    chars.write_text(json.dumps(items), encoding="utf-8")


def test_migrate_images_moves_data_urls_to_assets(env, client):
    store, chars, _ = env
    _write(chars, [
        {"id": "a", "name": "Nova", "image": SHEET},
        {"id": "b", "name": "Mara", "image": "/api/assets/file/kept"},
        {"id": "c", "name": "Jun", "image": None},
        {"id": "d", "name": "Bad", "image": "data:text/plain;base64,aGk="},
    ])
    r = client.post("/api/characters/migrate-images")
    assert r.status_code == 200, r.text
    assert r.json() == {"success": True, "migrated": 1, "failed": 1}
    saved = json.loads(chars.read_text())
    url = saved[0]["image"]
    assert url.startswith("/api/assets/file/")
    asset_id = url.rsplit("/", 1)[-1]
    assert store.get(asset_id)["kind"] == "character"
    assert store.path_for(asset_id).read_bytes() == base64.b64decode(SHEET.split(",", 1)[1])
    assert saved[1]["image"] == "/api/assets/file/kept"
    assert saved[2]["image"] is None
    assert saved[3]["image"].startswith("data:text/plain")      # left alone
    assert "base64" not in json.dumps(saved[:3])
    # idempotent: nothing left to move
    assert client.post("/api/characters/migrate-images").json()["migrated"] == 0
    assert len(list(store.ids())) == 1


def test_orphan_cleanup_keeps_character_sheets(env):
    import backend.main as main_mod
    store, chars, tmp_path = env
    png = base64.b64decode(SHEET.split(",", 1)[1])
    lib = store.save_bytes(png, kind="character")
    proj_sheet = store.save_bytes(png, kind="character")
    orphan = store.save_bytes(png, kind="panel")
    for a in (lib, proj_sheet, orphan):     # all past the grace period
        store._index[a["asset_id"]]["created_at"] = "2020-01-01T00:00:00Z"
    _write(chars, [{"id": "a", "name": "Nova", "image": store.url_for(lib["asset_id"])}])
    pd = tmp_path / "projects" / "p1"
    pd.mkdir()
    (pd / "project.json").write_text(json.dumps({
        "id": "p1", "name": "x", "panels": [], "composerPages": [],
        "settings": {"characters": [{"name": "Nova",
                                     "image": store.url_for(proj_sheet["asset_id"])}]}}))
    main_mod._cleanup_orphan_assets()
    assert store.get(lib["asset_id"]) is not None
    assert store.get(proj_sheet["asset_id"]) is not None
    assert store.get(orphan["asset_id"]) is None


def test_orphan_cleanup_aborts_on_unreadable_library(env):
    import backend.main as main_mod
    store, chars, _ = env
    a = store.save_bytes(b"x", kind="character")
    store._index[a["asset_id"]]["created_at"] = "2020-01-01T00:00:00Z"
    chars.write_text("{not json", encoding="utf-8")
    main_mod._cleanup_orphan_assets()
    assert store.get(a["asset_id"]) is not None


def test_panel_reference_reads_an_asset_sheet(env):
    from backend.prompting import reference_for_panel
    store, chars, _ = env
    png = base64.b64decode(SHEET.split(",", 1)[1])
    webp = store.save_bytes(png, ext="webp", kind="character")
    _write(chars, [{"id": "a", "name": "Nova", "refWeight": 0.6,
                    "image": store.url_for(webp["asset_id"])}])
    ref = reference_for_panel({"settings": {}}, {"characters": ["Nova"]})
    assert ref is not None and ref["weight"] == 0.6
    assert ref["image"].startswith("data:image/webp;base64,")
