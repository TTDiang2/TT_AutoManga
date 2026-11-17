"""Regression tests for the 2026-11 backend review fixes.

One focused test (or a few) per fix: arbitrary file read via export/render
refs, composer-pages optimistic concurrency, orphan-asset grace period,
settings model normalization / in-place reset / SwarmUI address, API-key
leak to foreign endpoints, font resolution, the local-layer renderer,
detached comics runs, atomic JSON writes and the small robustness fixes.
"""
import base64
import io
import json
import os
import shutil
import sys
import time
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT.parent))

from PIL import Image  # noqa: E402

from backend.core import config  # noqa: E402
from backend.tests._fixtures import solid_png  # noqa: E402
from backend.tests.test_e2e_agent import client  # noqa: E402,F401

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _zip_names(path: str):
    with zipfile.ZipFile(path) as zf:
        return {i.filename: zf.read(i) for i in zf.infolist()}


@pytest.fixture
def archive_tmp(tmp_path, monkeypatch):
    """Archive module redirected to tmp_path/archive."""
    import backend.api.archive as arch
    d = tmp_path / "archive"
    d.mkdir()
    monkeypatch.setattr(arch, "ARCHIVE_DIR", d)
    monkeypatch.setattr(arch, "METADATA_FILE", d / "metadata.json")
    monkeypatch.setattr(arch, "ARCHIVE_ROOT", d.resolve())
    return arch


# ---------------------------------------------------------------------------
# 1. arbitrary file read through export / render refs
# ---------------------------------------------------------------------------

def test_export_images_refuses_filesystem_paths(client, tmp_path):
    secret = tmp_path / "id_rsa"
    secret.write_bytes(b"-----BEGIN TOPSECRET KEY-----")
    r = client.post("/api/export/images", json={
        "project_id": "x", "panels": [{"image": str(secret)},
                                      {"image": solid_png((1, 2, 3), (8, 8))}]})
    assert r.status_code == 200
    entries = _zip_names(r.json()["file"])
    assert all(b"TOPSECRET" not in v for v in entries.values())
    assert list(entries) == ["panel_002.png"]   # the data: URL still exports


def test_export_pdf_refuses_filesystem_paths(client, tmp_path):
    secret = tmp_path / "secret.png"
    Image.new("RGB", (4, 4), (1, 2, 3)).save(secret)
    r = client.post("/api/export/pdf", json={
        "project_id": "x", "include_cover": False, "panels": [{"image": str(secret)}]})
    assert r.status_code == 200
    # one page, no embedded image XObject
    assert b"/Subtype /Image" not in Path(r.json()["file"]).read_bytes()


def test_export_validates_project_id_and_format(client):
    for bad in ("../x", "a/b", ".."):
        r = client.post("/api/export/images", json={"project_id": bad, "panels": []})
        assert r.status_code == 400, bad
        r = client.post("/api/export/pdf", json={"project_id": bad, "panels": []})
        assert r.status_code == 400, bad
    r = client.post("/api/export/images", json={
        "project_id": "x", "panels": [], "format": "png/../../evil"})
    assert r.status_code == 400


def test_export_accepts_asset_and_archive_refs(client, archive_tmp):
    from backend.storage import asset_store as astore_mod
    entry = astore_mod.asset_store.save_bytes(PNG_1PX)
    # add an archive image the regular way, then reference it by serve URL
    r = client.post("/api/archive/images", json={
        "source_data": "data:image/png;base64," + base64.b64encode(PNG_1PX).decode()})
    assert r.status_code == 200
    arch_id = r.json()["id"]
    r = client.post("/api/export/images", json={"project_id": "x", "panels": [
        {"image": f"/api/assets/file/{entry['asset_id']}"},
        {"image": f"/api/archive/images/{arch_id}/serve?t=1"},
        {"image": "/api/archive/images/nope/serve"}]})
    entries = _zip_names(r.json()["file"])
    assert entries == {"panel_001.png": PNG_1PX, "panel_002.png": PNG_1PX}


