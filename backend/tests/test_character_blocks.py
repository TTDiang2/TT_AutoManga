"""Character prompt blocks injected into a panel's prompt: a panel showing
several people never gets a block's ``solo`` tag (two "1x, solo" blocks make
the model merge the characters into one person).

Run: python -m pytest backend/tests/test_character_blocks.py -q
"""
import json
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT.parent))

JACK = {"id": "c1", "name": "Jack", "appearance": "1boy, solo, mature man, black glasses"}
HELLEN = {"id": "c2", "name": "Hellen", "appearance": "1girl, Solo Focus, blonde ponytail, solo"}
ONLY_SOLO = {"id": "c3", "name": "Kai", "appearance": "solo"}


@pytest.fixture
def prompting(tmp_path, monkeypatch):
    import backend.prompting as mod
    f = tmp_path / "characters.json"
    f.write_text(json.dumps([JACK, HELLEN, ONLY_SOLO]), encoding="utf-8")
    monkeypatch.setattr(mod, "_CHARACTERS_FILE", f)
    return mod


def test_solo_panel_keeps_the_block(prompting):
    assert prompting.blocks_for_panel({}, {"characters": ["Jack"]}) == [JACK["appearance"]]
    # the same name twice is still one person
    assert prompting.blocks_for_panel({}, {"characters": ["Jack", " jack "]}) == [JACK["appearance"]] * 2


def test_multi_character_panel_drops_solo(prompting):
    assert prompting.blocks_for_panel({}, {"characters": ["Jack", "Hellen"]}) == [
        "1boy, mature man, black glasses",
        "1girl, blonde ponytail",
    ]


def test_block_of_only_solo_is_skipped(prompting):
    assert prompting.blocks_for_panel({}, {"characters": ["Jack", "Kai"]}) == ["1boy, mature man, black glasses"]


def test_project_blocks_are_cleaned_too(prompting):
    project = {"settings": {"characters": [{"name": "Jack", "prompt_block": "1boy, solo, red scarf"}]}}
    assert prompting.blocks_for_panel(project, {"characters": ["Jack", "Hellen"]})[0] == "1boy, red scarf"
