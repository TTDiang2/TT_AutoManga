"""Content rating (backend/content_rating.py): SFW by default, opt-in Mature
for adult fictional characters, and the minor protections that apply in every
mode on every generation path (agent /generate and /generate-batch, Assets
/api/assets/swarmui/generate, the Characters tab's sheet, LoRA dataset
generation; the MCP tools go through the agent API).

SwarmUI is mocked; storage, the character library and settings.json live in
tmp_path.

Run: python -m pytest backend/tests/test_content_rating.py -q
"""
import json
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT.parent))

from backend import content_rating as cr  # noqa: E402
from backend.tests._fixtures import solid_png  # noqa: E402

SFW_TOKENS = ["nsfw", "nude", "naked", "nipples", "cleavage", "underwear", "lingerie"]
AGE_NEG_TOKENS = ["child", "loli", "shota", "childlike", "teen", "young", "underage", "petite child body"]

LIBRARY = [
    {"id": "c_ava", "name": "Ava", "description": "", "appearance": "1girl, long black hair", "age": 29,
     "sourcePanelIds": []},
    {"id": "c_ben", "name": "Ben", "description": "", "appearance": "1boy, adult man, beard",
     "sourcePanelIds": []},
    {"id": "c_kim", "name": "Kim", "description": "", "appearance": "1girl, red hair",
     "sourcePanelIds": []},                                      # no age: unknown
    {"id": "c_lia", "name": "Lia", "description": "", "appearance": "1girl, 15 years old, ponytail",
     "sourcePanelIds": []},                                      # a minor by description
    {"id": "c_tom", "name": "Tom", "description": "", "appearance": "1boy, short hair", "age": 12,
     "sourcePanelIds": []},                                      # a minor by age
    {"id": "c_old", "name": "Rae", "description": "", "appearance": "1girl, 34 years old",
     "sourcePanelIds": []},                                      # adult by description
]

MINOR_PROMPTS = [
    "a 16 years old girl", "16-year-old", "a sixteen year old", "17yo", "aged 15", "age: 14",
    "teenage girl", "teen", "teens at a party", "teenager", "pre-teen", "preteen", "tween",
    "schoolgirl", "schoolgirl uniform", "schoolboy", "school girl", "child", "children", "childlike",
    "kid", "kids", "underage", "under-age", "loli", "lolicon", "shota", "shotacon",
    "young girl", "young_boy", "little girl", "little boy", "toddler", "baby", "infant",
    "minor", "middle school", "high school student", "highschooler", "junior high", "jailbait",
    "TEENAGE", "Young Girl",
]
ADULT_PROMPTS = ["two adults kissing, bedroom", "a 25 years old woman", "twenty-five years old",
                 "woman in her thirties", "canteen at night", "fifteen candles on the table"]


# ---------------------------------------------------------------- pure rules

@pytest.mark.parametrize("text", MINOR_PROMPTS)
def test_minor_terms_found(text):
    assert cr.minor_terms(text), text


@pytest.mark.parametrize("text", ADULT_PROMPTS)
def test_adult_prompts_have_no_minor_terms(text):
    assert cr.minor_terms(text) == [], text


def test_classify():
    assert cr.classify(30, "1girl")["status"] == "adult"
    assert cr.classify(17, "1girl, adult woman")["status"] == "minor"       # explicit age < 18
    assert cr.classify(30, "1girl, teenage")["status"] == "minor"           # a minor description wins
    assert cr.classify(None, "1girl, 16 years old")["status"] == "minor"
    assert cr.classify(None, "1girl, 40 years old")["status"] == "adult"
    assert cr.classify(None, "adult woman")["status"] == "adult"
    assert cr.classify(None, "1girl, red hair")["status"] == "unknown"
    assert cr.classify("abc", "1girl")["status"] == "unknown"                # invalid age = unset


def test_decide_mature_needs_known_adults():
    d = cr.decide("mature", [{"name": "A", "age": 30, "text": "1girl"}])
    assert d["rating"] == "mature" and not d["forced"]
    d = cr.decide("mature", [{"name": "A", "age": 30, "text": ""}, {"name": "K", "age": None, "text": "1girl"}])
    assert d["rating"] == "sfw" and d["forced"] and "K has no age" in d["notice"]
    d = cr.decide("mature", [{"name": "L", "age": None, "text": "1girl, 15 years old"}])
    assert d["rating"] == "sfw" and "L is a minor" in d["notice"]
    d = cr.decide("sfw", [{"name": "K", "age": None, "text": ""}])
    assert d["rating"] == "sfw" and not d["forced"] and d["notice"] is None


