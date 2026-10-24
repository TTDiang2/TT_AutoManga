"""P0 orchestration endpoints (deep-analysis doc G-1/2/3/4/6/22):
page delete+reorder, variant pick, asset metadata, template listing,
agent settings, story bible."""
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT.parent))

from backend.tests.test_e2e_agent import client  # noqa: E402,F401
from backend.core import config  # noqa: E402


@pytest.fixture()
def pid(client):
    r = client.post("/api/agent/projects", json={"name": "p0"})
    assert r.status_code == 200
    return r.json()["project"]["id"]


def _blank_page(client, pid, name="pg"):
    r = client.post(f"/api/agent/projects/{pid}/pages",
                    json={"template": {"kind": "builtin", "id": "blank"},
                          "panel_ids": [], "name": name})
    assert r.status_code == 200
    return r.json()["page"]


# ------------------------------------------------------------------ G-1

def test_page_get_delete_reorder(client, pid):
    pages = [_blank_page(client, pid, f"p{i}") for i in range(3)]
    ids = [p["id"] for p in pages]

    # GET one page
    r = client.get(f"/api/agent/projects/{pid}/pages/{ids[0]}")
    assert r.status_code == 200 and r.json()["page"]["id"] == ids[0]
    r = client.get(f"/api/agent/projects/{pid}/pages/nope")
    assert r.status_code == 404

    # DELETE the middle page; remaining orders renormalize to 0..n-1
    r = client.delete(f"/api/agent/projects/{pid}/pages/{ids[1]}")
    assert r.status_code == 200 and r.json()["pages_remaining"] == 2
    r = client.get(f"/api/agent/projects/{pid}")
    orders = {p["id"]: p["order"]
              for p in r.json()["project"]["composerPages"]}
    assert sorted(orders.values()) == [0, 1]
    r = client.delete(f"/api/agent/projects/{pid}/pages/{ids[1]}")
    assert r.status_code == 404

    # REORDER must be a full permutation
    r = client.put(f"/api/agent/projects/{pid}/pages/order",
                   json={"page_ids": [ids[2], ids[0]]})
    assert r.status_code == 200
    assert r.json()["pages"] == [{"id": ids[2], "order": 0},
                                 {"id": ids[0], "order": 1}]
    r = client.put(f"/api/agent/projects/{pid}/pages/order",
                   json={"page_ids": [ids[0]]})          # missing one
    assert r.status_code == 400
    r = client.put(f"/api/agent/projects/{pid}/pages/order",
                   json={"page_ids": [ids[0], ids[0]]})  # duplicate
    assert r.status_code == 400


# ------------------------------------------------------------------ G-2

def test_apply_variant_binds_chosen_variant(client, pid):
    r = client.put(f"/api/agent/projects/{pid}/panels", json={"panels": [
        {"scene": "a lone figure on a rooftop", "dialogue": ""}]})
    assert r.status_code == 200
    r = client.post("/api/agent/generate", json={
        "project_id": pid, "panel_id": "panel_1", "prompt": "rooftop",
        "variants": 3, "apply_variant": 2})
    assert r.status_code == 200
    body = r.json()
    assert len(body["assets"]) == 3
    chosen = body["assets"][2]["url"]
    r = client.get(f"/api/agent/projects/{pid}")
    assert r.json()["project"]["panels"][0]["image"] == chosen

    # out-of-range index -> 400
    r = client.post("/api/agent/generate", json={
        "project_id": pid, "panel_id": "panel_1", "prompt": "x",
        "variants": 2, "apply_variant": 5})
    assert r.status_code == 400


# ------------------------------------------------------------------ G-3

