"""Character-sheet references through SwarmUI's IP-Adapter: the character's
``refWeight`` (opt-in, solo panels only), the SwarmUI payload assembly
(``promptimages`` + ``useipadapter`` + ``ipadapterweight``, redacted in the
log), both generation paths and the cached feature probe.

Run: python -m pytest backend/tests/test_character_refs.py -q
"""
import json
import logging
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT.parent))

from backend.tests._fixtures import solid_png  # noqa: E402

SHEET = solid_png((10, 20, 30))
NOVA = {"id": "char_nova", "name": "Nova", "description": "", "appearance": "1girl, blue hair",
        "image": SHEET, "refWeight": 0.5, "sourcePanelIds": []}
MARA = {"id": "char_mara", "name": "Mara", "description": "", "appearance": "1girl, red hair",
        "image": SHEET, "sourcePanelIds": []}          # a sheet, but no refWeight: off
JUN = {"id": "char_jun", "name": "Jun", "description": "", "appearance": "1boy",
       "refWeight": 0.7, "sourcePanelIds": []}         # a weight, but no sheet: off
PRESET = "PLUS (high strength)"


@pytest.fixture
def library(tmp_path, monkeypatch):
    import backend.api.characters as chars_mod
    import backend.prompting as prompting
    from backend.core.config import settings
    f = tmp_path / "characters.json"
    f.write_text(json.dumps([NOVA, MARA, JUN]), encoding="utf-8")
    monkeypatch.setattr(prompting, "_CHARACTERS_FILE", f)
    monkeypatch.setattr(chars_mod, "CHARACTERS_FILE", f)
    monkeypatch.setattr(settings.swarmui, "ipadapterPreset", PRESET)
    monkeypatch.setattr(settings.swarmui, "ipadapterWeightType", "prompt is more important")
    monkeypatch.setattr(settings.swarmui, "ipadapterEnd", 0.7)
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
        "name": "refs", "panels": [
            {"scene": "solo", "characters": ["Nova"], "dialogue": ""},
            {"scene": "pair", "characters": ["Nova", "Mara"], "dialogue": ""},
            {"scene": "no weight", "characters": ["Mara"], "dialogue": ""}]})
    assert r.status_code == 200, r.text
    project = r.json()["project"]
    return project["id"], [p["id"] for p in project["panels"]]


# --- prompting ------------------------------------------------------------------

def test_reference_solo_only_and_opt_in(library):
    from backend.prompting import conditioning_for_panel, reference_for_panel
    ref = reference_for_panel({}, {"characters": ["nova"]})
    assert ref == {"name": "nova", "image": SHEET, "weight": 0.5}
    assert conditioning_for_panel({}, {"characters": ["Nova"]})["reference"]["weight"] == 0.5
    # two people would get one blended face: no reference
    assert reference_for_panel({}, {"characters": ["Nova", "Mara"]}) is None
    # the same name twice is still one person
    assert reference_for_panel({}, {"characters": ["Nova", "NOVA"]})["weight"] == 0.5
    # a sheet without refWeight, a weight without a sheet, nobody: off
    assert reference_for_panel({}, {"characters": ["Mara"]}) is None
    assert reference_for_panel({}, {"characters": ["Jun"]}) is None
    assert reference_for_panel({}, {"characters": []}) is None


def test_reference_project_override_and_weights(library):
    from backend.prompting import normalize_ref_weight, reference_for_panel
    off = {"settings": {"characters": [{"name": "Nova", "prompt_block": "x", "refWeight": 0}]}}
    assert reference_for_panel(off, {"characters": ["Nova"]}) is None
    on = {"settings": {"characters": [{"name": "Mara", "prompt_block": "x", "refWeight": 0.8}]}}
    assert reference_for_panel(on, {"characters": ["Mara"]})["weight"] == 0.8
    assert [normalize_ref_weight(v) for v in (None, "x", -1, 0, 0.25, 3)] == [0, 0, 0, 0, 0.25, 1.0]


