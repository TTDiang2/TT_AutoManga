"""Per-character LoRAs: the character library's ``lora`` field, panel
conditioning (LoRA + trigger word, 0.6 of the weight on multi-character
panels), its merge into /api/agent/generate and /api/assets/swarmui/generate,
and the LoRA list for the Characters tab.

Run: python -m pytest backend/tests/test_character_loras.py -q
"""
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT.parent))

from backend.tests._fixtures import solid_png  # noqa: E402

NOVA = {"id": "char_nova", "name": "Nova", "description": "", "appearance": "1girl, blue hair",
        "sourcePanelIds": [], "lora": {"name": "SecondFloor/sf_nova", "weight": 0.8, "trigger": "sfnova"}}
MARA = {"id": "char_mara", "name": "Mara", "description": "", "appearance": "1girl, red hair",
        "sourcePanelIds": [], "lora": {"name": "SecondFloor/sf_mara.safetensors", "weight": 1.0}}
JUN = {"id": "char_jun", "name": "Jun", "description": "", "appearance": "1boy", "sourcePanelIds": []}


@pytest.fixture
def library(tmp_path, monkeypatch):
    """A temporary global character library (never data/characters.json)."""
    import backend.api.characters as chars_mod
    import backend.prompting as prompting
    f = tmp_path / "characters.json"
    f.write_text(json.dumps([NOVA, MARA, JUN]), encoding="utf-8")
    monkeypatch.setattr(prompting, "_CHARACTERS_FILE", f)
    monkeypatch.setattr(chars_mod, "CHARACTERS_FILE", f)
    return f


@pytest.fixture
def client(tmp_path, monkeypatch, library):
    from fastapi.testclient import TestClient

    from backend.core.config import settings
    from backend.storage import asset_store as astore_mod
    from backend.storage import manager as mgr

    (tmp_path / "projects").mkdir()
    monkeypatch.setattr(mgr, "PROJECTS_DIR", tmp_path / "projects")
    store = astore_mod.AssetStore(tmp_path / "assets", tmp_path / "assets" / "index.json")
    monkeypatch.setattr(astore_mod, "asset_store", store)

    import backend.api.agent as agent_mod
    import backend.api.assets as assets_mod
    for mod in (agent_mod, assets_mod):
        monkeypatch.setattr(mod, "asset_store", store)
    monkeypatch.setattr(settings.swarmui, "currentLoras", [])
    monkeypatch.setattr(settings.swarmui, "promptSuffix", "")

    captured = {}

    async def fake_generate(**kwargs):
        captured.clear()
        captured.update(kwargs)
        return {"success": True, "image": solid_png((120, 160, 200)), "path": "mock"}

    monkeypatch.setattr(agent_mod.swarm_client, "generate_image",
                        AsyncMock(side_effect=fake_generate))

    from backend.main import app
    return TestClient(app, client=("127.0.0.1", 50000)), captured


def _project(c):
    r = c.post("/api/agent/projects", json={
        "name": "loras", "panels": [
            {"scene": "solo", "characters": ["Nova"], "dialogue": ""},
            {"scene": "pair", "characters": ["nova", "Mara"], "dialogue": ""},
            {"scene": "no lora", "characters": ["Jun"], "dialogue": ""}]})
    assert r.status_code == 200, r.text
    project = r.json()["project"]
    return project["id"], [p["id"] for p in project["panels"]]


def _names(loras):
    return {l.name: l.weight for l in loras or []}


# --- conditioning_for_panel ---------------------------------------------------

def test_conditioning_solo_full_weight(library):
    from backend.prompting import conditioning_for_panel
    cond = conditioning_for_panel({}, {"characters": ["NOVA"]})
    assert _names(cond["loras"]) == {"SecondFloor/sf_nova": 0.8}
    assert cond["triggers"] == ["sfnova"]


def test_conditioning_multi_character_scaled_and_default_trigger(library):
    from backend.prompting import conditioning_for_panel
    cond = conditioning_for_panel({}, {"characters": ["Nova", "Mara", "Jun"]})
    # 0.6 of each weight; the .safetensors extension is dropped; Jun has none
    assert _names(cond["loras"]) == {"SecondFloor/sf_nova": 0.48, "SecondFloor/sf_mara": 0.6}
    # Mara's trigger follows the name convention (sf_mara -> sfmara)
    assert cond["triggers"] == ["sfnova", "sfmara"]


def test_conditioning_project_entry_wins(library):
    from backend.prompting import conditioning_for_panel
    project = {"settings": {"characters": [
        {"name": "Nova", "prompt_block": "x", "lora": {"name": "Other/nova_v2", "weight": 0.5, "trigger": ""}}]}}
    cond = conditioning_for_panel(project, {"characters": ["Nova"]})
    assert _names(cond["loras"]) == {"Other/nova_v2": 0.5}
    assert cond["triggers"] == []   # an explicit empty trigger means none


def test_conditioning_no_characters(library):
    from backend.prompting import conditioning_for_panel
    assert conditioning_for_panel({}, {"characters": []}) == {"loras": [], "triggers": [], "reference": None}


# --- generation paths -----------------------------------------------------------

