"""Tests for the workflow-gap fixes: per-request model/loras, prompt-format
aware injection, character/style blocks, img2img passthrough, alpha fallback,
asset registration, dynamic layouts, text fitting.

Run: python -m pytest backend/tests/test_agent_features.py -q
"""
import base64
import io
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT.parent))

from PIL import Image  # noqa: E402

from backend.tests._fixtures import solid_png, solid_rgba_png  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from backend.storage import asset_store as astore_mod
    from backend.storage import manager as mgr

    (tmp_path / "projects").mkdir()
    monkeypatch.setattr(mgr, "PROJECTS_DIR", tmp_path / "projects")
    store = astore_mod.AssetStore(tmp_path / "assets", tmp_path / "assets" / "index.json")
    monkeypatch.setattr(astore_mod, "asset_store", store)

    import backend.api.agent as agent_mod
    import backend.api.assets as assets_mod
    import backend.api.render as render_mod
    from backend.render.resolve import make_resolver
    for mod in (agent_mod, assets_mod, render_mod):
        monkeypatch.setattr(mod, "asset_store", store)
    for mod in (agent_mod, render_mod):
        monkeypatch.setattr(mod, "_resolver", make_resolver(store))

    import backend.api.agent as agent_mod  # noqa: F811

    captured = {}

    def _opaque_with_white_bg() -> str:
        img = Image.new("RGB", (400, 400), (255, 255, 255))
        from PIL import ImageDraw
        ImageDraw.Draw(img).ellipse([100, 100, 300, 300], fill=(200, 60, 60))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    async def fake_generate(**kwargs):
        captured.update(kwargs)
        src = _opaque_with_white_bg() if kwargs.get("remove_background") \
            else solid_rgba_png((200, 60, 60, 140))
        return {"success": True, "image": src, "path": "mock"}

    mock = AsyncMock(side_effect=fake_generate)
    monkeypatch.setattr(agent_mod.swarm_client, "generate_image", mock)
    monkeypatch.setattr(agent_mod.swarm_client, "list_models",
                        AsyncMock(return_value=[{"name": "m.safetensors",
                                                 "architecture": "qwen"}]))

    from backend.main import app
    yield TestClient(app), captured


def _mk_project(client):
    r = client.post("/api/agent/projects", json={
        "name": "feat", "panels": [
            {"scene": "s1", "characters": ["小雪"], "dialogue": "hi"},
            {"scene": "s2", "characters": [], "dialogue": ""}]})
    return r.json()["project"]["id"]


def test_per_request_model_and_loras_passthrough(client):
    c, captured = client
    pid = _mk_project(c)
    r = c.post("/api/agent/generate", json={
        "project_id": pid, "panel_id": "panel_1", "prompt": "1girl, test",
        "model": "qwen_image_2.1_int8_convrot", "prompt_format": "prose",
        "loras": [{"name": "someLora", "weight": 0.8}], "seed": 7,
        "inject_characters": False})
    assert r.status_code == 200, r.text
    assert captured["model"] == "qwen_image_2.1_int8_convrot"
    assert captured["seed"] == 7
    assert any(l.name == "someLora" and l.weight == 0.8 for l in captured["loras"])
    body = r.json()
    assert body["model"] == "qwen_image_2.1_int8_convrot"
    # meta records model + prompt format
    store = __import__("backend.api.agent", fromlist=["asset_store"]).asset_store
    meta = store.get(body["assets"][0]["asset_id"])
    assert meta["model"] == "qwen_image_2.1_int8_convrot"
    assert meta["prompt_format"] == "prose"


def test_style_and_character_injection(client):
    c, captured = client
    pid = _mk_project(c)
    r = c.put(f"/api/agent/projects/{pid}/settings", json={
        "style": "chinese ink painting style",
        "characters": [{"name": "小雪", "prompt_block": "1girl, white hair, blue eyes"}]})
    assert r.status_code == 200, r.text
    r = c.post("/api/agent/generate", json={
        "project_id": pid, "panel_id": "panel_1", "prompt": "classroom scene"})
    assert r.status_code == 200
    # danbooru default: joined with ', '
    assert "chinese ink painting style" in captured["prompt"]
    assert "1girl, white hair, blue eyes" in captured["prompt"]
    # prose format joins with '。'
    c.post("/api/agent/generate", json={
        "project_id": pid, "panel_id": "panel_1", "prompt": "教室场景",
        "prompt_format": "prose"})
    assert "教室场景。chinese ink painting style" in captured["prompt"]
    # character endpoint exposes effective blocks
    r = c.get(f"/api/agent/projects/{pid}/characters")
    assert "1girl, white hair, blue eyes" in r.json()["blocks"]["小雪"]


