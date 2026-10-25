"""Data-loss guard for the UI save endpoint.

The composer autosave historically posted panels: [] and a bare
settings dict for projects whose storyboard/settings were written by the
agent API — wiping them on disk (real incident, 2026-10-25). The save
endpoint now preserves stored panels when the payload carries none, and
merges settings keys instead of replacing them.
"""
import uuid

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from backend.storage import manager as mgr

    (tmp_path / "projects").mkdir()
    monkeypatch.setattr(mgr, "PROJECTS_DIR", tmp_path / "projects")

    from backend.main import app
    return TestClient(app)


def _make_project(client) -> str:
    pid = "t" + uuid.uuid4().hex[:12]
    r = client.post("/api/agent/projects", json={"name": "guard"})
    assert r.status_code == 200
    pid = r.json()["project"]["id"]
    r = client.put(f"/api/agent/projects/{pid}/panels", json={"panels": [
        {"scene": "s1", "dialogue": "A：hi"},
        {"scene": "s2"},
    ]})
    assert r.status_code == 200
    client.put(f"/api/agent/projects/{pid}/settings", json={
        "style": "ink", "characters": [{"name": "A", "prompt_block": "1boy"}]})
    return pid


def test_save_without_panels_keeps_storyboard(client):
    pid = _make_project(client)
    # composer autosave payload: no panels key at all
    r = client.post("/api/projects/save", json={
        "id": pid, "name": "guard", "settings": {"detailLevel": 3},
        "composerPages": []})
    assert r.status_code == 200
    panels = client.get(f"/api/agent/projects/{pid}").json()["project"]["panels"]
    assert len(panels) == 2


def test_save_empty_panels_keeps_storyboard(client):
    pid = _make_project(client)
    # legacy client explicitly sending an empty list
    r = client.post("/api/projects/save", json={
        "id": pid, "name": "guard", "panels": [], "settings": {},
        "composerPages": []})
    assert r.status_code == 200
    panels = client.get(f"/api/agent/projects/{pid}").json()["project"]["panels"]
    assert len(panels) == 2


def test_save_with_real_panels_replaces(client):
    pid = _make_project(client)
    r = client.post("/api/projects/save", json={
        "id": pid, "name": "guard",
        "panels": [{"id": "p1", "scene": "only one"}],
        "settings": {}, "composerPages": []})
    assert r.status_code == 200
    panels = client.get(f"/api/agent/projects/{pid}").json()["project"]["panels"]
    assert len(panels) == 1 and panels[0]["scene"] == "only one"


def test_save_merges_settings_keys(client):
    pid = _make_project(client)
    r = client.post("/api/projects/save", json={
        "id": pid, "name": "guard", "panels": [],
        "settings": {"detailLevel": 4}, "composerPages": []})
    assert r.status_code == 200
    settings = client.get(f"/api/agent/projects/{pid}").json()["project"]["settings"]
    assert settings.get("style") == "ink"                    # agent key survives
    assert settings.get("characters")[0]["name"] == "A"
    assert settings.get("detailLevel") == 4                 # UI key updated
