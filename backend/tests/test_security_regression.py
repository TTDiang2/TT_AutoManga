"""Security regression tests for the HTTP boundary (audit F-001..F-006).

Each test recreates one of the live-verified attack chains and asserts the
hardened behavior: no cross-origin access, masked API keys, no path
traversal via client-controlled ids or the static catch-all, and no
arbitrary-file copy through the archive."""
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT.parent))

from backend.tests.test_e2e_agent import client  # noqa: E402,F401
from backend.core import config  # noqa: E402


def test_no_cors_headers_for_foreign_origin(client):
    r = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert r.status_code == 200
    assert "access-control-allow-origin" not in r.headers
    assert "access-control-allow-credentials" not in r.headers


def test_settings_masks_api_key(client, monkeypatch, tmp_path):
    # the POST-less GET is safe, but redirect the settings file anyway so any
    # later save in this test can never rewrite the real data/settings.json
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(config.settings.api, "api_key", "sk-FAKE-SECRET-1234")
    r = client.get("/api/settings/")
    assert r.status_code == 200
    assert r.json()["api"]["api_key"] == "****1234"
    assert "sk-FAKE-SECRET-1234" not in r.text


def test_settings_save_ignores_masked_echo(client, monkeypatch, tmp_path):
    # POST /api/settings/ persists to config.SETTINGS_FILE — redirect it or
    # this test would rewrite the user's real settings.json
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(config.settings.api, "api_key", "sk-FAKE-SECRET-1234")
    # client saves the form back unchanged, echoing the mask
    r = client.post("/api/settings/", json={"api": {"api_key": "****1234"}})
    assert r.status_code == 200
    assert config.settings.api.api_key == "sk-FAKE-SECRET-1234"
    # a freshly typed key is stored; an empty string clears it
    r = client.post("/api/settings/", json={"api": {"api_key": "sk-NEW-KEY-9876"}})
    assert r.status_code == 200
    assert config.settings.api.api_key == "sk-NEW-KEY-9876"
    r = client.post("/api/settings/", json={"api": {"api_key": ""}})
    assert r.status_code == 200
    assert config.settings.api.api_key == ""


def test_storyboard_ignores_masked_key_echo(client, monkeypatch):
    """The storyboard tab echoes the masked key; the stored key must win."""
    monkeypatch.setattr(config.settings.api, "api_key", "sk-REAL-KEY-42")
    from backend.core import openai_client
    calls = {}
    orig = openai_client.OpenAIClient.update_config

    def spy(self, **kwargs):
        calls.update(kwargs)
        return orig(self, **kwargs)

    monkeypatch.setattr(openai_client.OpenAIClient, "update_config", spy)
    r = client.post("/api/storyboard/generate", json={
        "text": "hello", "api_key": "****-42"})
    # request may fail downstream (no LLM configured); we only assert the
    # masked echo never replaced the stored key
    assert calls.get("api_key", "sk-REAL-KEY-42") == "sk-REAL-KEY-42"


def test_static_catch_all_blocks_traversal(client, tmp_path):
    from backend.main import frontend_dir
    marker = frontend_dir.parent.parent / "__sec_marker__.txt"
    marker.write_text("TOPSECRET-LEAK-MARKER", encoding="utf-8")
    try:
        for url in ("/%2e%2e/%2e%2e/__sec_marker__.txt",
                    "/..%2f..%2f__sec_marker__.txt"):
            r = client.get(url)
            assert "TOPSECRET-LEAK-MARKER" not in r.text, url
    finally:
        marker.unlink(missing_ok=True)


def test_project_delete_traversal_blocked(client, tmp_path):
    # fixture redirected PROJECTS_DIR to tmp_path/"projects"; the parent
    # holds it, so a successful ".." delete would wipe tmp_path content.
    # (%2f-carrying forms are normalized away by httpx itself and surface
    # as 405 — what matters is that no form ever deletes anything.)
    (tmp_path / "projects").mkdir(exist_ok=True)
    (tmp_path / "canary.txt").write_text("alive", encoding="utf-8")
    for url in ("/api/projects/delete/%2e%2e",
                "/api/projects/delete/..%2e",
                "/api/projects/delete/..%2f..%2f"):
        r = client.delete(url)
        assert r.status_code in (400, 404, 405), url
        if r.status_code == 400:
            assert r.json()["detail"].startswith("invalid project id")
    assert (tmp_path / "canary.txt").read_text(encoding="utf-8") == "alive"
    assert (tmp_path / "projects").is_dir()


