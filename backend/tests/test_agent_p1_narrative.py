"""P1 narrative & publishing features (deep-analysis G-7/8/9/10/11/20):
page planning, shot field, speaker-aware bubbles, SFX stroke, cover page,
export page numbers."""
import io
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT.parent))

from backend.tests.test_e2e_agent import client  # noqa: E402,F401


@pytest.fixture()
def pid(client):
    r = client.post("/api/agent/projects", json={"name": "p1"})
    assert r.status_code == 200
    return r.json()["project"]["id"]


def _gen_panel_images(client, pid, n):
    for i in range(1, n + 1):
        r = client.post("/api/agent/generate", json={
            "project_id": pid, "panel_id": f"panel_{i}",
            "prompt": f"art {i}", "apply_to_panel": True})
        assert r.status_code == 200, r.text


# ------------------------------------------------------------------ G-8 shot

def test_shot_field_validated_and_injected(client, pid, monkeypatch):
    panels = [
        {"scene": "rooftop panorama", "dialogue": "", "shot": "wide"},
        {"scene": "her trembling hand", "dialogue": "", "shot": "macro"},
    ]
    r = client.put(f"/api/agent/projects/{pid}/panels", json={"panels": panels})
    assert r.status_code == 400
    assert "shot must be one of" in r.json()["detail"]

    panels[1]["shot"] = "close-up"
    r = client.put(f"/api/agent/projects/{pid}/panels", json={"panels": panels})
    assert r.status_code == 200

    captured = {}

    async def fake_generate(**kwargs):
        captured.update(kwargs)
        from backend.tests._fixtures import solid_png
        return {"success": True, "image": solid_png((10, 20, 30)), "path": "m"}

    import backend.api.agent as agent_mod
    monkeypatch.setattr(agent_mod.swarm_client, "generate_image",
                        AsyncMock(side_effect=fake_generate))

    r = client.post("/api/agent/generate", json={
        "project_id": pid, "panel_id": "panel_1", "prompt": "rooftop"})
    assert r.status_code == 200
    assert "wide shot" in captured["prompt"]           # tags format (default)

    r = client.post("/api/agent/generate", json={
        "project_id": pid, "panel_id": "panel_1", "prompt": "rooftop",
        "prompt_format": "prose"})
    assert r.status_code == 200
    assert "全景远景" in captured["prompt"]               # prose format


# ------------------------------------------------------------------ G-11 speaker

def test_speaker_bubbles_and_tails(client, pid):
    r = client.put(f"/api/agent/projects/{pid}/panels", json={"panels": [
        {"scene": "two kids arguing on the bridge",
         "characters": ["Yuki", "阿明"],
         "dialogue": "Yuki：走开！\n阿明：这是我的位置！\n时间：黄昏（旁白）"}]})
    assert r.status_code == 200
    _gen_panel_images(client, pid, 1)

    r = client.post(f"/api/agent/projects/{pid}/pages", json={
        "template": {"kind": "builtin", "id": "hero-splash"},
        "panel_ids": ["panel_1"]})
    assert r.status_code == 200
    bubbles = [e for e in r.json()["page"]["elements"]
               if e["type"] == "bubble"]
    assert len(bubbles) == 3
    by_text = {b["text"]: b for b in bubbles}
    # "时间：黄昏（旁白）" is narration, not a speaker line — no prefix strip
    assert by_text["走开！"]["speaker"] == "Yuki"
    assert by_text["这是我的位置！"]["speaker"] == "阿明"
    assert "speaker" not in by_text["时间：黄昏（旁白）"]
    # two speakers in one panel → opposite tails so the reader can tell apart
    assert by_text["走开！"]["tailPosition"] != by_text["这是我的位置！"]["tailPosition"]


def test_closeup_shot_shrinks_bubbles(client, pid):
    r = client.put(f"/api/agent/projects/{pid}/panels", json={
        "panels": [{"scene": "face", "dialogue": "一"*20}]})
    assert r.status_code == 200
    _gen_panel_images(client, pid, 1)

    def build():
        rr = client.post(f"/api/agent/projects/{pid}/pages", json={
            "template": {"kind": "rows", "rows": [1]},
            "panel_ids": ["panel_1"]})
        b = [e for e in rr.json()["page"]["elements"] if e["type"] == "bubble"][0]
        return b["width"]

    w_plain = build()
    r = client.patch(f"/api/agent/projects/{pid}/panels/panel_1",
                     json={"shot": "close-up"})
    assert r.status_code == 200
    w_close = build()
    assert w_close < w_plain


