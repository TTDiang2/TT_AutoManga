"""POST /api/settings/: the IP-Adapter (swarmui.ipadapter*) and LoRA training
(training.*) blocks of the Settings tab, validated on the server.

Run: python -m pytest backend/tests/test_settings_training.py -q
"""
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT.parent))

from backend.core import config  # noqa: E402


@pytest.fixture
def client(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from backend.main import app
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    saved = config.settings.model_copy(deep=True)
    yield TestClient(app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1")
    for name in config.AppSettings.model_fields:
        setattr(config.settings, name, getattr(saved, name))


def test_training_block_saves_and_reads_back(client):
    body = {"training": {"host": "me@trainer.lan", "toolkitDir": "~/ai-toolkit",
                         "python": "venv/bin/python", "baseModel": "/home/me/m/base.safetensors",
                         "loraFolder": "Comics/Trained", "sampling": True,
                         "resolution": [768, 512, 512], "cacheTextEmbeddings": True}}
    r = client.post("/api/settings/", json=body)
    assert r.status_code == 200, r.text
    t = config.settings.training
    assert (t.host, t.loraFolder, t.sampling, t.resolution, t.cacheTextEmbeddings) == \
        ("me@trainer.lan", "Comics/Trained", True, [512, 768], True)
    assert client.get("/api/training/settings").json()["host"] == "me@trainer.lan"
    assert client.get("/api/settings/").json()["training"]["resolution"] == [512, 768]
    # a partial update leaves the other fields alone
    assert client.post("/api/settings/", json={"training": {"sampling": False}}).status_code == 200
    assert config.settings.training.host == "me@trainer.lan"
    assert config.settings.training.sampling is False


def test_training_default_resolution_is_8gb_safe():
    assert config.TrainingConfig().resolution == [512, 768]


@pytest.mark.parametrize("field,value", [
    ("host", "trainer.lan"),                 # no user@
    ("host", "me@trainer lan"),
    ("host", "-oProxyCommand=x@h"),
    ("host", "me@'h'"),
    ("toolkitDir", "~/ai toolkit"),
    ("toolkitDir", "~/x;rm -rf ~"),
    ("python", "-c"),
    ("baseModel", "/m/$(id).safetensors"),
    ("loraFolder", "../Models"),
    ("loraFolder", "Comics/../../x"),
    ("loraFolder", ".hidden"),
    ("loraFolder", ""),
    ("resolution", [1000]),                  # not a multiple of 64
    ("resolution", [128]),
    ("resolution", [2048]),
    ("resolution", []),
])
def test_training_block_rejects_unsafe_values(client, field, value):
    before = config.settings.training.model_copy()
    r = client.post("/api/settings/", json={"training": {field: value}})
    assert r.status_code == 422, (field, value, r.text)
    assert config.settings.training == before


def test_ipadapter_block_validated(client):
    ok = {"swarmui": {"ipadapterPreset": "FACE", "ipadapterWeightType": "style transfer",
                      "ipadapterEnd": 0.5}}
    assert client.post("/api/settings/", json=ok).status_code == 200
    sw = config.settings.swarmui
    assert (sw.ipadapterPreset, sw.ipadapterWeightType, sw.ipadapterEnd) == \
        ("FACE", "style transfer", 0.5)
    for bad in ({"ipadapterWeightType": "linear"}, {"ipadapterPreset": "  "},
                {"ipadapterPreset": "a\nb"}):
        r = client.post("/api/settings/", json={"swarmui": bad})
        assert r.status_code == 422, bad
    assert config.settings.swarmui.ipadapterWeightType == "style transfer"