def test_archive_ref_outside_archive_is_refused(client, archive_tmp, tmp_path):
    # metadata pointing outside data/archive (tampered/legacy) never resolves
    outside = tmp_path / "outside.png"
    outside.write_bytes(PNG_1PX)
    archive_tmp.save_metadata(archive_tmp.ArchiveMetadata(images=[
        archive_tmp.ArchiveImage(id="evil", name="e", path=str(outside),
                                 created_at="0")], folders=[]))
    assert archive_tmp.resolve_archive_ref("/api/archive/images/evil/serve") is None


def test_render_page_ignores_filesystem_paths(client, tmp_path):
    secret = tmp_path / "red.png"
    Image.new("RGB", (50, 50), (255, 0, 0)).save(secret)
    page = {"width": 100, "height": 100, "elements": [
        {"id": "a", "type": "image", "src": str(secret), "x": 0, "y": 0,
         "width": 100, "height": 100, "frameBorderWidth": 0}]}
    r = client.post("/api/render/page", json={"page": page, "scale": 1})
    assert r.status_code == 200
    img = Image.open(io.BytesIO(r.content)).convert("RGB")
    assert img.getpixel((50, 50)) == (255, 255, 255)   # nothing was read


# ---------------------------------------------------------------------------
# 2. composer pages: optimistic concurrency + save guard
# ---------------------------------------------------------------------------

def _project_with_pages(client):
    pid = client.post("/api/agent/projects", json={"name": "cc"}).json()["project"]["id"]
    client.put(f"/api/agent/projects/{pid}/panels", json={"panels": [{"scene": "s1"}]})
    r = client.put(f"/api/projects/{pid}/composer-pages", json={
        "pages": [{"id": "pg1", "name": "one", "elements": []}], "base": None})
    assert r.status_code == 200
    return pid, r.json()["base"]


def test_composer_pages_put_and_conflict(client):
    from backend.storage.manager import pages_base
    pid, base = _project_with_pages(client)
    loaded = client.get(f"/api/projects/load/{pid}").json()
    assert loaded["pagesBase"] == base == pages_base(loaded["project"])

    # a write based on the current version succeeds and moves the base
    r = client.put(f"/api/projects/{pid}/composer-pages", json={
        "pages": [{"id": "pg1", "name": "renamed", "elements": []}], "base": base})
    assert r.status_code == 200
    new_base = r.json()["base"]
    assert new_base != base and r.json()["success"] is True and r.json()["updatedAt"]

    # a stale writer is refused with the current base, nothing is written
    r = client.put(f"/api/projects/{pid}/composer-pages", json={
        "pages": [], "base": base})
    assert r.status_code == 409
    assert r.json() == {"detail": "pages changed elsewhere", "base": new_base}
    proj = client.get(f"/api/projects/load/{pid}").json()["project"]
    assert proj["composerPages"][0]["name"] == "renamed"
    # only composerPages is ever touched
    assert proj["panels"][0]["scene"] == "s1" and proj["name"] == "cc"


def test_composer_pages_put_unknown_or_bad_project(client):
    assert client.put("/api/projects/nope/composer-pages",
                      json={"pages": [], "base": None}).status_code == 404
    assert client.put("/api/projects/a..b/composer-pages",
                      json={"pages": [], "base": None}).status_code == 400


def test_save_empty_composer_pages_keeps_stored(client):
    pid, _ = _project_with_pages(client)
    r = client.post("/api/projects/save", json={
        "id": pid, "name": "cc", "panels": [], "settings": {}, "composerPages": []})
    assert r.status_code == 200
    proj = client.get(f"/api/projects/load/{pid}").json()["project"]
    assert len(proj["composerPages"]) == 1


# ---------------------------------------------------------------------------
# 3. orphan cleanup grace period
# ---------------------------------------------------------------------------