# ------------------------------------------------------------------ G-7 planner

def test_plan_pages_chunks_and_splash(client, pid):
    r = client.put(f"/api/agent/projects/{pid}/panels", json={
        "panels": [{"scene": f"scene {i}", "dialogue": ""} for i in range(1, 10)]})
    assert r.status_code == 200
    _gen_panel_images(client, pid, 9)
    # panel_3 becomes a splash
    r = client.patch(f"/api/agent/projects/{pid}/panels/panel_3",
                     json={"shot": "splash"})
    assert r.status_code == 200

    r = client.post(f"/api/agent/projects/{pid}/plan-pages",
                    json={"panels_per_page": 4})
    assert r.status_code == 200
    body = r.json()
    assert body["applied"] is False and body["pages_added"] == 0
    plan = body["plan"]
    # 1 | 2 | splash(3) | 4 5 6 7 | 8 9
    assert [p["panel_ids"] for p in plan] == [
        ["panel_1", "panel_2"], ["panel_3"],
        ["panel_4", "panel_5", "panel_6", "panel_7"], ["panel_8", "panel_9"]]
    assert plan[1]["template"]["id"] == "hero-splash"
    assert plan[2]["template"]["id"] == "manga-4"

    # 5-panel group maps onto the dynamic 5-slot template; apply persists
    # panel_3 keeps its splash shot: [1*] [2] [3*] [4-8] [9] -> 5 pages,
    # with the 5-slot group mapping onto the dynamic template
    r = client.post(f"/api/agent/projects/{pid}/plan-pages",
                    json={"panels_per_page": 5, "apply": True,
                          "splash_panel_ids": ["panel_1"]})
    assert r.status_code == 200
    body = r.json()
    assert body["pages_added"] == len(body["plan"]) == 5
    assert body["plan"][3]["template"]["id"] == "dyn-5-mix"
    r = client.get(f"/api/agent/projects/{pid}")
    assert r.json()["stats"]["pages"] == 5


def test_plan_pages_skips_imageless_panels_by_default(client, pid):
    r = client.put(f"/api/agent/projects/{pid}/panels", json={
        "panels": [{"scene": "a"}, {"scene": "b"}]})
    assert r.status_code == 200
    r = client.post(f"/api/agent/projects/{pid}/plan-pages", json={})
    assert r.json()["plan"] == []          # nothing generated yet
    r = client.post(f"/api/agent/projects/{pid}/plan-pages",
                    json={"only_with_image": False})
    assert len(r.json()["plan"]) == 1


# ------------------------------------------------------------------ G-10 cover

def test_cover_page(client, pid):
    r = client.put(f"/api/agent/projects/{pid}/panels", json={
        "panels": [{"scene": "hero shot", "dialogue": ""}]})
    assert r.status_code == 200
    _gen_panel_images(client, pid, 1)
    r = client.post(f"/api/agent/projects/{pid}/pages", json={
        "template": {"kind": "builtin", "id": "manga-2v"},
        "panel_ids": []})
    assert r.status_code == 200

    r = client.post(f"/api/agent/projects/{pid}/cover", json={
        "title": "雨桥物语", "subtitle": "第一卷", "panel_id": "panel_1"})
    assert r.status_code == 200
    cover = r.json()["page"]
    assert cover["order"] == 0 and cover["name"] == "cover"
    title = next(e for e in cover["elements"]
                 if e.get("type") == "text" and e.get("strokeWidth") == 6)
    assert title["content"] == "雨桥物语" and title["fontWeight"] == "bold"

    r = client.get(f"/api/agent/projects/{pid}")
    pages = r.json()["project"]["composerPages"]
    assert pages[0]["name"] == "cover" and len(pages) == 2
    assert [p["order"] for p in pages] == [0, 1]

    # cover needs a source; arbitrary paths are rejected
    r = client.post(f"/api/agent/projects/{pid}/cover",
                    json={"title": "x", "panel_id": "no_such_panel"})
    assert r.status_code == 404
    r = client.post(f"/api/agent/projects/{pid}/cover",
                    json={"title": "x", "asset_url": "D:/Windows/win.ini"})
    assert r.status_code == 400
    r = client.post(f"/api/agent/projects/{pid}/cover", json={"title": "x"})
    assert r.status_code == 400


