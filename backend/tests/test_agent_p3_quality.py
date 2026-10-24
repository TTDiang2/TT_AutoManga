"""P3 quality/format batch (deep-analysis G-13/14/15/16/21 + ports from the
novelai_local_web study): location library, inpaint mask, render scale cap,
webtoon templates, PNG parameter embedding, local ONNX upscale."""
import base64
import io
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from PIL import Image

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT.parent))

from backend.tests.test_e2e_agent import client  # noqa: E402,F401


@pytest.fixture()
def pid(client):
    r = client.post("/api/agent/projects", json={"name": "p3"})
    assert r.status_code == 200
    return r.json()["project"]["id"]


def _solid_png(size=(8, 8), color=(90, 120, 200)) -> str:
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


@pytest.fixture()
def mock_swarm(monkeypatch):
    captured = {}

    async def fake_generate(**kwargs):
        captured.update(kwargs)
        from backend.tests._fixtures import solid_png
        return {"success": True, "image": solid_png((60, 90, 200), (32, 48)),
                "path": "m"}

    import backend.api.agent as agent_mod
    monkeypatch.setattr(agent_mod.swarm_client, "generate_image",
                        AsyncMock(side_effect=fake_generate))
    return captured


# ------------------------------------------------------------------ G-13 locations

def test_location_library_injection(client, pid, mock_swarm):
    r = client.put(f"/api/agent/projects/{pid}/settings", json={
        "locations": [{"name": "rain bridge",
                       "prompt_block": "old wooden bridge, heavy rain, lanterns"}]})
    assert r.status_code == 200
    r = client.put(f"/api/agent/projects/{pid}/panels", json={"panels": [
        {"scene": "standoff", "characters": ["Yuki"], "location": "rain bridge"},
        {"scene": "rooftop", "location": "nowhere"}]})
    assert r.status_code == 200

    r = client.post("/api/agent/generate", json={
        "project_id": pid, "panel_id": "panel_1", "prompt": "two figures"})
    assert r.status_code == 200
    assert "old wooden bridge" in mock_swarm["prompt"]
    kinds = [i["kind"] for i in r.json()["injected"]]
    assert "location" in kinds

    # an unknown location injects nothing
    r = client.post("/api/agent/generate", json={
        "project_id": pid, "panel_id": "panel_2", "prompt": "x"})
    assert r.status_code == 200
    assert "old wooden bridge" not in mock_swarm["prompt"]


def test_location_validation(client, pid):
    r = client.put(f"/api/agent/projects/{pid}/settings", json={
        "locations": [{"name": "", "prompt_block": "x"}]})
    assert r.status_code == 400
    assert "location needs name" in r.json()["detail"]


# ------------------------------------------------------------------ G-14 mask

def test_mask_requires_init_image(client, pid, mock_swarm):
    r = client.post("/api/agent/generate", json={
        "prompt": "fix hand", "mask_image": _solid_png()})
    assert r.status_code == 400
    assert "mask_image requires init_image" in r.json()["detail"]


def test_mask_passthrough_to_swarmui(client, pid, mock_swarm):
    r = client.post("/api/agent/generate", json={
        "prompt": "fix hand", "init_image": _solid_png(),
        "mask_image": _solid_png(color=(255, 255, 255))})
    assert r.status_code == 200
    assert mock_swarm["init_image"].startswith("data:image/png")
    assert mock_swarm["mask_image"].startswith("data:image/png")


# ------------------------------------------------------------------ P3-A PNG metadata

def test_generated_png_carries_parameters(client, pid, mock_swarm):
    r = client.post("/api/agent/generate", json={
        "project_id": pid, "panel_id": None, "prompt": "bridge at dusk",
        "negative_prompt": "blurry", "seed": 123, "apply_to_panel": False})
    assert r.status_code == 200
    url = r.json()["assets"][0]["url"]
    from backend.storage.asset_store import asset_store
    path = asset_store.path_for(url.rsplit("/", 1)[-1])
    img = Image.open(path)
    assert "parameters" in img.info
    params = img.info["parameters"]
    assert "bridge at dusk" in params
    assert "Negative prompt: blurry" in params
    assert "seed: 123" in params
    meta = __import__("json").loads(img.info["automanga"])
    assert meta["prompt"] == "bridge at dusk" and meta["seed"] == 123


# ------------------------------------------------------------------ G-16 webtoon

def test_webtoon_templates(client):
    r = client.get("/api/agent/templates")
    ids = {t["id"]: t for t in r.json()["templates"]}
    assert {"webtoon-3", "webtoon-4-mix", "webtoon-6"} <= set(ids)
    assert ids["webtoon-3"]["slots"] == 3
    assert ids["webtoon-3"]["width"] == 800 and ids["webtoon-3"]["height"] == 2400
    assert ids["webtoon-6"]["height"] == 4800 and ids["webtoon-6"]["slots"] == 6


def test_webtoon_page_build(client, pid):
    r = client.post(f"/api/agent/projects/{pid}/pages", json={
        "template": {"kind": "builtin", "id": "webtoon-3"},
        "panel_ids": []})
    assert r.status_code == 200
    page = r.json()["page"]
    assert page["width"] == 800 and page["height"] == 2400
    assert len([e for e in page["elements"] if e["type"] == "image-slot"]) == 3


# ------------------------------------------------------------------ G-15 scale cap

def test_preview_scale_cap_raised(client, pid):
    r = client.post(f"/api/agent/projects/{pid}/pages", json={
        "template": {"kind": "custom",
                     "elements": [{"type": "image-slot", "x": 5, "y": 5,
                                   "width": 40, "height": 40}],
                     "width": 100, "height": 150},
        "panel_ids": []})
    page_id = r.json()["page"]["id"]
    r = client.get(f"/api/agent/projects/{pid}/pages/{page_id}/preview.png?scale=8")
    assert r.status_code == 200
    assert Image.open(io.BytesIO(r.content)).size == (800, 1200)
    # clamp: 99 -> 8
    r = client.get(f"/api/agent/projects/{pid}/pages/{page_id}/preview.png?scale=99")
    assert Image.open(io.BytesIO(r.content)).size == (800, 1200)


# ------------------------------------------------------------------ P3-B upscale

def test_inference_models_listing(client):
    r = client.get("/api/agent/inference-models")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["available"], bool)
    assert {m["id"] for m in body["models"]} >= {"realesrgan-anime-6b",
                                                 "realesr-animevideov3"}
    assert all(m["scale"] == 4 for m in body["models"])


def test_upscale_requires_runtime_or_real_model(client):
    r = client.post("/api/agent/upscale", json={
        "asset_url": _solid_png(), "model": "realesr-animevideov3", "tile": 64})
    if r.status_code == 503:
        assert "onnxruntime" in r.json()["detail"]   # graceful without the dep
    else:
        assert r.status_code == 200                  # real run (dep installed)
        body = r.json()
        assert body["width"] == 32 and body["height"] == 32  # 8x8 -> x4
        assert body["model"] == "realesr-animevideov3"


def test_upscale_unknown_model(client):
    r = client.post("/api/agent/upscale", json={"asset_url": _solid_png(),
                                                "model": "nope"})
    assert r.status_code in (400, 502, 503)
