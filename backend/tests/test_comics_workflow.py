"""Comics tab workflow: run modes (repaint / variants), the panel and variant
file routes, and /plan (comic.js --plan, here a stub comic.js)."""
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT.parent))

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import backend.api.comics as cm  # noqa: E402
from backend.main import app  # noqa: E402

# a stand-in for comic.js --plan: reports what it was given; the script text decides the outcome
_FAKE_COMIC = r"""
const fs = require('fs');
const argv = process.argv.slice(2);
const text = argv.includes('--stdin') ? fs.readFileSync(0, 'utf8') : fs.readFileSync(argv[0], 'utf8');
if (text.includes('GARBAGE')) { console.log('not json'); process.exit(1); }
if (text.includes('BROKEN')) { console.log(JSON.stringify({ ok: false, error: 'x.comic:3: unknown character "zork"', line: 3 })); process.exit(1); }
console.log('some warning first');
console.log(JSON.stringify({ ok: true, argv, text, panels: [] }));
"""


@pytest.fixture
def client():
    # loopback peer, so these keep passing behind the login gate
    return TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))


@pytest.fixture
def repo(tmp_path, monkeypatch):
    node = shutil.which("node") or "/opt/homebrew/bin/node"
    if not os.path.exists(node):
        pytest.skip("node not installed")
    root = tmp_path / "Comics"
    (root / "scripts").mkdir(parents=True)
    (root / "comic.js").write_text(_FAKE_COMIC, encoding="utf-8")
    (root / "automanga.js").write_text("", encoding="utf-8")
    (root / "scripts" / "ok.comic").write_text("title: Saved\n", encoding="utf-8")
    monkeypatch.setattr(cm, "COMICS_DIR", root)
    monkeypatch.setattr(cm, "RUN_FILE", tmp_path / "comics_run.json")
    return root


# ---------------------------------------------------------------------------
# _mode_args
# ---------------------------------------------------------------------------

def _req(**kw):
    return cm.StartRunRequest(script="ok", **kw)


def test_mode_args_basic_modes():
    assert cm._mode_args(_req()) == []
    assert cm._mode_args(_req(mode="no-paint")) == ["--no-paint"]
    assert cm._mode_args(_req(mode="dry-run")) == ["--dry-run"]


def test_mode_args_repaint_and_variants():
    assert cm._mode_args(_req(mode="repaint", panels=["1.2", "3.1"])) == ["--panels", "1.2,3.1"]
    assert cm._mode_args(_req(mode="repaint", panels=["1.2"], force=True)) == ["--panels", "1.2", "--force"]
    assert cm._mode_args(_req(mode="variants", panels=["2.3"], variants=4)) == ["--panels", "2.3", "--variants", "4"]


@pytest.mark.parametrize("kw", [
    {"mode": "bogus"},
    {"mode": "repaint"},                      # no panels
    {"mode": "variants", "panels": ["1.1"]},  # no count
])
def test_mode_args_rejects(kw):
    with pytest.raises(HTTPException) as e:
        cm._mode_args(_req(**kw))
    assert e.value.status_code == 400


@pytest.mark.parametrize("kw", [
    {"panels": ["1.2; rm -rf /"]},
    {"panels": ["1"]},
    {"panels": ["--force"]},
    {"variants": 1},
    {"variants": 9},
])
def test_start_request_validation(kw):
    with pytest.raises(ValueError):
        _req(**kw)


def test_start_run_rejects_bad_mode_and_panels(client, repo):
    assert client.post("/api/comics/runs", json={"script": "ok", "mode": "repaint"}).status_code == 400
    assert client.post("/api/comics/runs", json={"script": "ok", "mode": "repaint", "panels": ["x"]}).status_code == 422
    assert client.post("/api/comics/runs", json={"script": "ok", "mode": "variants", "panels": ["1.1"],
                                                 "variants": 12}).status_code == 422