def test_patch_shot_and_scene_validation(client, pid):
    r = client.put(f"/api/agent/projects/{pid}/panels",
                   json={"panels": [{"scene": "x"}]})
    assert r.status_code == 200
    r = client.patch(f"/api/agent/projects/{pid}/panels/panel_1",
                     json={"shot": "macro"})
    assert r.status_code == 400 and "shot must be one of" in r.json()["detail"]
    r = client.patch(f"/api/agent/projects/{pid}/panels/panel_1",
                     json={"scene": "   "})
    assert r.status_code == 400 and "scene" in r.json()["detail"]
    r = client.patch(f"/api/agent/projects/{pid}/panels/panel_1",
                     json={"shot": "wide"})
    assert r.status_code == 200 and r.json()["panel"]["shot"] == "wide"


# ------------------------------------------------------------------ G-9 SFX

def test_sfx_presets_endpoint(client):
    r = client.get("/api/agent/sfx-presets")
    assert r.status_code == 200
    body = r.json()
    words = {p["word"] for p in body["presets"]}
    assert {"轰", "BOOM", "ざっ"} <= words
    assert body["default_style"]["strokeWidth"] == 4


def test_stroke_validation_and_render(client, pid):
    r = client.post(f"/api/agent/projects/{pid}/pages", json={
        "template": {"kind": "builtin", "id": "blank"}, "panel_ids": []})
    page_id = r.json()["page"]["id"]
    r = client.post(f"/api/agent/projects/{pid}/pages/{page_id}/elements", json={
        "type": "text", "content": "轰！", "x": 20, "y": 30,
        "width": 50, "height": 12, "strokeWidth": 25})
    assert r.status_code == 400
    r = client.post(f"/api/agent/projects/{pid}/pages/{page_id}/elements", json={
        "type": "text", "content": "轰！", "x": 20, "y": 30, "width": 50,
        "height": 12, "strokeWidth": 4, "strokeColor": "#000000"})
    assert r.status_code == 200

    # the stroke must actually change rendered pixels
    el_id = r.json()["element"]["id"]
    def preview():
        rr = client.get(
            f"/api/agent/projects/{pid}/pages/{page_id}/preview.png?scale=1")
        return rr.content
    with_stroke = preview()
    r = client.patch(
        f"/api/agent/projects/{pid}/pages/{page_id}/elements/{el_id}",
        json={"strokeWidth": 0})
    assert r.status_code == 200
    without_stroke = preview()
    assert with_stroke != without_stroke and len(with_stroke) > 4


# ------------------------------------------------------------------ G-20 page numbers

def test_page_number_stamp(client, pid):
    from PIL import Image
    from backend.render.export_service import _stamp_page_numbers
    img1 = Image.new("RGB", (60, 90), (255, 255, 255))
    img2 = Image.new("RGB", (60, 90), (255, 255, 255))
    _stamp_page_numbers([img1, img2], scale=1)
    def darkest(img):
        return img.convert("L").crop((20, 60, 40, 90)).getextrema()[0]
    assert darkest(img1) == 255  # cover stays clean
    assert darkest(img2) < 255   # page 2 carries the number "2"


def test_export_with_page_numbers(client, pid):
    r = client.put(f"/api/agent/projects/{pid}/panels", json={
        "panels": [{"scene": "x", "dialogue": ""}]})
    _gen_panel_images(client, pid, 1)
    for _ in range(2):
        r = client.post(f"/api/agent/projects/{pid}/pages", json={
            "template": {"kind": "rows", "rows": [1]},
            "panel_ids": ["panel_1"]})
        assert r.status_code == 200
    r = client.post("/api/agent/export", json={
        "project_id": pid, "format": "pdf", "scale": 1,
        "page_numbers": True})
    assert r.status_code == 200
    assert Path(r.json()["pdf"]["path"]).read_bytes()[:4] == b"%PDF"