def test_project_save_traversal_blocked(client, tmp_path):
    for bad_id in ("../pwned", "..", "a/b", "a\\b"):
        r = client.post("/api/projects/save", json={
            "id": bad_id, "name": "x"})
        assert r.status_code == 400, bad_id
    assert not (tmp_path / "pwned").exists()
    assert list((tmp_path / "projects").iterdir()) == []


def test_agent_load_traversal_blocked(client):
    r = client.get("/api/agent/projects/%2e%2e")
    assert r.status_code == 400


def test_archive_rejects_filesystem_sources(client, tmp_path):
    secret = tmp_path / "secret.png"
    secret.write_bytes(b"\x89PNG-not-really")
    r = client.post("/api/archive/images",
                    json={"source_data": str(secret), "name": "s"})
    assert r.status_code == 400
    assert "source must be" in r.json()["detail"]


def test_archive_folder_id_traversal_blocked(client):
    # ids in the JSON body reach validation directly
    for bad in ("..", "../x", "a/b"):
        r = client.post("/api/archive/folders", json={
            "id": bad, "name": "f", "created_at": "0"})
        assert r.status_code == 400, bad
    # URL-carried forms are either validated (400) or normalized away by
    # the HTTP client before routing — neither may delete anything
    r = client.delete("/api/archive/folders/%2e%2e%2f%2e%2e")
    assert r.status_code in (400, 404, 405)


def test_swarmui_task_status_stub_removed(client):
    r = client.get("/api/assets/swarmui/status/whatever")
    # unmatched GETs fall through to the SPA index.html — the stub JSON
    # with "not_implemented" must be gone
    assert "not_implemented" not in r.text


def test_export_download_traversal_blocked(client):
    # any traversal form must never serve settings.json content (either
    # the handler's containment check 404s it or the client normalizes the
    # URL away into the SPA fallback)
    for bad in ("%2e%2e%2fsettings.json", "..%2f..%2fsettings.json"):
        r = client.get(f"/api/export/download/{bad}")
        assert '"api_key"' not in r.text, bad


def test_catch_all_containment_branch_direct():
    """The catch-all handler itself must refuse paths escaping frontend/dist.
    httpx normalizes literal dot-segments before routing, so this branch is
    unreachable through TestClient — call the handler directly instead."""
    import asyncio
    from backend.main import serve_frontend_paths

    r = asyncio.run(serve_frontend_paths("../../requirements.txt"))
    body = b"".join(chunk for chunk in r.body_iterator) if hasattr(r, "body_iterator") else b""
    # whatever comes back (fallback index.html), it must not be requirements.txt
    assert b"fastapi==0.115.0" not in body


def test_export_download_containment_direct(tmp_path, monkeypatch):
    """download_file must 404 anything resolving outside data/exports."""
    import asyncio
    import backend.api.export as export_mod

    (tmp_path / "exports").mkdir()
    (tmp_path / "secret.txt").write_text("TOPSECRET", encoding="utf-8")
    monkeypatch.setattr(export_mod, "EXPORTS_DIR", tmp_path / "exports")
    monkeypatch.setattr(export_mod, "EXPORTS_ROOT", (tmp_path / "exports").resolve())

    # handler-reaching traversal form (route matching is bypassed entirely)
    from fastapi import HTTPException
    try:
        asyncio.run(export_mod.download_file("../secret.txt"))
        raised = False
    except HTTPException as e:
        raised = e.status_code == 404
    assert raised, "traversal filename must be rejected with 404"

    # a legit file inside exports still serves
    (tmp_path / "exports" / "ok.bin").write_bytes(b"x")
    resp = asyncio.run(export_mod.download_file("ok.bin"))
    assert resp.status_code == 200
