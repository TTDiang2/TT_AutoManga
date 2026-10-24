"""Contract tests for the agent element CRUD validation branches
(AGENTS.md §7: 400 on coordinates outside 0-100, illegal types, immutable
id/type). These branches had zero coverage in the audit's mutation test."""
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT.parent))

# reuse the e2e fixture (storage redirected to tmp, SwarmUI mocked)
from backend.tests.test_e2e_agent import client  # noqa: E402,F401


@pytest.fixture()
def page_id(client):
    r = client.post("/api/agent/projects", json={"name": "validation"})
    assert r.status_code == 200
    pid = r.json()["project"]["id"]
    r = client.post(f"/api/agent/projects/{pid}/pages", json={
        "template": {"kind": "custom", "elements": [
            {"type": "image-slot", "x": 5, "y": 5, "width": 40, "height": 40}]},
        "panel_ids": []})
    assert r.status_code == 200
    return pid, r.json()["page"]["id"]


def _post_el(client, pid, pgid, el):
    return client.post(f"/api/agent/projects/{pid}/pages/{pgid}/elements", json=el)


def test_reject_unknown_type(page_id, client):
    pid, pgid = page_id
    r = _post_el(client, pid, pgid, {"type": "bogus", "x": 1, "y": 1,
                                     "width": 10, "height": 10})
    assert r.status_code == 400
    assert "type" in r.json()["detail"]


def test_reject_missing_type(page_id, client):
    pid, pgid = page_id
    r = _post_el(client, pid, pgid, {"x": 1, "y": 1, "width": 10, "height": 10})
    assert r.status_code == 400


def test_reject_coordinate_out_of_range(page_id, client):
    pid, pgid = page_id
    r = _post_el(client, pid, pgid, {"type": "text", "x": 150, "y": 1,
                                     "width": 10, "height": 10})
    assert r.status_code == 400
    r = _post_el(client, pid, pgid, {"type": "text", "x": -1, "y": 1,
                                     "width": 10, "height": 10})
    assert r.status_code == 400


def test_reject_nonpositive_size(page_id, client):
    pid, pgid = page_id
    r = _post_el(client, pid, pgid, {"type": "text", "x": 1, "y": 1,
                                     "width": 0, "height": 10})
    assert r.status_code == 400
    r = _post_el(client, pid, pgid, {"type": "text", "x": 1, "y": 1,
                                     "width": 10, "height": -5})
    assert r.status_code == 400


def test_reject_malformed_corners(page_id, client):
    pid, pgid = page_id
    r = _post_el(client, pid, pgid, {
        "type": "image-slot", "x": 1, "y": 1, "width": 10, "height": 10,
        "corners": {"tl": {"x": 0, "y": 0}}})
    assert r.status_code == 400
    r = _post_el(client, pid, pgid, {
        "type": "image-slot", "x": 1, "y": 1, "width": 10, "height": 10,
        "corners": {"tl": {"x": "a", "y": 0}, "tr": {"x": 1, "y": 0},
                    "br": {"x": 1, "y": 1}, "bl": {"x": 0, "y": 1}}})
    assert r.status_code == 400


def test_valid_element_accepted(page_id, client):
    pid, pgid = page_id
    r = _post_el(client, pid, pgid, {
        "type": "bubble", "bubbleType": "speech", "text": "hello",
        "x": 10, "y": 10, "width": 20, "height": 10})
    assert r.status_code == 200
    el = r.json()["element"]
    r = client.patch(
        f"/api/agent/projects/{pid}/pages/{pgid}/elements/{el['id']}",
        json={"x": 35, "rotation": 5})
    assert r.status_code == 200
    assert r.json()["element"]["x"] == 35


def test_patch_rejects_immutable_fields(page_id, client):
    pid, pgid = page_id
    r = _post_el(client, pid, pgid, {
        "type": "text", "content": "hi", "x": 10, "y": 10,
        "width": 20, "height": 10})
    assert r.status_code == 200
    el_id = r.json()["element"]["id"]
    r = client.patch(
        f"/api/agent/projects/{pid}/pages/{pgid}/elements/{el_id}",
        json={"type": "bubble"})
    assert r.status_code == 400
    r = client.patch(
        f"/api/agent/projects/{pid}/pages/{pgid}/elements/{el_id}",
        json={"id": "other"})
    assert r.status_code == 400
    # out-of-range coordinate via PATCH must 400 too
    r = client.patch(
        f"/api/agent/projects/{pid}/pages/{pgid}/elements/{el_id}",
        json={"y": 200})
    assert r.status_code == 400
