"""Comics tab AI rewrite: POST /api/comics/scripts/{name}/rewrite with the LLM
mocked (an httpx MockTransport) and a stub comic.js that plans the way the
real one rates panels: a panel in an uncut context (PANEL uncut, or on a
PAGE uncut, no todo) is mature unless its cast has li (a minor) or bo (no
age)."""
import json
import os
import shutil
import sys
from pathlib import Path

import httpx
import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT.parent))

from fastapi.testclient import TestClient  # noqa: E402

import backend.api.comics as cm  # noqa: E402
import backend.api.comics_rewrite as rw  # noqa: E402
from backend.core import config, openai_client  # noqa: E402
from backend.main import app  # noqa: E402

_FAKE_COMIC = r"""
const fs = require('fs');
const argv = process.argv.slice(2);
const text = argv.includes('--stdin') ? fs.readFileSync(0, 'utf8') : fs.readFileSync(argv[0], 'utf8');
fs.appendFileSync(__dirname + '/calls.log', JSON.stringify({ argv, text }) + '\n');
const lines = text.split('\n');
const bad = lines.findIndex((l) => l.includes('BROKEN'));
if (bad >= 0) { console.log(JSON.stringify({ ok: false, error: `x.comic:${bad + 1}: unknown character "zork"`, line: bad + 1 })); process.exit(1); }
const uncut = argv.includes('--uncut');
const panels = [];
let pageUncut = false, pageTodo = false, cur = null;
lines.forEach((raw, i) => {
  const l = raw.trim();
  let m;
  if ((m = l.match(/^PAGE\b(\s+uncut)?(\s+todo)?/))) { pageUncut = !!m[1]; pageTodo = !!m[2]; cur = null; return; }
  if ((m = l.match(/^PANEL\b(\s+uncut)?(\s+todo)?/))) {
    const u = pageUncut || !!m[1], todo = (pageUncut && pageTodo) || !!m[2];
    cur = null;
    if (todo || (u && !uncut)) return;
    cur = { id: `p${i}`, line: i + 1, edition: u ? 'uncut' : 'regular', rating: u ? 'mature' : 'sfw', cast: [] };
    panels.push(cur);
    return;
  }
  if (cur && (m = l.match(/^cast:\s*(.*)$/))) cur.cast = m[1].split(',').map((c) => c.trim().split('(')[0]);
});
for (const p of panels) {
  if (p.edition !== 'uncut') continue;
  if (p.cast.includes('li')) { p.rating = 'sfw'; p.notice = 'painted SFW: li is a minor (age 16)'; }
  else if (p.cast.includes('bo')) { p.rating = 'sfw'; p.notice = 'painted SFW: bo has no age (add "age BO: <n>", 18 or over)'; }
}
console.log(JSON.stringify({ ok: true, ...(uncut ? { edition: 'uncut' } : {}), panels }));
"""

SCRIPT = """title: Test
seed: 100
character KIM: adult woman, 30 years old
age KIM: 30

PAGE
layout: 1-2

PANEL
place: diner, evening
cast: kim(casual)
shot: medium
Kim sits in a booth.
KIM: I have been waiting here for a really long time, you know.

PANEL uncut todo
cast: kim(casual)
// TODO: describe the panel

PANEL uncut
cast: kim(casual), li
Two at the counter.

PAGE uncut
PANEL
cast: kim, bo
// TODO

PANEL
cast: kim
Kim alone.
"""


def _span(text, first_line, last_line):
    """UTF-16 offsets (here: ASCII) of 1-based lines first..last, with the final newline."""
    lines = text.split("\n")
    start = sum(len(l) + 1 for l in lines[:first_line - 1])
    end = sum(len(l) + 1 for l in lines[:last_line])
    return start, end


@pytest.fixture
def client():
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
    monkeypatch.setattr(cm, "COMICS_DIR", root)
    return root


