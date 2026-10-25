"""End-to-end agent pipeline test (Phase 5).

Full golden path against the real app with SwarmUI mocked:
project → panels → batch generation (jobs) → page assembly → overlay
element → server preview → export → frontend-compatible project JSON.

Run: python -m pytest backend/tests/test_e2e_agent.py -q
"""
import base64
import io
import sys
import time
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
    """TestClient with storage redirected to tmp_path and SwarmUI mocked."""
    from fastapi.testclient import TestClient

    from backend.storage import asset_store as astore_mod
    from backend.storage import manager as mgr

    # 1) redirect storage to tmp
    (tmp_path / "projects").mkdir()
    monkeypatch.setattr(mgr, "PROJECTS_DIR", tmp_path / "projects")
    store = astore_mod.AssetStore(tmp_path / "assets", tmp_path / "assets" / "index.json")
    monkeypatch.setattr(astore_mod, "asset_store", store)

    # exports must not leak into the real data/exports either
    import backend.api.agent as agent_mod
    import backend.api.export as export_mod
    tmp_exports = tmp_path / "exports"
    monkeypatch.setattr(export_mod, "EXPORTS_DIR", tmp_exports)
    # agent.py caches the dir on first use — pre-seed the cache with the tmp one
    monkeypatch.setattr(agent_mod, "EXPORTS_DIR", tmp_exports)
    # modules holding their own reference to the singleton
    import backend.api.assets as assets_mod
    import backend.api.render as render_mod
    from backend.render.resolve import make_resolver
    for mod in (agent_mod, assets_mod, render_mod):
        monkeypatch.setattr(mod, "asset_store", store)
    for mod in (agent_mod, render_mod):   # modules with a module-level resolver
        monkeypatch.setattr(mod, "_resolver", make_resolver(store))

    # 2) mock SwarmUI generation
    async def fake_generate(**kwargs):
        src = solid_rgba_png((200, 60, 60, 140)) if kwargs.get("remove_background") \
            else solid_png((60, 90, 200))
        return {"success": True, "image": src, "path": "mock"}

    monkeypatch.setattr(agent_mod.swarm_client, "generate_image",
                        AsyncMock(side_effect=fake_generate))

    from backend.main import app
    return TestClient(app)


def test_full_agent_pipeline(client):
    c = client

    # --- 1. create project ---
    r = c.post("/api/agent/projects", json={"name": "e2e-comic"})
    assert r.status_code == 200
    pid = r.json()["project"]["id"]

    # --- 2. write panels (agent-authored storyboard) ---
    panels = [
        {"scene": "classroom", "characters": ["A"], "dialogue": "Hey! Look!"},
        {"scene": "window", "characters": ["A"], "dialogue": "maybe later..."},
        {"scene": "street", "characters": ["A", "B"], "dialogue": ""},
        {"scene": "sunset", "characters": ["B"], "dialogue": "Goodbye!"},
    ]
    r = c.put(f"/api/agent/projects/{pid}/panels", json={"panels": panels})
    assert r.status_code == 200
    assert [p["id"] for p in r.json()["panels"]] == [
        "panel_1", "panel_2", "panel_3", "panel_4"]

    # --- 3. batch generation: 4 panels + 2 transparent overlays ---
    jobs = [{"panel_id": f"panel_{i}", "prompt": f"art {i}"}
            for i in range(1, 5)]
    jobs += [{"prompt": "overlay A", "remove_background": True,
              "kind": "overlay", "apply_to_panel": False},
             {"prompt": "overlay B", "remove_background": True,
              "kind": "overlay", "apply_to_panel": False}]
    r = c.post("/api/agent/generate-batch",
               json={"project_id": pid, "concurrency": 2, "jobs": jobs})
    assert r.status_code == 202
    job_id = r.json()["job_id"]

    snap = None
    for _ in range(100):
        snap = c.get(f"/api/agent/jobs/{job_id}").json()
        if snap["status"] == "done":
            break
        time.sleep(0.1)
    assert snap["status"] == "done"
    assert all(it["status"] == "done" for it in snap["items"]), snap
    overlay_url = snap["items"][4]["result"]["assets"][0]["url"]
    assert snap["items"][4]["result"]["assets"][0]["has_alpha"] is True
    assert snap["items"][0]["result"]["assets"][0]["has_alpha"] is False

    # panels got their images applied
    r = c.get(f"/api/agent/projects/{pid}")
    assert r.json()["stats"]["panels_missing_image"] == []

    # --- 4. assemble a page (rows template, rtl fill, auto bubbles) ---
    r = c.post(f"/api/agent/projects/{pid}/pages", json={
        "template": {"kind": "rows", "rows": [2, 2]},
        "panel_ids": ["panel_1", "panel_2", "panel_3", "panel_4"],
        "name": "ch1-p1"})
    assert r.status_code == 200
    body = r.json()
    page = body["page"]
    assert body["saved"] is True and body["warnings"] == []
    imgs = [e for e in page["elements"] if e["type"] == "image"]
    bubs = [e for e in page["elements"] if e["type"] == "bubble"]
    assert len(imgs) == 4
    assert all(e["src"].startswith("/api/assets/file/") for e in imgs)
    types = {b["bubbleType"] for b in bubs}
    # exclamation/ellipsis lines must NOT auto-upgrade to shout/whisper —
    # balloons stay plain speech; accents are explicit element PATCHes
    assert types == {"speech"}
    assert all(b["zIndex"] > max(e["zIndex"] for e in imgs) for b in bubs)

    # --- 5. add a transparent breakout overlay element ---
    r = c.post(f"/api/agent/projects/{pid}/pages/{page['id']}/elements",
               json={"type": "page-image", "src": overlay_url,
                     "x": 25, "y": 25, "width": 50, "height": 50,
                     "rotation": 10})
    assert r.status_code == 200
    el = r.json()["element"]
    assert el["frameBorderWidth"] == 0
    assert el["zIndex"] == max(e["zIndex"] for e in page["elements"]) + 1

    # --- 6. server-side preview renders a PNG ---
    r = c.get(f"/api/agent/projects/{pid}/pages/{page['id']}/preview.png?scale=1")
    assert r.status_code == 200
    assert r.content[:4] == b"\x89PNG"
    img = Image.open(io.BytesIO(r.content))
    assert img.size == (600, 900)

    # --- 7. export pdf + zip ---
    r = c.post("/api/agent/export",
               json={"project_id": pid, "format": "both", "scale": 1})
    assert r.status_code == 200
    d = r.json()
    pdf_path, zip_path = Path(d["pdf"]["path"]), Path(d["zip"]["path"])
    assert pdf_path.exists() and pdf_path.stat().st_size > 1024
    assert pdf_path.read_bytes()[:4] == b"%PDF"
    assert zip_path.exists() and zip_path.stat().st_size > 1024

    # --- 8. project JSON is frontend-compatible (URL refs, no base64) ---
    r = c.get(f"/api/projects/load/{pid}")
    proj = r.json()["project"]
    assert all(p["image"].startswith("/api/assets/file/") for p in proj["panels"])
    dumped = r.text
    assert "data:image" not in dumped
    assert "e2e-comic" in dumped