def test_reference_sheet_sources(library, tmp_path, monkeypatch):
    """Only data: URLs and managed assets are read; never a filesystem path."""
    from backend.prompting import reference_for_panel
    from backend.storage import asset_store as astore_mod
    store = astore_mod.AssetStore(tmp_path / "a", tmp_path / "a" / "index.json")
    monkeypatch.setattr(astore_mod, "asset_store", store)
    entry = store.save_dataurl(SHEET, project_id=None, kind="upload")
    asset = {"settings": {"characters": [{"name": "Nova", "image": store.url_for(entry["asset_id"])}]}}
    assert reference_for_panel(asset, {"characters": ["Nova"]})["image"].startswith("data:image/png;base64,")
    path = {"settings": {"characters": [{"name": "Nova", "image": "/etc/passwd"}]}}
    assert reference_for_panel(path, {"characters": ["Nova"]}) is None


def test_ipadapter_args(library, monkeypatch):
    from backend.core.config import settings
    from backend.prompting import ipadapter_args
    ref = {"name": "Nova", "image": SHEET, "weight": 0.5}
    # the tuned defaults: prompt-first weighting, released at 70% of the steps
    assert ipadapter_args(ref) == {"prompt_images": [SHEET], "ipadapter": PRESET, "ipadapter_weight": 0.5,
                                   "ipadapter_weight_type": "prompt is more important", "ipadapter_end": 0.7}
    monkeypatch.setattr(settings.swarmui, "ipadapterWeightType", "")
    monkeypatch.setattr(settings.swarmui, "ipadapterEnd", 1.0)
    assert ipadapter_args(ref) == {"prompt_images": [SHEET], "ipadapter": PRESET, "ipadapter_weight": 0.5}
    assert ipadapter_args(None) == {}
    monkeypatch.setattr(settings.swarmui, "ipadapterPreset", "None")
    assert ipadapter_args(ref) == {}


# --- SwarmUI payload --------------------------------------------------------------

class _Resp:
    def __init__(self, data):
        self.status_code = 200
        self._data = data
        self.text = json.dumps(data)

    def json(self):
        return self._data


def _fake_httpx(monkeypatch, posts, routes):
    import backend.core.swarmui_client as sc

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            route = url.rsplit("/API/", 1)[-1]
            posts.append((route, dict(json or {})))
            return _Resp(routes[route](json) if callable(routes[route]) else routes[route])

    monkeypatch.setattr(sc.httpx, "AsyncClient", FakeClient)
    return sc


def test_generate_image_payload_and_redacted_log(monkeypatch, caplog):
    import asyncio
    posts = []
    sc = _fake_httpx(monkeypatch, posts, {
        "GetNewSession": {"session_id": "s1"},
        "GenerateText2Image": {"images": [solid_png((1, 2, 3))]}})
    client = sc.SwarmUIClient()
    with caplog.at_level(logging.INFO, logger="backend.core.swarmui_client"):
        r = asyncio.run(client.generate_image(
            "p", prompt_images=[SHEET, SHEET], ipadapter=PRESET, ipadapter_weight=0.5,
            ipadapter_weight_type="style transfer", ipadapter_end=0.7))
    assert r["success"]
    payload = [b for route, b in posts if route == "GenerateText2Image"][0]
    assert payload["promptimages"] == f"{SHEET}|{SHEET}"
    assert payload["useipadapter"] == PRESET
    assert payload["ipadapterweight"] == 0.5
    assert payload["ipadapterweighttype"] == "style transfer"
    assert payload["ipadapterend"] == 0.7
    # the sheet's base64 never reaches the log
    assert SHEET.split(",", 1)[1][:40] not in caplog.text
    assert "promptimages" in caplog.text

    # no preset (or no images): nothing IP-Adapter is sent, so SwarmUI never
    # reads the images as ReVision input
    posts.clear()
    asyncio.run(client.generate_image("p", prompt_images=[SHEET]))
    asyncio.run(client.generate_image("p", ipadapter=PRESET, ipadapter_weight=0.5))
    for route, body in posts:
        if route == "GenerateText2Image":
            assert not {"promptimages", "useipadapter", "ipadapterweight", "ipadapterend"} & set(body)


