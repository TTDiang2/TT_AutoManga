"""Project collections (episodes of a series): CRUD + validation, project
delete cleanup, auto-grouping by title, and the background collection export
(cover + episode title pages + continuous page numbers, one page at a time).

Run: python -m pytest backend/tests/test_collections.py -q
"""
import io
import re
import sys
import threading
import time
import weakref
import zipfile
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT.parent))

from backend.storage.collections import (  # noqa: E402
    auto_groups, episode_number, split_title)
from backend.tests._fixtures import solid_png  # noqa: E402

JADE = [f"Jade & Haile — Episode {n} — {t}" for n, t in [
    (3, "Wet Sneakers"), (1, "The Rainy Gym"), (7, "Finals"), (2, "Locker Room"),
    (5, "Away Game"), (4, "Bench"), (6, "Overtime")]]
SPACE = ["The Space Between Us — Part Two — Making Room",
         "The Space Between Us — Part One",
         "The Space Between Us — Part Three — A Place to Begin"]
SINGLES = ["Rooftop Chase", "Mara — Origins", "Spider-Gwen - The Fall"]


@pytest.fixture
def env(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from backend.storage import asset_store as astore_mod
    from backend.storage import collections as col_store
    from backend.storage import manager as mgr
    import backend.api.collections as col_api
    import backend.api.export as export_mod
    from backend.render.resolve import make_resolver

    (tmp_path / "projects").mkdir()
    monkeypatch.setattr(mgr, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(col_store, "COLLECTIONS_FILE", tmp_path / "collections.json")
    store = astore_mod.AssetStore(tmp_path / "assets", tmp_path / "assets" / "index.json")
    monkeypatch.setattr(astore_mod, "asset_store", store)
    monkeypatch.setattr(col_api, "_resolver", make_resolver(store))
    exports = tmp_path / "exports"
    exports.mkdir()
    monkeypatch.setattr(export_mod, "EXPORTS_DIR", exports)
    monkeypatch.setattr(export_mod, "EXPORTS_ROOT", exports.resolve())
    monkeypatch.setattr(col_api, "_jobs", {})

    from backend.main import app
    client = TestClient(app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1")
    return client, mgr.storage, exports


def _page(n: int, color=(200, 60, 60)) -> dict:
    return {"id": f"pg{n}", "name": f"page {n}", "width": 60, "height": 90,
            "elements": [{"id": f"im{n}", "type": "image", "src": solid_png(color, (60, 90)),
                          "x": 0, "y": 0, "width": 100, "height": 100}]}


def _project(storage, name: str, pages: int = 1) -> str:
    saved = storage.save_project({"name": name, "panels": [], "settings": {},
                                  "composerPages": [_page(i) for i in range(pages)]})
    return saved["id"]


# ---------------------------------------------------------------- parsing

def test_split_title_and_episode_numbers():
    assert split_title(JADE[1]) == ("Jade & Haile", "Episode 1 — The Rainy Gym")
    assert split_title(SPACE[1]) == ("The Space Between Us", "Part One")
    assert split_title("Spider-Gwen - The Fall") == ("Spider-Gwen", "The Fall")
    assert split_title("Rooftop Chase") == ("Rooftop Chase", "")
    cases = {"Episode 3 — x": 3, "Ep. 3": 3, "ep 12": 12, "Part Two — Making Room": 2,
             "Part 2": 2, "Part III": 3, "Chapter 4": 4, "#5": 5, "Part Twelve": 12,
             "The Chase": None, "Chill Night": None, "": None}
    for sub, n in cases.items():
        assert episode_number(sub) == n, sub


def test_auto_groups_order_and_singles():
    projects = [{"id": f"p{i}", "name": n} for i, n in enumerate(JADE + SPACE + SINGLES)]
    names = {p["id"]: p["name"] for p in projects}
    groups = auto_groups(projects)
    assert set(groups) == {"Jade & Haile", "The Space Between Us"}
    assert [names[i] for i in groups["Jade & Haile"]] == \
        sorted(JADE, key=lambda n: int(re.search(r"Episode (\d)", n).group(1)))
    assert [names[i] for i in groups["The Space Between Us"]] == \
        [SPACE[1], SPACE[0], SPACE[2]]


def test_exact_shared_title_groups_and_unnumbered_sort_by_name():
    projects = [{"id": "a", "name": "Sketches"}, {"id": "b", "name": "Sketches"},
                {"id": "c", "name": "Diary — Winter"}, {"id": "d", "name": "Diary — Autumn"},
                {"id": "e", "name": "Diary — Part 1"}]
    groups = auto_groups(projects)
    assert sorted(groups["Sketches"]) == ["a", "b"]
    assert groups["Diary"] == ["e", "d", "c"]   # numbered first, then by name


# ---------------------------------------------------------------- CRUD

def test_crud_and_validation(env):
    c, storage, _ = env
    a, b = _project(storage, "A"), _project(storage, "B", pages=3)
    assert c.get("/api/collections").json() == {"collections": []}

    assert c.post("/api/collections", json={"name": "  "}).status_code == 400
    assert c.post("/api/collections", json={"name": "S", "projectIds": ["nope"]}).status_code == 400
    assert c.post("/api/collections", json={"name": "S", "projectIds": [a, a]}).status_code == 400
    assert c.post("/api/collections", json={"name": "S", "projectIds": ["../x"]}).status_code == 400

    r = c.post("/api/collections", json={"name": "Series", "projectIds": [a, b]})
    assert r.status_code == 200, r.text
    col = r.json()["collection"]
    assert col["auto"] is False and col["projectIds"] == [a, b]
    assert [e["pages"] for e in col["episodes"]] == [1, 3]
    assert col["episodes"][0]["cover"].startswith("/api/assets/file/")
    assert col["coverUrl"] == col["episodes"][0]["cover"]

    cid = col["id"]
    r = c.patch(f"/api/collections/{cid}", json={"name": "Renamed", "description": "d",
                                                 "projectIds": [b, a]})
    assert r.status_code == 200, r.text
    assert r.json()["collection"]["projectIds"] == [b, a]
    assert r.json()["collection"]["name"] == "Renamed"
    assert c.patch(f"/api/collections/{cid}", json={"projectIds": [b, b]}).status_code == 400
    assert c.patch(f"/api/collections/{cid}", json={"projectIds": [b, "zz"]}).status_code == 400
    assert c.patch(f"/api/collections/{cid}", json={"cover": {"projectId": "zz"}}).status_code == 400
    r = c.patch(f"/api/collections/{cid}", json={"cover": {"projectId": b, "pageId": "pg2"}})
    assert r.json()["collection"]["cover"] == {"projectId": b, "pageId": "pg2"}
    assert c.patch("/api/collections/nope", json={"name": "x"}).status_code == 404

    assert c.get(f"/api/collections/{cid}").json()["collection"]["name"] == "Renamed"
    assert c.delete(f"/api/collections/{cid}").json() == {"success": True}
    assert c.delete(f"/api/collections/{cid}").status_code == 404
    assert storage.load_project(a) and storage.load_project(b)   # projects untouched


def test_delete_project_removes_it_from_collections(env):
    c, storage, _ = env
    a, b = _project(storage, "A"), _project(storage, "B")
    cid = c.post("/api/collections", json={"name": "S", "projectIds": [a, b]}).json()["collection"]["id"]
    c.post("/api/collections", json={"name": "T", "projectIds": [b]})
    c.patch(f"/api/collections/{cid}", json={"cover": {"projectId": b, "pageId": "pg0"}})
    assert c.delete(f"/api/projects/delete/{b}").status_code == 200
    cols = {x["name"]: x for x in c.get("/api/collections").json()["collections"]}
    assert cols["S"]["projectIds"] == [a] and cols["S"]["cover"] is None
    assert cols["T"]["projectIds"] == []


def test_missing_project_skipped_in_listing(env, tmp_path):
    import shutil
    c, storage, _ = env
    a, b = _project(storage, "A"), _project(storage, "B")
    c.post("/api/collections", json={"name": "S", "projectIds": [a, b]})
    shutil.rmtree(tmp_path / "projects" / b)    # vanished behind our back
    col = c.get("/api/collections").json()["collections"][0]
    assert [e["id"] for e in col["episodes"]] == [a]
    assert col["missing"] == [b]


def test_auto_group_endpoint_respects_manual_collections(env):
    c, storage, _ = env
    ids = {n: _project(storage, n) for n in JADE + SPACE + SINGLES}
    # a manual collection named like a series: auto-group must leave it alone
    manual = c.post("/api/collections", json={
        "name": "The Space Between Us", "projectIds": [ids[SPACE[0]]]}).json()["collection"]

    r = c.post("/api/collections/auto-group")
    assert r.status_code == 200, r.text
    out = r.json()
    assert [x["name"] for x in out["created"]] == ["Jade & Haile"]
    assert [x["name"] for x in out["skipped"]] == ["The Space Between Us"]
    cols = {x["id"]: x for x in out["collections"]}
    assert cols[manual["id"]]["projectIds"] == [ids[SPACE[0]]]
    jade = next(x for x in out["collections"] if x["name"] == "Jade & Haile")
    assert jade["auto"] is True
    assert [e["name"].split(" — ")[1] for e in jade["episodes"]] == \
        [f"Episode {n}" for n in range(1, 8)]

    # re-run: nothing new; a new episode updates the auto collection
    again = c.post("/api/collections/auto-group").json()
    assert again["created"] == [] and again["updated"] == []
    ep8 = _project(storage, "Jade & Haile — Episode 8 — Graduation")
    again = c.post("/api/collections/auto-group").json()
    assert [x["name"] for x in again["updated"]] == ["Jade & Haile"]
    assert again["updated"][0]["projectIds"][-1] == ep8

    # once the user edits it, it is manual and auto-group stops touching it
    c.patch(f"/api/collections/{jade['id']}", json={"projectIds": [ids[JADE[1]]]})
    _project(storage, "Jade & Haile — Episode 9")
    again = c.post("/api/collections/auto-group").json()
    assert [x["name"] for x in again["skipped"]] == ["Jade & Haile", "The Space Between Us"]
    assert c.get(f"/api/collections/{jade['id']}").json()["collection"]["projectIds"] == \
        [ids[JADE[1]]]


# ---------------------------------------------------------------- export

def _wait(c, job_id, timeout=60.0):
    end = time.time() + timeout
    while time.time() < end:
        job = c.get(f"/api/collections/exports/{job_id}").json()
        if job["status"] != "running":
            return job
        time.sleep(0.05)
    raise AssertionError("export did not finish")


def _pdf_pages(data: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page(?![s\w])", data))


def test_collection_export_end_to_end(env, tmp_path, monkeypatch):
    pytest.importorskip("reportlab")
    import shutil
    from backend.render import collection_export
    c, storage, exports = env
    e1 = _project(storage, "Saga — Episode 1 — Start", pages=2)
    e2 = _project(storage, "Saga — Episode 2 — Middle", pages=3)
    gone = _project(storage, "Saga — Episode 3")
    cid = c.post("/api/collections", json={"name": "Saga", "projectIds": [e1, gone, e2]}
                 ).json()["collection"]["id"]
    shutil.rmtree(tmp_path / "projects" / gone)

    labels = []
    real_stamp = collection_export.stamp_label
    monkeypatch.setattr(collection_export, "stamp_label",
                        lambda img, label, scale: (labels.append(label),
                                                   real_stamp(img, label, scale)))
    r = c.post(f"/api/collections/{cid}/export", json={
        "format": "both", "scale": 1, "pageNumbers": True,
        "episodeTitlePages": True, "cover": True})
    assert r.status_code == 202, r.text
    assert r.json()["total"] == 1 + (1 + 2) + (1 + 3)
    job = _wait(c, r.json()["id"])
    assert job["status"] == "done", job
    assert job["done"] == job["total"] == 8
    assert any(gone in w for w in job["warnings"])
    # continuous across the collection; the cover (page 1) is unnumbered
    assert labels == [str(n) for n in range(2, 9)]

    pdf_name = job["pdf"]["url"].rsplit("/", 1)[-1]
    zip_name = job["zip"]["url"].rsplit("/", 1)[-1]
    assert re.fullmatch(rf"collection_{cid[:8]}_\d{{8}}_\d{{6}}\.pdf", pdf_name)
    pdf = c.get(job["pdf"]["url"])
    assert pdf.status_code == 200 and _pdf_pages(pdf.content) == 8
    with zipfile.ZipFile(io.BytesIO(c.get(job["zip"]["url"]).content)) as zf:
        assert zf.namelist() == [f"page_{n:03d}.png" for n in range(1, 9)]
    # nothing left behind but the two outputs (no temp / _pages dirs)
    assert sorted(p.name for p in exports.iterdir()) == sorted([pdf_name, zip_name])
    # the existing export DELETE handles collection exports
    assert c.delete(f"/api/export/download/{pdf_name}").status_code == 200


def test_collection_export_without_extras(env):
    pytest.importorskip("reportlab")
    c, storage, _ = env
    e1, e2 = _project(storage, "X1", pages=2), _project(storage, "X2", pages=1)
    cid = c.post("/api/collections", json={"name": "X", "projectIds": [e1, e2]}
                 ).json()["collection"]["id"]
    r = c.post(f"/api/collections/{cid}/export", json={
        "format": "pdf", "episodeTitlePages": False, "cover": False, "scale": 0.01})
    job = _wait(c, r.json()["id"])
    assert job["status"] == "done" and job["total"] == 3 and job["zip"] is None
    assert _pdf_pages(c.get(job["pdf"]["url"]).content) == 3
    assert c.post(f"/api/collections/{cid}/export", json={"format": "tiff"}).status_code == 400
    assert c.post("/api/collections/nope/export", json={}).status_code == 404
    empty = c.post("/api/collections", json={"name": "E"}).json()["collection"]["id"]
    assert c.post(f"/api/collections/{empty}/export", json={}).status_code == 400


def test_collection_export_streams_one_page_at_a_time(env, monkeypatch):
    """~40 pages: never more than a couple of rendered page images alive."""
    pytest.importorskip("reportlab")
    from backend.render import collection_export
    c, storage, _ = env
    ids = [_project(storage, f"Long — Part {i}", pages=8) for i in range(1, 6)]
    cid = c.post("/api/collections", json={"name": "Long", "projectIds": ids}
                 ).json()["collection"]["id"]
    alive = {"now": 0, "peak": 0}
    real = collection_export.render_page

    def counting(page, scale, resolve=None):
        img = real(page, scale, resolve)
        alive["now"] += 1
        alive["peak"] = max(alive["peak"], alive["now"])
        weakref.finalize(img, lambda: alive.__setitem__("now", alive["now"] - 1))
        return img
    monkeypatch.setattr(collection_export, "render_page", counting)
    r = c.post(f"/api/collections/{cid}/export", json={
        "format": "both", "scale": 1, "cover": True, "pageNumbers": True})
    job = _wait(c, r.json()["id"])
    assert job["status"] == "done" and job["total"] == 1 + 5 * 9
    # the generated pages hold one pre-rendered thumbnail next to the page
    assert alive["peak"] <= 3, alive


def test_concurrent_collection_export_is_409(env, monkeypatch):
    pytest.importorskip("reportlab")
    from backend.render import collection_export
    c, storage, _ = env
    e1 = _project(storage, "C1", pages=2)
    cid = c.post("/api/collections", json={"name": "C", "projectIds": [e1]}
                 ).json()["collection"]["id"]
    gate = threading.Event()
    real = collection_export.render_page

    def slow(page, scale, resolve=None):
        gate.wait(10)
        return real(page, scale, resolve)
    monkeypatch.setattr(collection_export, "render_page", slow)
    first = c.post(f"/api/collections/{cid}/export", json={"format": "pdf"})
    assert first.status_code == 202
    try:
        second = c.post(f"/api/collections/{cid}/export", json={"format": "pdf"})
        assert second.status_code == 409
    finally:
        gate.set()
    assert _wait(c, first.json()["id"])["status"] == "done"
    assert c.get("/api/collections/exports/nope").status_code == 404


def test_prune_groups_collection_exports(tmp_path):
    import os
    from backend.render.export_service import export_group, prune_exports
    assert export_group("collection_ab12cd34_20261117_120000") == "collection:ab12cd34"
    now = time.time()
    for i in range(22):
        p = tmp_path / f"collection_ab12cd34_20261117_{i:06d}.pdf"
        p.write_bytes(b"%PDF")
        os.utime(p, (now - i * 60, now - i * 60))
    old = tmp_path / "collection_ffffffff_20261001_000000.zip"
    old.write_bytes(b"zip")
    os.utime(old, (now - 30 * 86400, now - 30 * 86400))
    prune_exports(tmp_path, now=now)
    left = sorted(p.name for p in tmp_path.iterdir())
    assert len(left) == 20 and old.name not in left
    assert "collection_ab12cd34_20261117_000021.pdf" not in left