# ---------------------------------------------------------------------------
# panel / variant files
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pattern,good,bad", [
    (cm._PANEL_FILE_RE, ["p01-02.png", "p10-11.prev.png"],
     ["p1-2.png", "p01-02.png.json", "../p01-02.png", "p01-02.old.png", "page_01.png"]),
    (cm._VARIANT_FILE_RE, ["p01-02_seed4301.png"],
     ["p01-02_seed.png", "p01-02_seed12.png.json", "p01-02_seed-1.png", "p01-02.png"]),
])
def test_file_regexes(pattern, good, bad):
    assert all(pattern.fullmatch(f) for f in good)
    assert not any(pattern.fullmatch(f) for f in bad)


def test_panel_and_variant_routes(client, repo):
    out = repo / "out" / "ok"
    (out / "panels").mkdir(parents=True)
    (out / "variants").mkdir()
    (out / "panels" / "p01-02.png").write_bytes(b"panel")
    (out / "panels" / "p01-02.prev.png").write_bytes(b"prev")
    (out / "variants" / "p01-02_seed77.png").write_bytes(b"variant")
    assert client.get("/api/comics/scripts/ok/panel/p01-02.png").content == b"panel"
    assert client.get("/api/comics/scripts/ok/panel/p01-02.prev.png").content == b"prev"
    assert client.get("/api/comics/scripts/ok/variant/p01-02_seed77.png").content == b"variant"
    assert client.get("/api/comics/scripts/ok/panel/p01-03.png").status_code == 404
    assert client.get("/api/comics/scripts/ok/panel/p01-02.png.json").status_code == 400
    assert client.get("/api/comics/scripts/ok/variant/p01-02.png").status_code == 400
    assert client.get("/api/comics/scripts/-bad/panel/p01-02.png").status_code == 400


# ---------------------------------------------------------------------------
# /plan
# ---------------------------------------------------------------------------