def test_apply_rating_tokens():
    sfw = cr.apply_rating("p", "blurry", cast=[], rating="sfw")
    assert sfw["negative"] == "blurry, " + cr.SFW_NEG and sfw["prompt"] == "p"
    mature = cr.apply_rating("p", "blurry", cast=[{"name": "A", "age": 30, "text": ""}], rating="mature")
    assert mature["prompt"] == "p, " + cr.AGE_POS
    assert mature["negative"] == "blurry, " + cr.AGE_NEG
    assert not any(t in mature["negative"].split(", ") for t in SFW_TOKENS)
    # tokens already there are not repeated
    again = cr.apply_rating(mature["prompt"], mature["negative"], cast=[{"name": "A", "age": 30, "text": ""}],
                            rating="mature")
    assert again["prompt"] == mature["prompt"] and again["negative"] == mature["negative"]
    with pytest.raises(cr.RatingRefused):
        cr.apply_rating("a teenage girl", "", cast=[], rating="mature")
    # SFW never refuses (the SFW negatives are added instead)
    assert cr.apply_rating("a teenage girl", "", cast=[], rating="sfw")["rating"] == "sfw"
    # training: always SFW, even when mature is asked for
    t = cr.apply_rating("1girl", "x", cast=[], rating="mature", force_sfw=True)
    assert t["rating"] == "sfw" and cr.SFW_NEG in t["negative"]


# ---------------------------------------------------------------- app fixture