def test_character_block_validation(client):
    c, _ = client
    pid = _mk_project(c)
    r = c.put(f"/api/agent/projects/{pid}/settings", json={
        "characters": [{"name": "x"}]})
    assert r.status_code == 400


def test_init_image_passthrough(client):
    c, captured = client
    pid = _mk_project(c)
    entry = __import__("backend.api.agent", fromlist=["asset_store"]).asset_store \
        .save_dataurl(solid_png((10, 200, 10)))
    r = c.post("/api/agent/generate", json={
        "project_id": pid, "panel_id": "panel_2", "prompt": "edit this",
        "init_image": __import__("backend.api.agent",
                                 fromlist=["asset_store"]).asset_store.url_for(entry["asset_id"]),
        "init_creativity": 0.6, "inject_characters": False})
    assert r.status_code == 200, r.text
    assert captured["init_image"].startswith("data:image/")
    assert captured["init_creativity"] == 0.6


def test_init_image_missing_400(client):
    c, _ = client
    pid = _mk_project(c)
    r = c.post("/api/agent/generate", json={
        "project_id": pid, "prompt": "x",
        "init_image": "/api/assets/file/nope"})
    assert r.status_code == 400


def test_alpha_fallback_threshold(client):
    """SwarmUI returns an opaque image despite remove_background=True →
    local threshold fallback produces a transparent asset and reports how."""
    c, captured = client
    pid = _mk_project(c)
    r = c.post("/api/agent/generate", json={
        "project_id": pid, "prompt": "dragon on white bg",
        "remove_background": True, "apply_to_panel": False,
        "inject_characters": False})
    body = r.json()
    assert body["assets"][0]["has_alpha"] is True
    assert body["assets"][0]["alpha_method"] in ("rembg", "threshold")


def test_models_endpoint(client):
    c, _ = client
    r = c.get("/api/agent/models")
    assert r.status_code == 200
    assert r.json()["models"][0]["architecture"] == "qwen"


def test_register_asset_endpoint(client):
    c, _ = client
    from backend.tests._fixtures import solid_png as sp
    import base64 as b
    raw = b.b64decode(sp((1, 2, 3)).split(",", 1)[1])
    r = c.post("/api/assets/file", files={"file": ("x.png", raw, "image/png")},
               data={"kind": "overlay"})
    assert r.status_code == 200, r.text
    assert r.json()["url"].startswith("/api/assets/file/")
    fetch = c.get(r.json()["url"])
    assert fetch.status_code == 200
    assert Image.open(io.BytesIO(fetch.content)).size == (400, 400)


def test_dynamic_corners_applied(client):
    c, _ = client
    pid = _mk_project(c)
    for i in range(1, 5):
        e = __import__("backend.api.agent", fromlist=["asset_store"]).asset_store \
            .save_dataurl(solid_png((10 * i, 50, 90)))
        c.patch(f"/api/agent/projects/{pid}/panels/panel_{i}",
                json={"image": __import__("backend.api.agent",
                                          fromlist=["asset_store"]).asset_store.url_for(e["asset_id"])})
    r = c.post(f"/api/agent/projects/{pid}/pages", json={
        "template": {"kind": "builtin", "id": "manga-4"},
        "panel_ids": ["panel_1", "panel_2", "panel_3", "panel_4"],
        "dynamic": True, "bubbles": {"mode": "none"}})
    page = r.json()["page"]
    frames = [e for e in page["elements"] if e["type"] == "image"]
    with_corners = [e for e in frames if e.get("corners")]
    assert len(with_corners) >= len(frames) - 1  # all but the hero slot
    # hero slot stays rectangular
    hero = max(frames, key=lambda e: e["width"] * e["height"])
    assert not hero.get("corners")


def test_dynamic_builtin_templates_geometry():
    from backend.composer_builtins import DYNAMIC_TEMPLATES, get_template
    for t in DYNAMIC_TEMPLATES:
        for el in t["elements"]:
            c = el.get("corners")
            assert c and set(c) == {"tl", "tr", "br", "bl"}, (t["id"], el["label"])
            for pt in c.values():
                assert 0 <= pt["x"] <= 100 and 0 <= pt["y"] <= 100
        # slots must stay inside the page
        for el in t["elements"]:
            assert 0 <= el["x"] and el["x"] + el["width"] <= 100
            assert 0 <= el["y"] and el["y"] + el["height"] <= 100
    assert get_template("dyn-2-slant") is not None