def test_plan_saved_script(client, repo):
    r = client.post("/api/comics/scripts/ok/plan", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True and body["text"] == "title: Saved\n"
    assert body["argv"][1:] == ["--plan"] and body["argv"][0].endswith("scripts/ok.comic")


def test_plan_unsaved_text_via_stdin(client, repo):
    body = client.post("/api/comics/scripts/new-one/plan", json={"text": "title: Draft\n", "face": True}).json()
    assert body["ok"] is True and body["text"] == "title: Draft\n"
    assert body["argv"][1:] == ["--plan", "--stdin", "--face"]


def test_plan_script_error_passes_through(client, repo):
    r = client.post("/api/comics/scripts/ok/plan", json={"text": "BROKEN"})
    assert r.status_code == 200
    assert r.json() == {"ok": False, "error": 'x.comic:3: unknown character "zork"', "line": 3}


def test_plan_unparseable_output_is_500(client, repo):
    r = client.post("/api/comics/scripts/ok/plan", json={"text": "GARBAGE"})
    assert r.status_code == 500 and "not json" in r.json()["detail"]


def test_plan_missing_script_and_bad_name(client, repo):
    assert client.post("/api/comics/scripts/nope/plan", json={}).status_code == 404
    assert client.post("/api/comics/scripts/-bad/plan", json={"text": "x"}).status_code == 400


def test_plan_allowed_while_running(client, repo, monkeypatch):
    monkeypatch.setattr(cm, "_running_run", lambda: {"script": "ok", "pid": 1})
    assert client.post("/api/comics/scripts/ok/plan", json={}).json()["ok"] is True


def test_is_our_process_does_not_cache_a_failed_ps(monkeypatch):
    monkeypatch.setattr(cm, "_verified", {})
    run = {"pid": 999999, "id": "r1", "log": "/x/run.log"}

    def boom(*a, **kw):
        raise OSError("ps missing")
    monkeypatch.setattr(cm.subprocess, "run", boom)
    assert cm._is_our_process(run) is True
    assert cm._verified == {}
    monkeypatch.setattr(cm.subprocess, "run",
                        lambda *a, **kw: type("P", (), {"stdout": "/bin/sh other.log"})())
    assert cm._is_our_process(run) is False
    assert cm._verified == {(999999, "r1"): False}


def test_stop_run_survives_a_foreign_pid(client, tmp_path, monkeypatch):
    monkeypatch.setattr(cm, "RUN_FILE", tmp_path / "comics_run.json")
    run = {"id": "r1", "pid": 999999, "log": str(tmp_path / "run.log")}
    monkeypatch.setattr(cm, "_running_run", lambda: dict(run))
    monkeypatch.setattr(cm, "_snapshot", lambda r, since=0: {"id": r["id"], "stopped": r.get("stopped")})

    def denied(pid, sig):
        raise PermissionError(1, "Operation not permitted")
    monkeypatch.setattr(cm.os, "killpg", denied)
    r = client.post("/api/comics/runs/current/stop")
    assert r.status_code == 200 and r.json()["run"]["stopped"] is True


# ---------------------------------------------------------------------------
# uncut editions
# ---------------------------------------------------------------------------

def test_mode_args_uncut():
    assert cm._mode_args(_req(uncut=True)) == ["--uncut"]
    assert cm._mode_args(_req(mode="no-paint", uncut=True)) == ["--no-paint", "--uncut"]
    assert cm._mode_args(_req(mode="dry-run", uncut=True)) == ["--dry-run", "--uncut"]
    assert cm._mode_args(_req(mode="repaint", panels=["1.u1", "u2.3", "4.1"], force=True, uncut=True)) == \
        ["--panels", "1.u1,u2.3,4.1", "--force", "--uncut"]
    assert cm._mode_args(_req(mode="variants", panels=["u1.1"], variants=2, uncut=True)) == \
        ["--panels", "u1.1", "--variants", "2", "--uncut"]
    # regular runs are as before; uncut ids need the uncut edition
    assert cm._mode_args(_req(mode="repaint", panels=["1.2"])) == ["--panels", "1.2"]
    with pytest.raises(HTTPException):
        cm._mode_args(_req(mode="repaint", panels=["1.u1"]))
    for bad in ["u1", "1.u", "uu1.2", "1.2u"]:
        with pytest.raises(ValueError):
            _req(mode="repaint", panels=[bad])


def test_plan_uncut_flag(client, repo):
    r = client.post("/api/comics/scripts/ok/plan", json={"uncut": True})
    assert r.status_code == 200 and r.json()["argv"][-1] == "--uncut"
    r = client.post("/api/comics/scripts/ok/plan", json={})
    assert "--uncut" not in r.json()["argv"]


def test_summary_counts_uncut_slots_and_serves_uncut_files(client, repo):
    (repo / "scripts" / "u.comic").write_text(
        "title: U\nPAGE 1\nPANEL\nPANEL uncut\nPANEL uncut todo\nPAGE uncut\nPANEL\nPANEL\n"
        "PAGE uncut todo\nPANEL\nPAGE 2 — uncut words in a title\nPANEL\n", encoding="utf-8")
    s = client.get("/api/comics/scripts/u").json()
    assert (s["pages"], s["panels"], s["uncut"], s["uncut_slots"]) == (2, 2, 4, 2)
    assert client.get("/api/comics/scripts/ok").json()["uncut_slots"] == 0
    panels = repo / "out" / "u-uncut" / "panels"
    panels.mkdir(parents=True)
    (panels / "u01-02.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    assert client.get("/api/comics/scripts/u/panel/u01-02.png?uncut=1").status_code == 200
    assert client.get("/api/comics/scripts/u/panel/u01-02.png").status_code == 404
    assert client.get("/api/comics/scripts/u/panel/p01-u01.png?uncut=1").status_code == 404
    assert client.get("/api/comics/scripts/u/panel/x01-02.png?uncut=1").status_code == 400
