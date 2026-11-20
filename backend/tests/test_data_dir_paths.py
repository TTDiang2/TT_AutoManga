"""AUTOMANGA_DATA_DIR must relocate all of data/, not just part of it.

The paths are module constants computed at import, so each check runs in a
fresh interpreter with the variable set."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_PROBE = r"""
import json
from backend.core import config
from backend.api import archive, character_templates, characters, composer_templates, export, layouts
from backend import prompting
print(json.dumps({
    "DATA_DIR": str(config.DATA_DIR),
    "settings": str(config.SETTINGS_FILE),
    "projects": str(config.PROJECTS_DIR),
    "assets": str(config.ASSETS_DIR),
    "characters": str(characters.CHARACTERS_FILE),
    "prompting_characters": str(prompting._CHARACTERS_FILE),
    "character_templates": str(character_templates.TEMPLATES_FILE),
    "composer_templates": str(composer_templates.TEMPLATES_FILE),
    "layouts": str(layouts.LAYOUTS_FILE),
    "archive": str(archive.ARCHIVE_DIR),
    "exports": str(export.EXPORTS_DIR),
}))
"""


def _paths(data_dir: Path) -> dict:
    env = {**os.environ, "AUTOMANGA_DATA_DIR": str(data_dir)}
    out = subprocess.run([sys.executable, "-c", _PROBE], cwd=ROOT, env=env,
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_every_data_path_follows_automanga_data_dir(tmp_path):
    data = tmp_path / "other-data"
    paths = _paths(data)
    root = data.resolve()
    for name, value in paths.items():
        assert Path(value).resolve().is_relative_to(root), f"{name} is outside AUTOMANGA_DATA_DIR: {value}"
    # nothing was written to the repo's own data/ by importing
    assert (data / "exports").is_dir()


def test_library_and_generation_read_the_same_characters_file(tmp_path):
    paths = _paths(tmp_path / "d")
    assert paths["characters"] == paths["prompting_characters"]


def test_no_module_builds_its_own_data_path():
    """Paths under data/ must come from core.config.DATA_DIR."""
    offenders = []
    for py in (ROOT / "backend").rglob("*.py"):
        if "tests" in py.parts or py.name == "config.py":
            continue
        text = py.read_text(encoding="utf-8")
        if re.search(r"""/\s*["']data["']""", text):
            offenders.append(str(py.relative_to(ROOT)))
    assert not offenders, f"build paths from DATA_DIR instead: {offenders}"
