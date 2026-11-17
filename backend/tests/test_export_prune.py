"""data/exports housekeeping: old exports are pruned on each new export
(older than 7 days, beyond the 20 newest per project) and a downloaded export
can be deleted with DELETE /api/export/download/{name}.

Run: python -m pytest backend/tests/test_export_prune.py -q
"""
import os
import sys
import time
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT.parent))

from backend.render.export_service import export_group, prune_exports  # noqa: E402

DAY = 86400


def _export(d: Path, stem: str, age_days: float, now: float, pages: bool = True) -> None:
    pdf = d / f"{stem}.pdf"
    pdf.write_bytes(b"%PDF")
    t = now - age_days * DAY
    os.utime(pdf, (t, t))
    if pages:
        pd = d / f"{stem}_pages"
        pd.mkdir()
        (pd / "page_001.png").write_bytes(b"png")
        os.utime(pd, (t, t))


def test_export_group_names():
    assert export_group("manga_67537cf6_20261117_073326") == "manga:67537cf6"
    assert export_group("manga_67537cf6-aaaa-bbbb_ab12cd34") == "manga:67537cf6"
    assert export_group("composer_ab12cd34") == "composer:"
    assert export_group("my notes") is None
    assert export_group("manga_67537cf6_2026") is None


def test_prune_by_age_and_count(tmp_path):
    now = time.time()
    for i in range(25):   # project A: 25 fresh exports, one per minute
        _export(tmp_path, f"manga_aaaaaaaa_20261117_{i:06d}", i / 1440, now)
    _export(tmp_path, "manga_bbbbbbbb_20261101_000000", 10, now)   # project B: too old
    _export(tmp_path, "manga_bbbbbbbb_20261116_000000", 1, now)    # project B: fresh
    (tmp_path / "notes.pdf").write_bytes(b"x")                     # not an export name
    os.utime(tmp_path / "notes.pdf", (now - 30 * DAY, now - 30 * DAY))

    deleted = prune_exports(tmp_path, now=now)

    left = sorted(p.name for p in tmp_path.iterdir())
    a = [n for n in left if n.startswith("manga_aaaaaaaa") and n.endswith(".pdf")]
    assert len(a) == 20
    # the 5 oldest of project A went, with their _pages folders
    for i in range(20, 25):
        assert f"manga_aaaaaaaa_20261117_{i:06d}.pdf" not in left
        assert f"manga_aaaaaaaa_20261117_{i:06d}_pages" not in left
    assert "manga_aaaaaaaa_20261117_000000_pages" in left
    assert "manga_bbbbbbbb_20261101_000000.pdf" not in left
    assert "manga_bbbbbbbb_20261101_000000_pages" not in left
    assert "manga_bbbbbbbb_20261116_000000.pdf" in left
    assert "notes.pdf" in left
    assert len(deleted) == 12


def test_prune_keeps_the_new_export(tmp_path):
    now = time.time()
    _export(tmp_path, "composer_ab12cd34", 30, now, pages=False)
    assert prune_exports(tmp_path, keep={"composer_ab12cd34"}, now=now) == []
    assert (tmp_path / "composer_ab12cd34.pdf").exists()


def test_agent_export_prunes(tmp_path, monkeypatch):
    """export_pages (POST /api/agent/export) prunes after writing."""
    pytest.importorskip("reportlab")
    from backend.render import export_service
    now = time.time()
    _export(tmp_path, "manga_aaaaaaaa_20261001_000000", 40, now)
    page = {"width": 60, "height": 90, "elements": [], "backgroundColor": "#ffffff"}
    out = export_service.export_pages([page], "pdf", 1.0, lambda ref: None,
                                      tmp_path, "manga_aaaaaaaa_20261117_120000")
    assert Path(out["pdf"]["path"]).exists()
    assert not (tmp_path / "manga_aaaaaaaa_20261001_000000.pdf").exists()
    assert not (tmp_path / "manga_aaaaaaaa_20261001_000000_pages").exists()


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import backend.api.export as export_mod
    from backend.main import app
    exports = tmp_path / "exports"
    exports.mkdir()
    monkeypatch.setattr(export_mod, "EXPORTS_DIR", exports)
    monkeypatch.setattr(export_mod, "EXPORTS_ROOT", exports.resolve())
    (tmp_path / "secret.pdf").write_bytes(b"secret")
    return TestClient(app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1"), exports


def test_delete_export_removes_file_and_pages(client):
    c, exports = client
    _export(exports, "manga_aaaaaaaa_20261117_120000", 0, time.time())
    r = c.delete("/api/export/download/manga_aaaaaaaa_20261117_120000.pdf")
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] == ["manga_aaaaaaaa_20261117_120000.pdf",
                                   "manga_aaaaaaaa_20261117_120000_pages"]
    assert list(exports.iterdir()) == []
    assert c.delete("/api/export/download/manga_aaaaaaaa_20261117_120000.pdf").status_code == 404


def test_delete_export_keeps_pages_while_a_sibling_remains(client):
    c, exports = client
    _export(exports, "manga_aaaaaaaa_20261117_120000", 0, time.time())
    (exports / "manga_aaaaaaaa_20261117_120000.zip").write_bytes(b"zip")
    assert c.delete("/api/export/download/manga_aaaaaaaa_20261117_120000.pdf").status_code == 200
    assert (exports / "manga_aaaaaaaa_20261117_120000_pages").is_dir()


@pytest.mark.parametrize("name", ["..%2Fsecret.pdf", "%2E%2E%2Fsecret.pdf", ".hidden.pdf",
                                  "page.png", "manga_x_pages", "a..pdf"])
def test_delete_export_rejects_bad_names(client, name):
    c, exports = client
    r = c.delete(f"/api/export/download/{name}")
    assert r.status_code in (400, 404, 405)   # 405: an encoded / matches no route
    assert (exports.parent / "secret.pdf").exists()


def test_delete_export_handler_rejects_traversal(client):
    import asyncio
    from fastapi import HTTPException
    import backend.api.export as export_mod
    _, exports = client
    with pytest.raises(HTTPException) as e:
        asyncio.run(export_mod.delete_export("../secret.pdf"))
    assert e.value.status_code == 400
    assert (exports.parent / "secret.pdf").exists()
