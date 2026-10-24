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
    # machine-readable block keeps the full recipe (incl. negative prompt),
    # the human block does not repeat the prompt in the settings line
    meta = __import__("json").loads(img.info["automanga"])
    assert meta["prompt"] == "bridge at dusk" and meta["seed"] == 123
    assert meta["negative_prompt"] == "blurry"
    settings_line = params.splitlines()[-1]
    assert "prompt:" not in settings_line and "seed: 123" in settings_line


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


def test_upscale_error_mapping(client, monkeypatch):
    # bad bytes -> 400 (UnidentifiedImageError is an OSError)
    r = client.post("/api/agent/upscale", json={
        "asset_url": "data:image/png;base64,QUJD", "model": "realesr-animevideov3"})
    assert r.status_code == 400 and "invalid image" in r.json()["detail"]

    # model download transport failure -> 502, not a bare 500
    import httpx
    from backend import inference as inf

    def boom(*a, **k):
        raise httpx.ConnectError("no route to host")
    monkeypatch.setattr(inf, "_model_file", boom)
    monkeypatch.setattr(inf, "_SESSIONS", {})   # bypass the cached session
    r = client.post("/api/agent/upscale", json={
        "asset_url": _solid_png(), "model": "realesr-animevideov3"})
    assert r.status_code == 502 and "model download failed" in r.json()["detail"]


def test_upscale_alpha_preserved():
    """Transparent overlays must survive upscaling (P3 review #4)."""
    pytest.importorskip("onnxruntime")
    import numpy as np
    from backend.inference import upscale_bytes
    img = Image.new("RGBA", (8, 8), (255, 0, 0, 255))
    for y in range(8):
        for x in range(8):
            if x < 4:
                img.putpixel((x, y), (255, 0, 0, 0))   # fully transparent half
    buf = io.BytesIO(); img.save(buf, format="PNG")
    out = upscale_bytes(buf.getvalue(), "realesr-animevideov3", tile=64)
    up = Image.open(io.BytesIO(out))
    assert up.mode == "RGBA" and up.size == (32, 32)
    a = np.asarray(up.getchannel("A"))
    assert a[:, :14].max() < 100          # transparent half stays transparent
    assert a[:, 18:].min() > 150          # opaque half stays opaque
    assert a[:, :16].mean() < 20


def test_upscale_multitile_seamless():
    """Multi-tile path blends with a tent window: no visible step across the
    tile seam (P3 review #3)."""
    pytest.importorskip("onnxruntime")
    import numpy as np
    from backend.inference import upscale_bytes
    # smooth horizontal gradient, 96px wide with tile=64 -> seam at x=64
    img = Image.new("RGB", (96, 32))
    for x in range(96):
        v = int(255 * x / 95)
        for y in range(32):
            img.putpixel((x, y), (v, v, v))
    buf = io.BytesIO(); img.save(buf, format="PNG")
    out = upscale_bytes(buf.getvalue(), "realesr-animevideov3", tile=64)
    up = Image.open(io.BytesIO(out))
    assert up.size == (384, 128)
    arr = np.asarray(up, dtype=np.float32).mean(axis=(0, 2))   # column means
    x = np.arange(arr.shape[0], dtype=np.float32)
    slope, intercept = np.polyfit(x, arr, 1)
    residual = arr - (slope * x + intercept)
    seam = 64 * 4   # tile boundary in output pixels
    # a hard seam is a step in the detrended profile (several levels with
    # this model); tent blending keeps the profile smooth through the seam.
    # (the model's own tone curve bends the residual globally — only the
    # LOCAL behaviour at the seam is blending's responsibility)
    assert abs(float(residual[seam - 1]) - float(residual[seam])) < 2.0
    window = residual[seam - 24:seam + 24]
    assert float(np.abs(np.diff(window)).max()) < 1.5


def test_upscale_output_budget_guard():
    """Oversized inputs raise a clean ModelError before allocating (P3 #5)."""
    from backend.inference import ModelError, upscale_bytes
    img = Image.new("RGB", (5000, 3000), (10, 10, 10))
    buf = io.BytesIO(); img.save(buf, format="PNG")
    with pytest.raises(ModelError):
        upscale_bytes(buf.getvalue(), "realesr-animevideov3", tile=512)


def test_upscale_unknown_model(client):
    r = client.post("/api/agent/upscale", json={"asset_url": _solid_png(),
                                                "model": "nope"})
    assert r.status_code in (400, 502, 503)