@pytest.fixture
def env(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import backend.api.agent as agent_mod
    import backend.api.assets as assets_mod
    import backend.api.characters as chars_mod
    import backend.prompting as prompting
    from backend.core import config
    from backend.storage import asset_store as astore_mod
    from backend.storage import manager as mgr

    (tmp_path / "projects").mkdir()
    monkeypatch.setattr(mgr, "PROJECTS_DIR", tmp_path / "projects")
    store = astore_mod.AssetStore(tmp_path / "assets", tmp_path / "assets" / "index.json")
    monkeypatch.setattr(astore_mod, "asset_store", store)
    for mod in (agent_mod, assets_mod):
        monkeypatch.setattr(mod, "asset_store", store)
    lib = tmp_path / "characters.json"
    lib.write_text(json.dumps(LIBRARY), encoding="utf-8")
    monkeypatch.setattr(prompting, "_CHARACTERS_FILE", lib)
    monkeypatch.setattr(chars_mod, "CHARACTERS_FILE", lib)
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(config.settings, "content", config.ContentConfig())
    monkeypatch.setattr(config.settings.swarmui, "currentLoras", [])
    monkeypatch.setattr(config.settings.swarmui, "promptSuffix", "")

    calls = []

    async def fake_generate(**kwargs):
        calls.append(kwargs)
        return {"success": True, "image": solid_png((120, 160, 200), (32, 32)), "path": "mock"}

    monkeypatch.setattr(agent_mod.swarm_client, "generate_image", AsyncMock(side_effect=fake_generate))

    from backend.main import app
    client = TestClient(app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1")

    class Env:
        pass
    e = Env()
    e.c, e.calls, e.config, e.tmp = client, calls, config, tmp_path
    return e


PANELS = [
    {"id": "solo_adult", "scene": "Ava on the sofa", "characters": ["Ava"]},
    {"id": "adults", "scene": "Ava and Ben", "characters": ["Ava", "Ben", "Rae"]},
    {"id": "unknown", "scene": "Ava and Kim", "characters": ["Ava", "Kim"]},
    {"id": "minor_desc", "scene": "Ava and Lia", "characters": ["Ava", "Lia"]},
    {"id": "minor_age", "scene": "Tom", "characters": ["Tom"]},
    {"id": "nobody_known", "scene": "a stranger", "characters": ["Zed"]},
    {"id": "scene_kid", "scene": "Ava walks a kid to class", "characters": ["Ava"]},
    {"id": "empty", "scene": "an empty street"},
]


def _project(e, rating=None):
    r = e.c.post("/api/agent/projects", json={"name": "rated", "panels": PANELS})
    assert r.status_code == 200, r.text
    pid = r.json()["project"]["id"]
    if rating is not None:
        r = e.c.put(f"/api/agent/projects/{pid}/settings", json={"contentRating": rating})
        assert r.status_code == 200, r.text
    return pid


def _gen(e, pid, panel, prompt="a quiet scene", **kw):
    return e.c.post("/api/agent/generate", json={"project_id": pid, "panel_id": panel, "prompt": prompt,
                                                 "negative_prompt": "blurry", "apply_to_panel": False, **kw})


def _assets(e, pid, panel, prompt="a quiet scene"):
    return e.c.post("/api/assets/swarmui/generate", json={"project_id": pid, "panel_id": panel,
                                                         "prompt": prompt, "negative_prompt": "blurry"})


def _sfw(kwargs):
    neg = [t.strip() for t in kwargs["negative_prompt"].split(",")]
    return all(t in neg for t in SFW_TOKENS)


def _mature(kwargs):
    neg = kwargs["negative_prompt"]
    return (not any(t in [x.strip() for x in neg.split(",")] for t in SFW_TOKENS)
            and all(t in neg for t in AGE_NEG_TOKENS) and cr.AGE_POS in kwargs["prompt"])


# ---------------------------------------------------------------- settings

def test_settings_default_rating(env):
    c = env.c
    assert c.get("/api/settings/").json()["content"] == {"defaultRating": "sfw"}
    assert c.post("/api/settings/", json={"content": {"defaultRating": "nsfw"}}).status_code == 422
    assert c.post("/api/settings/", json={"content": {"defaultRating": "mature"}}).status_code == 200
    assert c.get("/api/settings/").json()["content"]["defaultRating"] == "mature"
    saved = json.loads((env.tmp / "settings.json").read_text())
    assert saved["content"]["defaultRating"] == "mature"


def test_project_rating_setting(env):
    pid = _project(env)
    c = env.c
    assert c.put(f"/api/agent/projects/{pid}/settings", json={"contentRating": "porn"}).status_code == 400
    r = c.put(f"/api/agent/projects/{pid}/settings", json={"contentRating": "MATURE"})
    assert r.json()["settings"]["contentRating"] == "mature"
    r = c.put(f"/api/agent/projects/{pid}/settings", json={"contentRating": ""})
    assert "contentRating" not in r.json()["settings"]


def test_character_age_field(env):
    c = env.c
    assert c.patch("/api/characters/c_kim", json={"age": 200}).status_code == 422
    assert c.patch("/api/characters/c_kim", json={"age": "30"}).status_code == 422
    assert c.patch("/api/characters/c_kim", json={"age": 31}).status_code == 200
    assert next(x for x in c.get("/api/characters/").json() if x["id"] == "c_kim")["age"] == 31
    assert c.patch("/api/characters/c_kim", json={"age": None}).status_code == 200
    r = c.post("/api/characters/add", json={"id": "c_new", "name": "New", "age": 140})
    assert r.status_code == 422
    r = c.post("/api/characters/add", json={"id": "c_new", "name": "New", "age": 40})
    assert r.status_code == 200


# ---------------------------------------------------------------- SFW (default)

def test_sfw_default_every_path(env, monkeypatch):
    pid = _project(env)
    for panel in ("solo_adult", "minor_age", "unknown", "empty"):
        r = _gen(env, pid, panel)
        assert r.status_code == 200, r.text
        assert _sfw(env.calls[-1]) and cr.AGE_POS not in env.calls[-1]["prompt"]
        assert r.json()["content_rating"] == "sfw"
        assert {"kind": "rating", "rating": "sfw", "requested": "sfw"} in r.json()["injected"]
        assert "notice" not in r.json()
        r = _assets(env, pid, panel)
        assert r.status_code == 200, r.text
        assert _sfw(env.calls[-1]) and r.json()["content_rating"] == "sfw"
    # no project at all: the global default
    r = env.c.post("/api/agent/generate", json={"prompt": "x", "apply_to_panel": False})
    assert r.status_code == 200 and _sfw(env.calls[-1])
    # SFW never refuses a prompt
    assert _gen(env, pid, "solo_adult", prompt="a teenage girl").status_code == 200
    # the asset's metadata records the rating
    url = r.json()["assets"][0]["url"]
    asset = env.c.get(f"/api/agent/assets/{url.rsplit('/', 1)[-1]}").json()["asset"]
    meta = asset.get("meta", asset)
    assert meta["content_rating"] == "sfw" and _sfw({"negative_prompt": meta["negative_prompt"]})


def test_sfw_batch(env):
    pid = _project(env)
    r = env.c.post("/api/agent/generate-batch", json={"project_id": pid, "jobs": [
        {"panel_id": "solo_adult", "prompt": "a", "apply_to_panel": False},
        {"panel_id": "adults", "prompt": "b", "apply_to_panel": False}]})
    assert r.status_code == 202, r.text
    _wait_job(env, r.json()["job_id"])
    assert len(env.calls) == 2 and all(_sfw(k) for k in env.calls)


def _wait_job(env, job_id):
    snap = None
    for _ in range(100):
        snap = env.c.get(f"/api/agent/jobs/{job_id}").json()
        if snap["status"] == "done":
            break
        time.sleep(0.05)
    assert snap["status"] == "done"
    assert all(it["status"] == "done" for it in snap["items"]), snap
    return snap


def test_mature_project_over_sfw_default_and_back(env, monkeypatch):
    """The project's rating wins over the global default either way."""
    pid = _project(env, "mature")
    assert _gen(env, pid, "solo_adult").status_code == 200 and _mature(env.calls[-1])
    monkeypatch.setattr(env.config.settings, "content", env.config.ContentConfig(defaultRating="mature"))
    pid2 = _project(env, "sfw")
    assert _gen(env, pid2, "solo_adult").status_code == 200 and _sfw(env.calls[-1])
    pid3 = _project(env)          # unset: the (mature) default
    assert _gen(env, pid3, "solo_adult").status_code == 200 and _mature(env.calls[-1])


# ---------------------------------------------------------------- mature

@pytest.mark.parametrize("path", ["agent", "assets"])
def test_mature_all_adult_cast_drops_sfw_negatives(env, path):
    pid = _project(env, "mature")
    send = _gen if path == "agent" else _assets
    for panel in ("solo_adult", "adults", "empty"):
        r = send(env, pid, panel)
        assert r.status_code == 200, r.text
        assert _mature(env.calls[-1]), env.calls[-1]
        assert r.json()["content_rating"] == "mature" and "notice" not in r.json()


@pytest.mark.parametrize("path", ["agent", "assets"])
@pytest.mark.parametrize("panel,why", [
    ("unknown", "Kim has no age"), ("nobody_known", "Zed has no age"),
    ("minor_desc", "Lia is a minor"), ("minor_age", "Tom is a minor (age 12)"),
    ("scene_kid", "scene mentions a minor"),
])
def test_mature_forced_sfw_with_notice(env, path, panel, why):
    pid = _project(env, "mature")
    send = _gen if path == "agent" else _assets
    r = send(env, pid, panel)
    assert r.status_code == 200, r.text
    k = env.calls[-1]
    assert _sfw(k) and cr.AGE_POS not in k["prompt"]
    assert r.json()["content_rating"] == "sfw"
    assert "forced SFW" in r.json()["notice"] and why in r.json()["notice"]
    if path == "agent":
        rating = next(i for i in r.json()["injected"] if i["kind"] == "rating")
        assert rating["requested"] == "mature" and rating["forced"] and why in rating["notice"]


def test_mature_minor_character_never_gets_adult_tokens(env):
    pid = _project(env, "mature")
    _gen(env, pid, "minor_age")
    assert "adult" not in env.calls[-1]["prompt"]


@pytest.mark.parametrize("prompt", MINOR_PROMPTS)
def test_mature_free_prompt_with_minor_terms_is_400(env, prompt):
    pid = _project(env, "mature")
    for r in (_gen(env, pid, "solo_adult", prompt=prompt), _assets(env, pid, "solo_adult", prompt=prompt),
              env.c.post("/api/characters/templates/generate-image",
                         json={"prompt": prompt, "character_id": "c_ava", "project_id": pid})):
        assert r.status_code == 400, (prompt, r.text)
        assert "minor" in r.json()["detail"]
    assert env.calls == []


def test_mature_free_prompt_refused_without_project_when_default_mature(env, monkeypatch):
    monkeypatch.setattr(env.config.settings, "content", env.config.ContentConfig(defaultRating="mature"))
    r = env.c.post("/api/agent/generate", json={"prompt": "a 16 years old", "apply_to_panel": False})
    assert r.status_code == 400
    r = env.c.post("/api/agent/generate", json={"prompt": "two adults", "apply_to_panel": False})
    assert r.status_code == 200 and _mature(env.calls[-1])


def test_mature_batch_refuses_up_front_and_rates_each_job(env):
    pid = _project(env, "mature")
    r = env.c.post("/api/agent/generate-batch", json={"project_id": pid, "jobs": [
        {"panel_id": "solo_adult", "prompt": "fine"},
        {"panel_id": "solo_adult", "prompt": "schoolgirl outfit"}]})
    assert r.status_code == 400 and "job 1" in r.json()["detail"]
    assert env.calls == []
    r = env.c.post("/api/agent/generate-batch", json={"project_id": pid, "jobs": [
        {"panel_id": "solo_adult", "prompt": "a", "apply_to_panel": False},
        {"panel_id": "unknown", "prompt": "b", "apply_to_panel": False}]})
    assert r.status_code == 202
    snap = _wait_job(env, r.json()["job_id"])
    by_prompt = {k["prompt"].split(",")[0]: k for k in env.calls}
    assert _mature(by_prompt["a"]) and _sfw(by_prompt["b"])
    assert "forced SFW" in snap["items"][1]["result"]["notice"]


def test_mcp_generate_goes_through_the_rating(env, monkeypatch):
    """The MCP tool posts to /api/agent/generate: same rules (refusal included)."""
    import asyncio

    import httpx

    from backend import mcp_tools
    pid = _project(env, "mature")

    def handler(request: httpx.Request) -> httpx.Response:
        r = env.c.request(request.method, request.url.path, content=request.content,
                          headers={"content-type": "application/json"})
        return httpx.Response(r.status_code, content=r.content, headers={"content-type": "application/json"})

    monkeypatch.setattr(mcp_tools, "_TRANSPORT", httpx.MockTransport(handler))
    out = asyncio.run(mcp_tools.generate_image("rooftop", project_id=pid, panel_id="unknown",
                                               apply_to_panel=False))
    assert out["content_rating"] == "sfw" and "forced SFW" in out["notice"] and _sfw(env.calls[-1])
    with pytest.raises(mcp_tools.ToolError, match="400"):
        asyncio.run(mcp_tools.generate_image("a teen", project_id=pid, panel_id="solo_adult"))


# ---------------------------------------------------------------- character sheet

def test_character_sheet_uses_its_own_age(env, monkeypatch):
    c = env.c
    gen = lambda cid, prompt="1girl, portrait": c.post(  # noqa: E731
        "/api/characters/templates/generate-image",
        json={"prompt": prompt, "negative_prompt": "low quality", "character_id": cid, "project_id": "default"})
    # SFW default
    r = gen("c_ava")
    assert r.status_code == 200 and _sfw(env.calls[-1]) and r.json()["content_rating"] == "sfw"
    monkeypatch.setattr(env.config.settings, "content", env.config.ContentConfig(defaultRating="mature"))
    r = gen("c_ava")                                      # age 29: mature
    assert r.status_code == 200 and _mature(env.calls[-1])
    for cid, why in (("c_kim", "has no age"), ("c_tom", "is a minor"), ("c_lia", "is a minor"),
                     ("c_unsaved", "has no age")):
        r = gen(cid)
        assert r.status_code == 200 and _sfw(env.calls[-1]), cid
        assert why in r.json()["notice"], (cid, r.json())
    # a mature project's rating applies to a sheet generated for it
    monkeypatch.setattr(env.config.settings, "content", env.config.ContentConfig())
    pid = _project(env, "mature")
    r = c.post("/api/characters/templates/generate-image",
               json={"prompt": "1boy", "character_id": "c_ben", "project_id": pid})
    assert r.status_code == 200 and _mature(env.calls[-1])


# ---------------------------------------------------------------- training

def test_training_dataset_generation_always_sfw(env, monkeypatch, tmp_path):
    import backend.api.training as tapi
    monkeypatch.setattr(tapi, "DATASETS_DIR", tmp_path / "data" / "training")
    monkeypatch.setattr(tapi, "_gen", {})
    monkeypatch.setattr(env.config.settings, "content", env.config.ContentConfig(defaultRating="mature"))
    c = env.c
    r = c.post("/api/training/datasets", json={"slug": "ava", "trigger": "amava", "characterId": "c_ava"})
    assert r.status_code == 200, r.text
    with c:
        r = c.post("/api/training/datasets/ava/generate", json={"count": 3})
        assert r.status_code == 200, r.text
        end = time.time() + 10
        while time.time() < end and c.get("/api/training/datasets/ava").json()["generation"]["running"]:
            time.sleep(0.05)
    assert len(env.calls) == 3
    for k in env.calls:
        assert _sfw(k) and cr.AGE_POS not in k["prompt"]
        assert k["negative_prompt"].startswith(tapi.GEN_NEGATIVE)


def test_assets_path_records_the_rating_in_the_asset(env):
    pid = _project(env, "mature")
    for panel, rating in (("solo_adult", "mature"), ("unknown", "sfw")):
        r = _assets(env, pid, panel)
        assert r.status_code == 200 and r.json()["asset_id"], r.text
        asset = env.c.get(f"/api/agent/assets/{r.json()['asset_id']}").json()["asset"]
        meta = asset.get("meta", asset)
        assert meta["content_rating"] == rating
        assert meta["negative_prompt"] == env.calls[-1]["negative_prompt"]