def test_ipadapter_features_probe(monkeypatch):
    import asyncio
    params = {"list": [{"id": "useipadapter", "values": ["None", PRESET, "PLUS FACE (portraits)"]}]}
    sc = _fake_httpx(monkeypatch, [], {
        "GetNewSession": {"session_id": "s1"},
        "ListBackends": {"0": {"status": "running", "features": ["comfyui", "ipadapter"]}},
        "ListT2IParams": params})
    assert asyncio.run(sc.SwarmUIClient().ipadapter_features()) == {
        "ipadapter": True, "presets": [PRESET, "PLUS FACE (portraits)"]}
    sc = _fake_httpx(monkeypatch, [], {
        "GetNewSession": {"session_id": "s1"},
        "ListBackends": {"0": {"status": "running", "features": ["comfyui"]}},
        "ListT2IParams": params})
    assert asyncio.run(sc.SwarmUIClient().ipadapter_features())["ipadapter"] is False


# --- generation paths -------------------------------------------------------------

def test_agent_generate_sends_reference_on_solo_panel(client):
    c, captured = client
    pid, panels = _project(c)
    r = c.post("/api/agent/generate", json={"project_id": pid, "panel_id": panels[0], "prompt": "rooftop"})
    assert r.status_code == 200, r.text
    assert captured["prompt_images"] == [SHEET]
    assert captured["ipadapter"] == PRESET and captured["ipadapter_weight"] == 0.5
    refs = [i for i in r.json()["injected"] if i["kind"] == "reference"]
    assert refs == [{"kind": "reference", "name": "Nova", "weight": 0.5, "preset": PRESET}]
    # a pair, a character without refWeight, inject_characters: false → no reference
    for body in ({"panel_id": panels[1]}, {"panel_id": panels[2]},
                 {"panel_id": panels[0], "inject_characters": False}):
        r = c.post("/api/agent/generate", json={"project_id": pid, "prompt": "x", **body})
        assert r.status_code == 200, r.text
        assert "prompt_images" not in captured and "ipadapter" not in captured


def test_assets_swarmui_generate_sends_reference(client):
    c, captured = client
    pid, panels = _project(c)
    r = c.post("/api/assets/swarmui/generate", json={"project_id": pid, "panel_id": panels[0], "prompt": "p"})
    assert r.status_code == 200, r.text
    assert captured["prompt_images"] == [SHEET] and captured["ipadapter_weight"] == 0.5
    c.post("/api/assets/swarmui/generate", json={"project_id": pid, "panel_id": panels[1], "prompt": "p"})
    assert "prompt_images" not in captured


def test_swarmui_features_endpoint_cached(client, monkeypatch):
    c, _ = client
    import backend.api.assets as assets_mod
    monkeypatch.setattr(assets_mod, "_features_cache", {"at": 0.0, "address": None, "value": None})
    mock = AsyncMock(return_value={"ipadapter": False, "presets": []})
    monkeypatch.setattr(assets_mod.swarm_client, "ipadapter_features", mock)
    for _ in range(3):
        r = c.get("/api/assets/swarmui/features")
        assert r.status_code == 200
        assert r.json() == {"ipadapter": False, "presets": [], "preset": PRESET}
    assert mock.await_count == 1   # cached for 60 s
    monkeypatch.setattr(assets_mod, "_FEATURES_TTL", -1.0)
    c.get("/api/assets/swarmui/features")
    assert mock.await_count == 2


# --- character library ---------------------------------------------------------------

def test_patch_character_ref_weight(client, library):
    c, _ = client
    assert c.patch("/api/characters/char_mara", json={"refWeight": 0.6}).status_code == 200
    mara = next(x for x in json.loads(library.read_text()) if x["id"] == "char_mara")
    assert mara["refWeight"] == 0.6
    for bad in (1.5, -0.1, "strong", True):
        assert c.patch("/api/characters/char_mara", json={"refWeight": bad}).status_code == 422
    assert c.patch("/api/characters/char_mara", json={"refWeight": 0}).status_code == 200
    mara = next(x for x in json.loads(library.read_text()) if x["id"] == "char_mara")
    assert mara["refWeight"] is None
    # the full-list save keeps the field
    lib = c.get("/api/characters/").json()
    assert c.post("/api/characters/", json=lib).status_code == 200
    nova = next(x for x in json.loads(library.read_text()) if x["id"] == "char_nova")
    assert nova["refWeight"] == 0.5