def test_agent_generate_injects_panel_loras(client):
    c, captured = client
    pid, panels = _project(c)
    r = c.post("/api/agent/generate", json={
        "project_id": pid, "panel_id": panels[0], "prompt": "rooftop, evening"})
    assert r.status_code == 200, r.text
    assert _names(captured["loras"]) == {"SecondFloor/sf_nova": 0.8}
    assert "sfnova" in captured["prompt"]
    kinds = [i for i in r.json()["injected"] if i["kind"] == "lora"]
    assert kinds == [{"kind": "lora", "text": "<lora:SecondFloor/sf_nova:0.8>",
                      "name": "SecondFloor/sf_nova", "weight": 0.8, "trigger": "sfnova"}]


def test_agent_generate_multi_character_and_merge(client):
    c, captured = client
    pid, panels = _project(c)
    # a request LoRA stays; the same LoRA as a panel character's takes the character weight
    r = c.post("/api/agent/generate", json={
        "project_id": pid, "panel_id": panels[1], "prompt": "two friends",
        "loras": [{"name": "style/inkwash", "weight": 0.4},
                  {"name": "SecondFloor/sf_nova", "weight": 1.1}]})
    assert r.status_code == 200, r.text
    assert _names(captured["loras"]) == {"style/inkwash": 0.4, "SecondFloor/sf_nova": 0.48,
                                         "SecondFloor/sf_mara": 0.6}
    assert "sfnova" in captured["prompt"] and "sfmara" in captured["prompt"]


def test_agent_generate_respects_existing_tag_and_opt_out(client):
    c, captured = client
    pid, panels = _project(c)
    # a converted comic prompt already carries the tag and trigger: nothing doubled
    prompt = "rooftop, sfnova <lora:SecondFloor/sf_nova:0.8>"
    r = c.post("/api/agent/generate", json={
        "project_id": pid, "panel_id": panels[0], "prompt": prompt})
    assert r.status_code == 200, r.text
    assert not captured["loras"]
    assert captured["prompt"].count("sfnova") == 1
    assert not [i for i in r.json()["injected"] if i["kind"] == "lora"]
    # inject_characters: false leaves the LoRAs out too
    c.post("/api/agent/generate", json={
        "project_id": pid, "panel_id": panels[0], "prompt": "rooftop", "inject_characters": False})
    assert not captured["loras"] and "sfnova" not in captured["prompt"]
    # a character without a LoRA adds none
    c.post("/api/agent/generate", json={"project_id": pid, "panel_id": panels[2], "prompt": "street"})
    assert not captured["loras"]


def test_assets_swarmui_generate_injects_panel_loras(client):
    c, captured = client
    pid, panels = _project(c)
    r = c.post("/api/assets/swarmui/generate", json={
        "project_id": pid, "panel_id": panels[1], "prompt": "two friends"})
    assert r.status_code == 200, r.text
    assert _names(captured["loras"]) == {"SecondFloor/sf_nova": 0.48, "SecondFloor/sf_mara": 0.6}
    assert captured["prompt"] == "two friends, sfnova, sfmara"
    # an unknown project just paints the prompt as sent
    c.post("/api/assets/swarmui/generate", json={"project_id": "nope", "panel_id": "x", "prompt": "p"})
    assert captured["prompt"] == "p" and not captured["loras"]


# --- character library + LoRA list ----------------------------------------------

def test_patch_character_lora(client, library):
    c, _ = client
    r = c.patch("/api/characters/char_jun", json={"lora": {"name": "SecondFloor/sf_jun", "weight": 0.7}})
    assert r.status_code == 200, r.text
    jun = next(x for x in json.loads(library.read_text()) if x["id"] == "char_jun")
    assert jun["lora"] == {"name": "SecondFloor/sf_jun", "weight": 0.7, "trigger": None}
    assert c.patch("/api/characters/char_jun", json={"lora": {"weight": "heavy", "name": "x"}}).status_code == 422
    assert c.patch("/api/characters/char_jun", json={"lora": None}).status_code == 200
    jun = next(x for x in json.loads(library.read_text()) if x["id"] == "char_jun")
    assert jun["lora"] is None
    # the full-list save keeps the field
    lib = c.get("/api/characters/").json()
    assert c.post("/api/characters/", json=lib).status_code == 200
    nova = next(x for x in json.loads(library.read_text()) if x["id"] == "char_nova")
    assert nova["lora"]["trigger"] == "sfnova"


def test_swarmui_loras_endpoint(client, monkeypatch):
    c, _ = client
    import backend.api.assets as assets_mod
    mock = AsyncMock(return_value=[
        {"name": "SecondFloor/sf_nova.safetensors", "trigger_phrase": "sfnova", "architecture": "sdxl/lora"},
        {"name": "SecondFloor/sf_you_f1.safetensors", "trigger_phrase": "", "architecture": "sdxl/lora"}])
    monkeypatch.setattr(assets_mod.swarm_client, "list_models", mock)
    r = c.get("/api/assets/swarmui/loras")
    assert r.status_code == 200
    assert mock.await_args.kwargs == {"subtype": "LoRA"}
    assert r.json()["loras"] == [
        {"name": "SecondFloor/sf_nova", "trigger": "sfnova", "architecture": "sdxl/lora"},
        {"name": "SecondFloor/sf_you_f1", "trigger": "sfyouf1", "architecture": "sdxl/lora"}]