def test_asset_metadata_query(client, pid):
    r = client.post("/api/agent/generate", json={
        "project_id": pid, "prompt": "meta test", "seed": 42,
        "apply_to_panel": False})
    assert r.status_code == 200
    asset_id = r.json()["assets"][0]["asset_id"]

    r = client.get(f"/api/agent/assets/{asset_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["url"].endswith(asset_id)
    assert body["file_exists"] is True
    entry = body["asset"]
    assert entry["kind"] == "panel"
    assert entry["prompt"] == "meta test"
    assert entry["seed"] == 42

    r = client.get("/api/agent/assets/does_not_exist")
    assert r.status_code == 404


# ------------------------------------------------------------------ G-4

def test_templates_listing(client):
    r = client.get("/api/agent/templates")
    assert r.status_code == 200
    templates = r.json()["templates"]
    ids = {t["id"] for t in templates}
    assert {"manga-2v", "manga-8", "hero-splash", "dyn-2-slant",
            "dyn-5-mix"} <= ids
    by_id = {t["id"]: t for t in templates}
    assert by_id["manga-2v"]["slots"] == 2
    assert by_id["manga-2v"]["dynamic"] is False
    assert by_id["dyn-2-slant"]["dynamic"] is True
    assert by_id["dyn-2-slant"]["slots"] == 3
    assert by_id["blank"]["slots"] == 0
    assert all(t["width"] > 0 and t["height"] > 0 for t in templates)
    assert "rows" in r.json()["other_kinds"]


# ------------------------------------------------------------------ G-6

@pytest.fixture()
def settings_sandbox(tmp_path, monkeypatch):
    """Keep global settings mutations + persistence out of the real file."""
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    sw = config.settings.swarmui
    originals = {f: getattr(sw, f) for f in (
        "currentModel", "currentSteps", "currentCfgScale", "currentWidth",
        "currentHeight", "currentSamplerName", "promptSuffix",
        "currentLoras")}
    yield
    for f, v in originals.items():
        setattr(sw, f, v)


def test_agent_settings_get_put(client, settings_sandbox):
    r = client.get("/api/agent/settings")
    assert r.status_code == 200
    view = r.json()["swarmui"]
    assert {"currentSteps", "currentWidth", "currentSamplerName",
            "promptSuffix"} <= set(view)

    r = client.put("/api/agent/settings", json={
        "currentSteps": 28, "currentWidth": 832,
        "currentLoras": [{"name": "ink", "weight": 0.8}]})
    assert r.status_code == 200
    view = r.json()["swarmui"]
    assert view["currentSteps"] == 28 and view["currentWidth"] == 832
    assert view["currentLoras"] == [{"name": "ink", "weight": 0.8}]

    # persisted to the redirected file, and reflected on GET
    assert (config.SETTINGS_FILE).exists()
    assert client.get("/api/agent/settings").json()["swarmui"]["currentSteps"] == 28

    # validation branches
    for bad in ({"currentSteps": 0}, {"currentSteps": 999},
                {"currentWidth": 999},        # not a multiple of 8
                {"currentCfgScale": 31},
                {"currentLoras": [{"name": "", "weight": 1}]},
                {"currentLoras": [{"name": "x", "weight": 5}]}):
        r = client.put("/api/agent/settings", json=bad)
        assert r.status_code == 400, bad


# ------------------------------------------------------------------ G-22

def test_story_bible_field(client, pid):
    r = client.put(f"/api/agent/projects/{pid}/settings",
                   json={"style": "ink wash",
                         "bible": "Ch1: Yuki loses the jade pendant."})
    assert r.status_code == 200
    r = client.get(f"/api/agent/projects/{pid}")
    cfg = r.json()["project"]["settings"]
    assert cfg["bible"] == "Ch1: Yuki loses the jade pendant."
    assert cfg["style"] == "ink wash"


def test_global_loras_do_not_break_generation(client, pid, settings_sandbox):
    """P0-1 regression: setting currentLoras via PUT /api/agent/settings used
    to make every /generate 500 (LoraConfig models accessed dict-style)."""
    r = client.put("/api/agent/settings",
                   json={"currentLoras": [{"name": "ink", "weight": 0.5}]})
    assert r.status_code == 200
    r = client.put(f"/api/agent/projects/{pid}/panels", json={"panels": [
        {"scene": "bridge in the rain", "dialogue": ""}]})
    assert r.status_code == 200
    r = client.post("/api/agent/generate", json={
        "project_id": pid, "panel_id": "panel_1", "prompt": "bridge"})
    assert r.status_code == 200, r.text


def test_settings_lora_name_type_validated(client, settings_sandbox):
    r = client.put("/api/agent/settings",
                   json={"currentLoras": [{"name": 123, "weight": 1}]})
    assert r.status_code == 400