def test_cleanup_keeps_fresh_orphans_and_flushes_once(tmp_path, monkeypatch):
    import backend.main as main_mod
    from backend.storage import asset_store as astore_mod
    store = astore_mod.AssetStore(tmp_path / "assets", tmp_path / "assets" / "index.json")
    monkeypatch.setattr(astore_mod, "asset_store", store)
    (tmp_path / "projects").mkdir()
    monkeypatch.setattr(main_mod, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(main_mod, "ASSETS_DIR", tmp_path / "assets")

    fresh = store.save_bytes(PNG_1PX, kind="variant")       # unapplied variant
    old1 = store.save_bytes(PNG_1PX, kind="panel")
    old2 = store.save_bytes(PNG_1PX, kind="upload")
    no_date = store.save_bytes(PNG_1PX, kind="upload")
    store._index[old1["asset_id"]]["created_at"] = "2020-01-01T00:00:00Z"
    store._index[old2["asset_id"]]["created_at"] = "2020-01-02T00:00:00Z"
    # no created_at: the file mtime decides (old file → removable)
    del store._index[no_date["asset_id"]]["created_at"]
    os.utime(no_date["path"], (time.time() - 30 * 86400,) * 2)

    flushes = []
    orig = store._flush
    monkeypatch.setattr(store, "_flush", lambda: (flushes.append(1), orig())[1])
    main_mod._cleanup_orphan_assets()
    assert store.get(fresh["asset_id"]) is not None
    assert Path(fresh["path"]).exists()
    for e in (old1, old2, no_date):
        assert store.get(e["asset_id"]) is None
        assert not Path(e["path"]).exists()
    assert len(flushes) == 1
    # the persisted index agrees
    assert set(json.loads((tmp_path / "assets" / "index.json").read_text())) \
        == {fresh["asset_id"]}


# ---------------------------------------------------------------------------
# 4. settings: model instances, in-place reset, SwarmUI address
# ---------------------------------------------------------------------------

@pytest.fixture
def settings_tmp(monkeypatch, tmp_path):
    """Redirect settings.json and snapshot/restore the live settings object."""
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    saved = config.settings.model_copy(deep=True)
    yield config.settings
    for name in config.AppSettings.model_fields:
        setattr(config.settings, name, getattr(saved, name))


def test_settings_post_stores_model_instances(client, settings_tmp):
    r = client.post("/api/settings/", json={"swarmui": {
        "currentLoras": [{"name": "ink", "weight": 0.5}],
        "presets": [{"id": "p", "name": "P", "loras": [{"name": "x"}]}]}})
    assert r.status_code == 200
    sw = config.settings.swarmui
    assert isinstance(sw.currentLoras[0], config.LoraConfig)
    assert sw.currentLoras[0].name == "ink"
    assert isinstance(sw.presets[0], config.SwarmUIPreset)
    assert isinstance(sw.presets[0].loras[0], config.LoraConfig)
    # readers use attribute access and now work: agent view + character gen
    assert client.get("/api/agent/settings").json()["swarmui"]["currentLoras"] \
        == [{"name": "ink", "weight": 0.5}]
    assert client.post("/api/settings/", json={"swarmui": {
        "currentLoras": [{"name": "x", "weight": "heavy"}]}}).status_code == 400


def test_character_template_generation_with_settings_loras(client, settings_tmp,
                                                           monkeypatch):
    import backend.api.character_templates as ct
    config.settings.swarmui.currentLoras = [config.LoraConfig(name="ink", weight=0.7)]
    gen = AsyncMock(return_value={"success": True, "image": "data:,"})
    monkeypatch.setattr(ct.swarm_client, "generate_image", gen)
    r = client.post("/api/characters/templates/generate-image", json={
        "prompt": "x", "character_id": "c", "project_id": "p"})
    assert r.status_code == 200, r.text
    assert gen.call_args.kwargs["loras"][0].name == "ink"


def test_settings_reset_is_in_place(client, settings_tmp):
    import backend.api.agent as agent_mod
    import backend.core.swarmui_client as sc
    before = config.settings
    config.settings.swarmui.currentSteps = 77
    r = client.post("/api/settings/reset")
    assert r.status_code == 200
    assert config.settings is before
    # modules that imported the object see the defaults
    assert agent_mod.settings.swarmui.currentSteps == 20
    assert sc.settings is config.settings


def test_swarm_client_reads_address_per_call(settings_tmp):
    from backend.core.swarmui_client import swarm_client
    config.settings.swarmui.address = "10.0.0.5:7801"
    assert swarm_client.address == "http://10.0.0.5:7801"
    config.settings.swarmui.address = "http://127.0.0.1:9999/"
    assert swarm_client.address == "http://127.0.0.1:9999"


def test_swarm_request_address_is_one_shot(client, settings_tmp, monkeypatch):
    import backend.api.assets as assets_mod
    from backend.core import swarmui_client as sc
    config.settings.swarmui.address = "http://127.0.0.1:7801"
    seen = []

    class FakeResp:
        status_code = 200

        def __init__(self, data):
            self._d = data

        def json(self):
            return self._d

    class FakeHTTP:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            seen.append(url)
            if url.endswith("GetNewSession"):
                return FakeResp({"session_id": "s"})
            return FakeResp({"images": ["data:image/png;base64,"
                                        + base64.b64encode(PNG_1PX).decode()]})

    monkeypatch.setattr(sc.httpx, "AsyncClient", FakeHTTP)
    # the e2e fixture mocks agent's generate_image; this endpoint uses the real one
    monkeypatch.setattr(assets_mod.swarm_client, "generate_image",
                        sc.SwarmUIClient.generate_image.__get__(assets_mod.swarm_client))
    r = client.post("/api/assets/swarmui/generate", json={
        "prompt": "x", "panel_id": "p", "project_id": "nope",
        "swarmui_address": "192.168.1.9:7801"})
    assert r.status_code == 200 and r.json()["success"], r.text
    assert seen and all(u.startswith("http://192.168.1.9:7801/") for u in seen)
    assert sc.swarm_client.address == "http://127.0.0.1:7801"   # not stored


# ---------------------------------------------------------------------------
# 5. stored API key never goes to a foreign endpoint
# ---------------------------------------------------------------------------

@pytest.fixture
def llm_spy(monkeypatch):
    from backend.core import openai_client
    monkeypatch.setattr(config.settings.api, "endpoint", "https://api.real.example/v1")
    monkeypatch.setattr(config.settings.api, "api_key", "sk-STORED-1234")
    sent = {}

    async def fake_chat(self, messages, temperature=None, system_prompt=None):
        sent["endpoint"], sent["api_key"] = self.endpoint, self.api_key
        return {"choices": [{"message": {"content": '[{"id":"panel_1","scene":"s"}]'}}]}

    monkeypatch.setattr(openai_client.OpenAIClient, "chat_completion", fake_chat)
    return sent


@pytest.mark.parametrize("path", ["/api/storyboard/generate", "/api/agent/storyboard"])
def test_foreign_endpoint_never_gets_stored_key(client, llm_spy, path):
    body = {"text": "hi", "endpoint": "https://evil.example/v1"}
    if path == "/api/agent/storyboard":
        pid = client.post("/api/agent/projects", json={"name": "k"}).json()["project"]["id"]
        body["project_id"] = pid
    client.post(path, json=body)
    assert llm_spy["endpoint"] == "https://evil.example/v1"
    assert llm_spy["api_key"] == ""
    # masked echo of the stored key does not count as a key either
    client.post(path, json={**body, "api_key": "****1234"})
    assert llm_spy["api_key"] == ""
    # the request's own key goes to its own endpoint
    client.post(path, json={**body, "api_key": "sk-THEIRS"})
    assert llm_spy["api_key"] == "sk-THEIRS"
    # the stored endpoint (spelled with a trailing slash) keeps the stored key
    client.post(path, json={**body, "endpoint": "https://api.real.example/v1/"})
    assert llm_spy["api_key"] == "sk-STORED-1234"


def test_prompt_enhance_foreign_endpoint(client, llm_spy):
    client.post("/api/prompt/enhance", json={
        "scene_description": "x", "mode": "turbo", "endpoint": "https://evil.example/v1"})
    assert llm_spy["api_key"] == ""


# ---------------------------------------------------------------------------
# 6. fonts
# ---------------------------------------------------------------------------

@pytest.fixture
def font_dir(tmp_path, monkeypatch):
    from backend.render import fonts
    real = Path(config.DATA_DIR) / "fonts"
    d = tmp_path / "fonts"
    d.mkdir()
    for name in ("default-letter-bold.ttf", "title-bebas.ttf", "sfx-baloo2.ttf"):
        if (real / name).exists():
            shutil.copy(real / name, d / name)
    if not (d / "title-bebas.ttf").exists():
        pytest.skip("bundled fonts not present")
    monkeypatch.setattr(fonts, "_USER_FONT_DIR", d)
    monkeypatch.setattr(fonts, "_find_cache", {})
    monkeypatch.setattr(fonts, "_cache", {})
    return d


def test_font_family_prefix_and_default_fallback(font_dir):
    from backend.render import fonts
    assert fonts._find_font("title") == str(font_dir / "title-bebas.ttf")
    # bold request still prefers the family's own file over "any bold font"
    assert fonts._find_font("title", bold=True) == str(font_dir / "title-bebas.ttf")
    # substring of a file name is not a family
    assert fonts._find_font("bebas") == str(font_dir / "default-letter-bold.ttf")
    # unknown family → the user's default font before system fonts
    assert fonts._find_font("Comic Sans") == str(font_dir / "default-letter-bold.ttf")
    assert fonts._find_font(None) == str(font_dir / "default-letter-bold.ttf")


def test_font_lookup_is_cached(font_dir, monkeypatch):
    from backend.render import fonts
    fonts._find_font("title")
    calls = []
    monkeypatch.setattr(fonts, "_match_user_font",
                        lambda *a: calls.append(a) or None)
    fonts._find_font("title")
    assert calls == []
    # a font added to the dir invalidates (dir mtime changes)
    (font_dir / "new-x.ttf").write_bytes((font_dir / "title-bebas.ttf").read_bytes())
    os.utime(font_dir, (time.time() + 5,) * 2)
    fonts._find_font("title")
    assert calls


def test_font_last_resort_is_sized(tmp_path, monkeypatch):
    from backend.render import fonts
    monkeypatch.setattr(fonts, "_USER_FONT_DIR", tmp_path / "none")
    monkeypatch.setattr(fonts, "_FALLBACKS", [])
    monkeypatch.setattr(fonts, "_BOLD_FALLBACKS", [])
    monkeypatch.setattr(fonts, "_find_cache", {})
    monkeypatch.setattr(fonts, "_cache", {})
    f = fonts.get_font(40)
    assert getattr(f, "size", None) == 40


def test_macos_fallback_paths_exist_when_listed():
    from backend.render import fonts
    if sys.platform != "darwin":
        pytest.skip("macOS only")
    mac = [p for p in fonts._FALLBACKS + fonts._BOLD_FALLBACKS
           if p.startswith("/System/")]
    assert any(os.path.exists(p) for p in mac)


# ---------------------------------------------------------------------------
# 8. renderer: local layers render the same as full-page layers
# ---------------------------------------------------------------------------

def _old_render(page, scale, resolve):
    """The previous algorithm: one page-sized RGBA layer per element,
    rotated as a whole. Used as the reference for pixel parity."""
    from backend.render import renderer as R
    W = max(1, int(round(page.get("width", 600) * scale)))
    H = max(1, int(round(page.get("height", 900) * scale)))
    canvas = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    els = sorted([e for e in page["elements"] if e.get("visible", True)],
                 key=lambda e: e.get("zIndex", 0))
    for el in els:
        X = el.get("x", 0) / 100 * W
        Y = el.get("y", 0) / 100 * H
        EW = el.get("width", 0) / 100 * W
        EH = el.get("height", 0) / 100 * H
        ew, eh = int(round(EW)), int(round(EH))
        t = el.get("type")
        if t in ("image", "page-image"):
            local, pad = R._draw_image(el, ew, eh, scale, resolve), 0
        elif t == "text":
            local, pad = R._draw_text(el, ew, eh, scale), 0
        else:
            local, pad = R.bubbles.draw_bubble(el, ew, eh, scale)
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        layer.paste(local, (int(round(X)) - pad, int(round(Y)) - pad))
        rot = el.get("rotation") or 0
        if rot:
            layer = layer.rotate(-float(rot), center=(X + EW / 2, Y + EH / 2),
                                 resample=Image.BICUBIC, expand=False)
        canvas = Image.alpha_composite(canvas, layer)
    return canvas.convert("RGB")


def test_rotated_render_matches_full_layer_reference():
    np = pytest.importorskip("numpy")
    from backend.render import render_page
    from backend.render.resolve import make_resolver
    from backend.tests._fixtures import transparent_circle_png
    page = {"width": 300, "height": 450, "elements": [
        {"id": "a", "type": "image", "src": solid_png((40, 90, 200), (60, 80)),
         "x": 5, "y": 5, "width": 40, "height": 30, "rotation": 12, "zIndex": 1},
        {"id": "b", "type": "page-image", "src": transparent_circle_png(),
         "x": 50, "y": 10, "width": 30, "height": 20, "rotation": -33, "zIndex": 2},
        {"id": "c", "type": "text", "content": "HELLO", "x": 10, "y": 50,
         "width": 40, "height": 15, "rotation": 20, "fontSize": 20,
         "strokeWidth": 2, "zIndex": 3},
        {"id": "d", "type": "bubble", "text": "hi there", "bubbleType": "speech",
         "x": 55, "y": 55, "width": 30, "height": 20, "rotation": -8, "zIndex": 4},
        {"id": "e", "type": "image", "src": solid_png((200, 30, 30), (40, 40)),
         "x": 33.3, "y": 70.7, "width": 21.1, "height": 13.3, "rotation": 45,
         "zIndex": 5},
        {"id": "f", "type": "text", "content": "edge", "x": 85, "y": 90,
         "width": 30, "height": 8, "rotation": 0, "zIndex": 6},
    ]}
    res = make_resolver(None)
    new = np.asarray(render_page(page, 2.0, res)).astype(int)
    old = np.asarray(_old_render(page, 2.0, res)).astype(int)
    assert np.abs(new - old).mean() < 0.05


def test_unknown_text_align_renders_left():
    from backend.render import render_page
    page = {"width": 200, "height": 100, "elements": [
        {"id": "t", "type": "text", "content": "x", "textAlign": "justify",
         "x": 0, "y": 0, "width": 100, "height": 100}]}
    render_page(page, 1.0, None)   # used to raise KeyError


# ---------------------------------------------------------------------------
# 7. export service: page-at-a-time, PNGs stored in the ZIP
# ---------------------------------------------------------------------------

def test_export_pages_zip_is_stored_from_written_pngs(tmp_path):
    from backend.render.export_service import export_pages, export_pages_to_bytes
    pages = [{"width": 60, "height": 90, "elements": []} for _ in range(3)]
    res = export_pages(pages, "both", 1.0, None, tmp_path, "m", page_numbers=True)
    with zipfile.ZipFile(res["zip"]["path"]) as zf:
        infos = zf.infolist()
        assert [i.filename for i in infos] == ["page_001.png", "page_002.png", "page_003.png"]
        assert all(i.compress_type == zipfile.ZIP_STORED for i in infos)
        assert zf.read("page_002.png") == (Path(res["pages_dir"]) / "page_002.png").read_bytes()
    assert Path(res["pdf"]["path"]).read_bytes().startswith(b"%PDF")
    out = export_pages_to_bytes(pages, "both", 1.0, None)
    assert out["pdf"].startswith(b"%PDF") and zipfile.is_zipfile(io.BytesIO(out["zip"]))


# ---------------------------------------------------------------------------
# 9. comics runs: detached, restart-proof
# ---------------------------------------------------------------------------

_FAKE_CONVERTER = r"""
const fs = require('fs');
const script = fs.readFileSync(process.argv[2], 'utf8');
fs.writeFileSync('node.pid', String(process.pid));
console.log('converting ' + process.argv.slice(3).join(' '));
console.log('x'.repeat(100 * 1024));            // > 64 KiB in one line
for (let i = 0; i < 5; i++) console.log('line ' + i);
if (script.includes('SLEEP')) { setInterval(() => {}, 1000); }
else if (script.includes('FAIL')) { process.exit(3); }
else { process.stdout.write('no newline at end'); }
"""


@pytest.fixture
def comics_env(tmp_path, monkeypatch):
    import backend.api.comics as cm
    node = shutil.which("node") or "/opt/homebrew/bin/node"
    if not os.path.exists(node):
        pytest.skip("node not installed")
    repo = tmp_path / "Comics"
    (repo / "scripts").mkdir(parents=True)
    (repo / "automanga.js").write_text(_FAKE_CONVERTER, encoding="utf-8")
    for name, body in (("ok", "title: OK\n"), ("bad", "FAIL\n"), ("slow", "SLEEP\n")):
        (repo / "scripts" / f"{name}.comic").write_text(body, encoding="utf-8")
    monkeypatch.setattr(cm, "COMICS_DIR", repo)
    monkeypatch.setattr(cm, "RUN_FILE", tmp_path / "comics_run.json")
    monkeypatch.setattr(cm, "_procs", {})
    monkeypatch.setattr(cm, "_line_index", {})
    monkeypatch.setattr(cm, "_verified", {})
    yield cm
    run = cm._load_run()
    if run:
        try:
            os.killpg(int(run["pid"]), 15)
        except (ProcessLookupError, PermissionError):
            pass


def _wait(client, pred, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        run = client.get("/api/comics/runs/current").json()["run"]
        if pred(run):
            return run
        time.sleep(0.05)
    raise AssertionError(f"timeout; last run: {run and run['status']}")


def test_comics_run_done_with_long_line(client, comics_env):
    r = client.post("/api/comics/runs", json={"script": "ok", "mode": "dry-run"})
    assert r.status_code == 200, r.text
    run = _wait(client, lambda r: r["status"] != "running")
    assert run["status"] == "done" and run["exit_code"] == 0 and run["ended"]
    assert run["lines"][0] == "$ node automanga.js scripts/ok.comic --dry-run"
    assert run["lines"][1] == "converting --dry-run"
    assert len(run["lines"][2]) == comics_env._LINE_LIMIT     # capped, not fatal
    assert run["lines"][-1] == "no newline at end"
    # incremental read: since=N returns only what follows
    tail = client.get(f"/api/comics/runs/current?since={run['next'] - 2}").json()["run"]
    assert tail["lines"] == ["line 4", "no newline at end"]
    assert set(run) == {"id", "script", "mode", "face", "status", "exit_code",
                        "started", "ended", "lines", "next", "project_id"}
    log = comics_env.COMICS_DIR / "out" / "ok" / "automanga.run.log"
    assert log.exists() and Path(str(log) + ".exit").read_text().strip() == "0"
    persisted = json.loads(comics_env.RUN_FILE.read_text())
    assert {"id", "script", "mode", "face", "pid", "log", "started"} <= set(persisted)


def test_comics_run_failure_exit_code(client, comics_env):
    client.post("/api/comics/runs", json={"script": "bad", "mode": "no-paint"})
    run = _wait(client, lambda r: r["status"] != "running")
    assert run["status"] == "failed" and run["exit_code"] == 3


def test_comics_run_survives_restart_and_stops_group(client, comics_env):
    r = client.post("/api/comics/runs", json={"script": "slow", "mode": "paint"})
    pid = r.json() and json.loads(comics_env.RUN_FILE.read_text())["pid"]
    _wait(client, lambda r: "line 4" in r["lines"])
    # one at a time, and the running script can't be saved
    assert client.post("/api/comics/runs", json={"script": "ok"}).status_code == 409
    assert client.put("/api/comics/scripts/slow", json={"text": "x"}).status_code == 409

    # "restart": drop all in-memory state; the run is picked up from disk
    comics_env._procs.clear()
    comics_env._line_index.clear()
    run = client.get("/api/comics/runs/current").json()["run"]
    assert run["status"] == "running" and "line 4" in run["lines"]

    r = client.post("/api/comics/runs/current/stop")
    assert r.status_code == 200 and r.json()["run"]["status"] == "stopped"
    # the grandchild (node, not the /bin/sh we spawned) must be gone too
    node_pid = int((comics_env.COMICS_DIR / "node.pid").read_text())
    assert node_pid != pid
    end = time.time() + 5
    while time.time() < end:
        try:
            os.kill(node_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("converter still alive after stop")
    run = client.get("/api/comics/runs/current").json()["run"]
    assert run["status"] == "stopped" and run["lines"][-1] == "stopped"
    assert client.post("/api/comics/runs/current/stop").status_code == 409


def test_comics_reused_pid_is_not_our_run(client, comics_env):
    # persisted run whose pid now belongs to an unrelated live process
    # (this test process): it must not count as running, nor be killable
    comics_env._save_run({"id": "old", "script": "ok", "mode": "paint",
                          "face": False, "pid": os.getpid(),
                          "log": str(comics_env.COMICS_DIR / "gone.log"),
                          "started": time.time() - 3600})
    run = client.get("/api/comics/runs/current").json()["run"]
    assert run["status"] == "failed" and run["exit_code"] is None
    assert client.post("/api/comics/runs/current/stop").status_code == 409


def test_comics_name_rejects_trailing_newline(client, comics_env):
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        comics_env._script_path("ok\n")


# ---------------------------------------------------------------------------
# 10. atomic JSON writes, resilient project listing
# ---------------------------------------------------------------------------

def test_atomic_write_json_keeps_old_file_on_failure(tmp_path):
    target = tmp_path / "x.json"
    config.atomic_write_json(target, {"a": 1})
    with pytest.raises(TypeError):
        config.atomic_write_json(target, {"a": object()})
    assert json.loads(target.read_text()) == {"a": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["x.json"]   # no temp left


def test_list_projects_skips_unreadable(client, tmp_path):
    client.post("/api/agent/projects", json={"name": "good"})
    bad = tmp_path / "projects" / "broken"
    bad.mkdir()
    (bad / "project.json").write_text("{not json", encoding="utf-8")
    r = client.get("/api/projects/")
    assert r.status_code == 200
    assert [p["name"] for p in r.json()["projects"]] == ["good"]


# ---------------------------------------------------------------------------
# 11. small fixes
# ---------------------------------------------------------------------------

def test_archive_folders_sort_by_created_mixed_formats(client, archive_tmp):
    for fid, created in (("a", "2026-11-02T10:00:00Z"), ("b", "1700000000.0"),
                         ("c", "2026-11-01T10:00:00.000Z")):
        assert client.post("/api/archive/folders", json={
            "id": fid, "name": fid, "created_at": created}).status_code == 200
    r = client.get("/api/archive/folders?sort_by=created")
    assert r.status_code == 200
    assert [f["id"] for f in r.json()] == ["b", "c", "a"]


def test_finished_jobs_are_pruned():
    from backend import jobs
    old = jobs.create_job([{"panel_id": "p"}])
    old.finished_at = time.time() - 2 * 3600
    running = jobs.create_job([{"panel_id": "q"}])
    recent = jobs.create_job([{"panel_id": "r"}])
    recent.finished_at = time.time() - 60
    jobs.create_job([])
    assert old.id not in jobs._jobs and old.id not in jobs._semaphores
    assert running.id in jobs._jobs and recent.id in jobs._jobs