def _calls(repo):
    log = repo / "calls.log"
    return [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []


@pytest.fixture
def llm(monkeypatch):
    """The LLM: answers with llm.answer (or llm.status/llm.body for errors); records each request body."""
    monkeypatch.setattr(config.settings.api, "endpoint", "http://127.0.0.1:1234/v1")
    monkeypatch.setattr(config.settings.api, "api_key", "")
    monkeypatch.setattr(config.settings.api, "model", "stored-model")

    class State:
        answer = "PANEL\nfoo\n"
        status = 200
        body = None
        sent = []
    st = State()
    st.sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        st.sent.append(json.loads(request.content))
        if st.status != 200:
            return httpx.Response(st.status, text=st.body or "")
        return httpx.Response(200, json={"choices": [{"message": {"content": st.answer}}]})

    real = httpx.AsyncClient
    monkeypatch.setattr(openai_client.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler),
                                          **{k: v for k, v in kw.items() if k != "http2"}))
    return st


def _post(client, body, name="test"):
    return client.post(f"/api/comics/scripts/{name}/rewrite", json=body)


# ---------------------------------------------------------------------------
# happy paths
# ---------------------------------------------------------------------------

def test_tighten_dialogue(client, repo, llm):
    start, end = _span(SCRIPT, 9, 15)
    llm.answer = ("PANEL\nplace: diner, evening\ncast: kim(casual)\nshot: medium\nKim sits in a booth.\n"
                  "KIM: I waited. Forever.")
    r = _post(client, {"text": SCRIPT, "start": start, "end": end, "action": "tighten_dialogue"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["original"] == SCRIPT[start:end]
    assert d["suggestion"].endswith("KIM: I waited. Forever.\n\n")   # the block's trailing blank line is kept
    assert d["plan"] == {"ok": True, "error": None, "line": None}
    assert d["model"] == "stored-model" and isinstance(d["durationMs"], int)
    sent = llm.sent[0]
    assert sent["temperature"] == 0.7 and sent["max_tokens"] == 4096 and sent["model"] == "stored-model"
    system, user = sent["messages"][0]["content"], sent["messages"][1]["content"]
    assert "ONLY the replacement text" in system
    assert "Tighten the dialogue" in user and "title: Test" in user and "KIM: I have been waiting" in user
    # validated on the text with the block replaced (--uncut: the script has uncut blocks)
    plan_call = _calls(repo)[-1]
    assert "--stdin" in plan_call["argv"] and "--uncut" in plan_call["argv"]
    assert "KIM: I waited. Forever." in plan_call["text"]
    assert plan_call["text"] == SCRIPT[:start] + d["suggestion"] + SCRIPT[end:]


def test_enrich_description_with_model_override(client, repo, llm):
    start, end = _span(SCRIPT, 9, 14)
    llm.answer = "PANEL\nplace: diner, evening\ncast: kim(casual)\nshot: medium\nKim in a red vinyl booth, neon light."
    r = _post(client, {"text": SCRIPT, "start": start, "end": end, "action": "enrich_description",
                       "model": "cydonia", "instruction": "rainy night"})
    assert r.status_code == 200, r.text
    assert r.json()["model"] == "cydonia" and llm.sent[0]["model"] == "cydonia"
    user = llm.sent[0]["messages"][1]["content"]
    assert "Enrich the panel descriptions" in user and "EXTRA INSTRUCTION: rainy night" in user
    # the regular panel of an SFW script: no minor check, so one plan call only
    assert len(_calls(repo)) == 1


def test_custom_needs_instruction(client, repo, llm):
    start, end = _span(SCRIPT, 9, 14)
    for instr in (None, "", "   "):
        r = _post(client, {"text": SCRIPT, "start": start, "end": end, "action": "custom", "instruction": instr})
        assert r.status_code == 400 and "instruction" in r.json()["detail"]
    assert r.status_code == 400
    assert not llm.sent
    llm.answer = "PANEL\ncast: kim(casual)\nKim stands up."
    r = _post(client, {"text": SCRIPT, "start": start, "end": end, "action": "custom", "instruction": "make her stand"})
    assert r.status_code == 200 and "AUTHOR'S INSTRUCTION: make her stand" in llm.sent[0]["messages"][1]["content"]
    assert _post(client, {"text": SCRIPT, "start": start, "end": end, "action": "custom",
                          "instruction": "x" * 2001}).status_code == 422


def test_draft_uncut_keeps_todo_by_default(client, repo, llm):
    start, end = _span(SCRIPT, 16, 19)
    llm.answer = "PANEL uncut\ncast: kim(wearing a robe)\nKim by the window, lamplight."
    r = _post(client, {"text": SCRIPT, "start": start, "end": end, "action": "draft_uncut"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["suggestion"].startswith("PANEL uncut todo\ncast: kim(wearing a robe)")
    assert d["plan"]["ok"] is True
    assert "Draft this uncut" in llm.sent[0]["messages"][1]["content"]
    # asked to: todo goes
    llm.answer = "PANEL uncut todo\ncast: kim(wearing a robe)\nKim by the window."
    r = _post(client, {"text": SCRIPT, "start": start, "end": end, "action": "draft_uncut", "remove_todo": True})
    assert r.json()["suggestion"].startswith("PANEL uncut\ncast:")


# ---------------------------------------------------------------------------
# minor protection and refusals
# ---------------------------------------------------------------------------

def test_draft_uncut_refused_outside_uncut_blocks(client, repo, llm):
    start, end = _span(SCRIPT, 9, 14)
    r = _post(client, {"text": SCRIPT, "start": start, "end": end, "action": "draft_uncut"})
    assert r.status_code == 400 and "uncut" in r.json()["detail"]
    assert not llm.sent


@pytest.mark.parametrize("lines,who", [((20, 23), "li is a minor"), ((25, 28), "bo has no age")])
@pytest.mark.parametrize("action", ["draft_uncut", "tighten_dialogue"])
def test_minor_or_unknown_age_never_reaches_the_model(client, repo, llm, lines, who, action):
    start, end = _span(SCRIPT, *lines)
    r = _post(client, {"text": SCRIPT, "start": start, "end": end, "action": action})
    assert r.status_code == 400
    assert who in r.json()["detail"] and "Not sent to the model" in r.json()["detail"]
    assert not llm.sent
    # the check planned the block as uncut panels, todo dropped (the page's too)
    probe = _calls(repo)[-1]
    assert "--uncut" in probe["argv"] and "PAGE uncut todo" not in probe["text"]


def test_mature_script_checks_regular_panels(client, repo, llm):
    text = SCRIPT.replace("seed: 100", "seed: 100\nrating: mature").replace("cast: kim(casual)\nshot: medium",
                                                                           "cast: kim(casual), li\nshot: medium")
    start, end = _span(text, 10, 15)
    r = _post(client, {"text": text, "start": start, "end": end, "action": "enrich_description"})
    assert r.status_code == 400 and "li is a minor" in r.json()["detail"]
    assert not llm.sent
    probe = _calls(repo)[-1]["text"].split("\n")
    assert probe[9] == "PANEL uncut"   # the regular panel was planned as a mature one


def test_suggestion_adding_a_minor_fails_the_plan(client, repo, llm):
    start, end = _span(SCRIPT, 16, 19)
    llm.answer = "PANEL uncut todo\ncast: kim(casual), li\nTwo."
    r = _post(client, {"text": SCRIPT, "start": start, "end": end, "action": "draft_uncut"})
    assert r.status_code == 200
    plan = r.json()["plan"]
    assert plan["ok"] is False and "minor protection" in plan["error"] and "li is a minor" in plan["error"]
    assert plan["line"] == 16


def test_fences_and_chatter_stripped(client, repo, llm):
    start, end = _span(SCRIPT, 9, 14)
    llm.answer = ("<think>hmm</think>Sure! Here is the rewritten block:\n```comic\nPANEL\nplace: diner, evening\n"
                  "cast: kim(casual)\nKim.\n```\nHope this helps!")
    r = _post(client, {"text": SCRIPT, "start": start, "end": end, "action": "enrich_description"})
    assert r.json()["suggestion"] == "PANEL\nplace: diner, evening\ncast: kim(casual)\nKim.\n"


def test_crlf_text_keeps_crlf(client, repo, llm):
    text = SCRIPT.replace("\n", "\r\n")
    lines = text.split("\n")
    start = sum(len(l) + 1 for l in lines[:8])
    end = sum(len(l) + 1 for l in lines[:14])
    llm.answer = "PANEL\ncast: kim(casual)\nKim."
    r = _post(client, {"text": text, "start": start, "end": end, "action": "enrich_description"})
    assert r.status_code == 200
    assert r.json()["suggestion"] == "PANEL\r\ncast: kim(casual)\r\nKim.\r\n"


def test_plan_failure_is_flagged(client, repo, llm):
    start, end = _span(SCRIPT, 9, 14)
    llm.answer = "PANEL\ncast: BROKEN\nKim."
    r = _post(client, {"text": SCRIPT, "start": start, "end": end, "action": "custom", "instruction": "x"})
    assert r.status_code == 200
    d = r.json()
    assert d["suggestion"].startswith("PANEL\ncast: BROKEN")
    assert d["plan"] == {"ok": False, "error": 'x.comic:10: unknown character "zork"', "line": 10}


@pytest.mark.parametrize("status,body,hint", [
    (404, '{"error":"Unexpected endpoint or method. (POST /chat/completions)"}', "end with /v1"),
    (400, '{"error":"The model has crashed without additional information. (Exit code: null)"}', "crashed"),
])
def test_llm_error_is_502_with_hint(client, repo, llm, status, body, hint):
    llm.status, llm.body = status, body
    start, end = _span(SCRIPT, 9, 14)
    r = _post(client, {"text": SCRIPT, "start": start, "end": end, "action": "tighten_dialogue"})
    assert r.status_code == 502
    assert hint in r.json()["detail"] and "LLM" in r.json()["detail"]


@pytest.mark.parametrize("start,end", [(-1, 5), (10, 5), (0, len(SCRIPT) + 1), (5, 5)])
def test_offsets_validated(client, repo, llm, start, end):
    r = _post(client, {"text": SCRIPT, "start": start, "end": end, "action": "tighten_dialogue"})
    assert r.status_code == 400
    assert not llm.sent


def test_bad_action_and_name(client, repo, llm):
    assert _post(client, {"text": SCRIPT, "start": 0, "end": 5, "action": "nope"}).status_code == 400
    assert _post(client, {"text": SCRIPT, "start": 0, "end": 5, "action": "custom", "instruction": "x"},
                 name="bad.name").status_code == 400
    assert not llm.sent


def test_utf16_offsets():
    text = "a😀b\nPANEL\n"
    assert rw._u16_len(text) == len(text) + 1
    assert rw._u16_index(text, 3) == 2      # after the emoji (2 code units)
    with pytest.raises(Exception):
        rw._u16_index(text, 2)              # inside the emoji


def test_structure_and_uncut_lines():
    lines = SCRIPT.split("\n")
    first, pages, panels = rw._structure(lines)
    assert first == 5 and [p.line for p in pages] == [5, 23]
    assert [(p.line, p.end, p.uncut, p.todo) for p in panels] == [
        (8, 14, False, False), (15, 18, True, True), (19, 22, True, False), (24, 27, False, False),
        (28, len(lines) - 1, False, False)]
    assert not rw._line_uncut(6, pages, panels)       # layout of a regular page
    assert rw._line_uncut(16, pages, panels) and rw._line_uncut(23, pages, panels) and rw._line_uncut(26, pages, panels)


# ---------------------------------------------------------------------------
# echoed prompt sections and the panel structure (a live cydonia answer to tighten_dialogue on
# rooftop-static 1.2 returned the block followed by the "CONTEXT AFTER" section, i.e. the next panels)
# ---------------------------------------------------------------------------

_REWRITTEN = ("PANEL\nplace: diner, evening\ncast: kim(casual)\nshot: medium\nKim sits in a booth.\n"
              "KIM: I waited. Forever.")
_ECHO = "PANEL uncut todo\ncast: kim(casual)\n// TODO: describe the panel\n\nPANEL uncut\ncast: kim(casual), li\nTwo at the counter.\n"


@pytest.mark.parametrize("heading", [
    "<<<CONTEXT_AFTER>>> (the script just after the block; read only, never return it)",
    "CONTEXT AFTER THE BLOCK (for continuity; do not return it):",   # the older prompt's label
    "<<<END>>>",
])
def test_echoed_context_is_cut(client, repo, llm, heading):
    start, end = _span(SCRIPT, 9, 15)
    llm.answer = f"{_REWRITTEN}\n\n\n{heading}\n{_ECHO}"
    r = _post(client, {"text": SCRIPT, "start": start, "end": end, "action": "tighten_dialogue"})
    assert r.status_code == 200, r.text
    d = r.json()
    # cut at the heading; the trailing blank lines trimmed back to the original block's one blank line
    assert d["suggestion"] == _REWRITTEN + "\n\n"
    assert d["plan"]["ok"] is True
    assert _calls(repo)[-1]["text"].count("PANEL uncut todo") == 1   # the next panels are not duplicated


def test_answer_between_block_markers(client, repo, llm):
    start, end = _span(SCRIPT, 9, 15)
    llm.answer = f"Sure, here it is:\n<<<BLOCK>>> (script lines 9-15)\n{_REWRITTEN}\n<<<END>>>\n\n<<<CONTEXT_AFTER>>>\n{_ECHO}"
    d = _post(client, {"text": SCRIPT, "start": start, "end": end, "action": "tighten_dialogue"}).json()
    assert d["suggestion"] == _REWRITTEN + "\n\n" and d["plan"]["ok"] is True


def test_prompt_puts_context_first_and_task_last(client, repo, llm):
    start, end = _span(SCRIPT, 9, 15)
    llm.answer = _REWRITTEN
    _post(client, {"text": SCRIPT, "start": start, "end": end, "action": "tighten_dialogue"})
    user = llm.sent[0]["messages"][1]["content"]
    i_head, i_after, i_block, i_end, i_task = (user.index(rw.SEC_HEADER), user.index(rw.SEC_AFTER),
                                               user.index(rw.SEC_BLOCK), user.index(rw.SEC_END), user.index("TASK:"))
    assert i_head < i_after < i_block < i_end < i_task
    assert "KIM: I have been waiting" in user[i_block:i_end] and "PANEL uncut todo" in user[i_after:i_block]
    assert user.rstrip().endswith("nothing after it.")


def test_duplicated_panels_fail_the_structure_check(client, repo, llm):
    # the echo without any heading: valid script (the plan passes), but the next panels would be doubled
    start, end = _span(SCRIPT, 9, 15)
    llm.answer = f"{_REWRITTEN}\n\n{_ECHO}"
    d = _post(client, {"text": SCRIPT, "start": start, "end": end, "action": "tighten_dialogue"}).json()
    assert d["plan"] == {"ok": False, "line": 9,
                         "error": "the model changed the panel structure (expected 1 panel, got 3)"}
    # a changed marker argument too
    llm.answer = _REWRITTEN.replace("PANEL", "PANEL h=1.2", 1)
    d = _post(client, {"text": SCRIPT, "start": start, "end": end, "action": "enrich_description"}).json()
    assert d["plan"]["ok"] is False
    assert d["plan"]["error"] == ('the model changed the panel structure (expected 1 panel, got 1): '
                                  '"PANEL" became "PANEL h=1.2"')
    # same markers, other whitespace: fine
    llm.answer = _REWRITTEN.replace("PANEL", "PANEL  ", 1)
    assert _post(client, {"text": SCRIPT, "start": start, "end": end, "action": "tighten_dialogue"}).json()["plan"]["ok"]


def test_custom_and_draft_uncut_may_change_the_structure(client, repo, llm):
    start, end = _span(SCRIPT, 9, 15)
    llm.answer = f"{_REWRITTEN}\n\nPANEL\ncast: kim(casual)\nKim leaves.\n\n<<<CONTEXT_AFTER>>>\n{_ECHO}"
    d = _post(client, {"text": SCRIPT, "start": start, "end": end, "action": "custom", "instruction": "split it"}).json()
    assert d["plan"]["ok"] is True
    assert d["suggestion"].endswith("Kim leaves.\n\n") and "PANEL uncut" not in d["suggestion"]   # the cut still applies
    start, end = _span(SCRIPT, 16, 19)
    llm.answer = "PANEL uncut\ncast: kim(wearing a robe)\nKim.\n\nPANEL uncut\ncast: kim\nKim again.\n<<<CONTEXT_AFTER>>>\nPANEL uncut\n"
    d = _post(client, {"text": SCRIPT, "start": start, "end": end, "action": "draft_uncut"}).json()
    assert d["plan"]["ok"] is True and d["suggestion"].count("PANEL uncut") == 2


def test_clean_unit():
    orig = "PANEL\nKIM: Hi.\n\n"
    assert rw._clean("PANEL\nKIM: Yo.\n\n   \n\nCONTEXT BEFORE THE BLOCK (x):\nPAGE\n", orig) == "PANEL\nKIM: Yo.\n\n"
    # a marker line before any content is dropped, not the whole answer
    assert rw._clean("<<<BLOCK>>>\nPANEL\nKIM: Yo.", orig) == "PANEL\nKIM: Yo.\n\n"
    assert rw._clean("<<<SCRIPT_HEADER>>>\nPANEL\nKIM: Yo.", orig) == "PANEL\nKIM: Yo.\n\n"
    assert rw._structure_error("PAGE 2\nlayout: 1\nPANEL\n", "PAGE 2\nPANEL\nPANEL\n").startswith(
        "the model changed the panel structure (expected 1 panel, got 2)")


def test_each_action_keeps_the_lines_it_may_not_touch(client, repo, llm):
    sfx = SCRIPT.replace("Kim sits in a booth.\n", "Kim sits in a booth.\nSFX (tr): KRZZT\n")
    start, end = _span(sfx, 9, 16)
    # tighten_dialogue dropped the SFX line: valid script, so only this check catches it
    llm.answer = _REWRITTEN
    d = _post(client, {"text": sfx, "start": start, "end": end, "action": "tighten_dialogue"}).json()
    assert d["plan"] == {"ok": False, "line": 9,
                         "error": 'the model removed "SFX (tr): KRZZT" (only dialogue may change)'}
    # dialogue rewritten, SFX kept: fine
    llm.answer = _REWRITTEN.replace("booth.\n", "booth.\nSFX (tr): KRZZT\n")
    assert _post(client, {"text": sfx, "start": start, "end": end, "action": "tighten_dialogue"}).json()["plan"]["ok"]
    # tighten_dialogue may not rewrite the description or the cast
    llm.answer = _REWRITTEN.replace("booth.\n", "booth, tired.\nSFX (tr): KRZZT\n")
    assert _post(client, {"text": sfx, "start": start, "end": end, "action": "tighten_dialogue"}).json()["plan"]["error"] == (
        'the model changed "Kim sits in a booth." to "Kim sits in a booth, tired." (only dialogue may change)')
    # enrich_description may only change the prose: the speech line must stay
    llm.answer = _REWRITTEN.replace("booth.\n", "booth, neon light on the window.\nSFX (tr): KRZZT\n")
    d = _post(client, {"text": sfx, "start": start, "end": end, "action": "enrich_description"}).json()
    assert d["plan"]["error"] == ('the model changed "KIM: I have been waiting here for a really long time, you know." '
                                  'to "KIM: I waited. Forever." (only descriptions may change)')
    llm.answer = ("PANEL\nplace: diner, evening\ncast: kim(casual)\nshot: medium\nKim sits in a booth.\n"
                  "Neon light spills over the window.\nSFX (tr): KRZZT\n"
                  "KIM: I have been waiting here for a really long time, you know.")
    assert _post(client, {"text": sfx, "start": start, "end": end, "action": "enrich_description"}).json()["plan"]["ok"]


def test_line_kinds():
    k = rw._line_kind
    assert [k(l) for l in ["PANEL", "cast: kim", "Shot: wide", "KIM (whisper): hi", "CAPTION: Later.", "SFX: BANG",
                           "TEXT (left): on my way", "// note", "", "Kim waits: still.", "MR. LEE: Hi"]] == [
        "marker", "key", "key", "speech", "caption", "sfx", "text", "comment", "blank", "description", "speech"]
    assert rw._kept_lines_error("PANEL\nKIM: a\n", "PANEL\nKIM: b\n", "custom") is None
