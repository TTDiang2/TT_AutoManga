"""Comics tab "Batch AI": POST /api/comics/scripts/{name}/rewrite-batch and /api/comics/rewrite-batch/current, with
the LLM mocked and comic.js stubbed (the stub and the script of test_comics_rewrite.py)."""
import json
import threading
import time

import httpx
import pytest

from fastapi.testclient import TestClient

import backend.api.comics_rewrite_batch as rb
from backend.core import config, openai_client
from backend.main import app
from backend.tests.test_comics_rewrite import SCRIPT, _calls, _span, repo  # noqa: F401  (repo: a fixture)

URL = "/api/comics/rewrite-batch/current"
DINER = _span(SCRIPT, 9, 15)        # PANEL (regular): kim
TODO = _span(SCRIPT, 16, 19)        # PANEL uncut todo: kim
MINOR = _span(SCRIPT, 20, 23)       # PANEL uncut: kim, li (a minor)
UNKNOWN = _span(SCRIPT, 25, 28)     # PAGE uncut, PANEL: kim, bo (no age)
ALONE = (_span(SCRIPT, 29, 32)[0], len(SCRIPT))     # PAGE uncut, PANEL: kim


@pytest.fixture
def client():
    return TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))


@pytest.fixture(autouse=True)
def state(tmp_path, monkeypatch):
    """A fresh job state and file per test; the worker is waited for afterwards."""
    monkeypatch.setattr(rb, "BATCH_FILE", tmp_path / "rewrite_batch.json")
    monkeypatch.setattr(rb, "_job", None)
    monkeypatch.setattr(rb, "_loaded", False)
    monkeypatch.setattr(rb, "_worker", None)
    rb._stop.clear()
    yield
    w = rb._worker
    if w is not None:
        rb._stop.set()
        w.join(10)


@pytest.fixture
def llm(monkeypatch):
    """The LLM: llm.reply(user_prompt) answers (or raises httpx errors / returns llm.status); every request is
    recorded. llm.gate, when set, holds each call until it is set."""
    monkeypatch.setattr(config.settings.api, "endpoint", "http://127.0.0.1:1234/v1")
    monkeypatch.setattr(config.settings.api, "api_key", "")
    monkeypatch.setattr(config.settings.api, "model", "stored-model")

    class State:
        sent = []
        gate = None
        entered = threading.Event()
        fail_on = ()          # substrings of the block: answer 500
        connect_error = False

        def reply(self, user):
            block = user.split("<<<BLOCK>>>", 1)[1].split("<<<END>>>", 1)[0]
            body = "\n".join(block.split("\n")[1:]).strip("\n")
            return f"<<<BLOCK>>>\n{body}\n// rewritten\n<<<END>>>\n<<<CONTEXT_AFTER>>>\nPANEL\necho"
    st = State()
    st.sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        st.sent.append(body)
        st.entered.set()
        if st.gate is not None:
            st.gate.wait(10)
        if st.connect_error:
            raise httpx.ConnectError("connection refused")
        user = body["messages"][-1]["content"]
        if any(s in user.split("<<<BLOCK>>>", 1)[1] for s in st.fail_on):
            return httpx.Response(500, text="model crashed")
        return httpx.Response(200, json={"choices": [{"message": {"content": st.reply(user)}}]})

    real = httpx.AsyncClient
    monkeypatch.setattr(openai_client.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler),
                                          **{k: v for k, v in kw.items() if k != "http2"}))
    return st


def _blocks(*spans, kind="panel"):
    return [{"start": s, "end": e, "label": f"b{i}", "kind": kind} for i, (s, e) in enumerate(spans)]


def _start(client, blocks, action="enrich_description", text=SCRIPT, **kw):
    return client.post("/api/comics/scripts/test/rewrite-batch", json={"text": text, "blocks": blocks, "action": action, **kw})


def _wait(client, timeout=20):
    t0 = time.time()
    while time.time() - t0 < timeout:
        b = client.get(URL).json()["batch"]
        if b and b["status"] != "running":
            return b
        time.sleep(0.05)
    raise AssertionError(f"the batch did not finish: {b}")


def _user(sent):
    return sent["messages"][-1]["content"]


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("spans,why", [
    ([(DINER[0], DINER[1] + 5), (DINER[1], TODO[1])], "overlap"),
    ([TODO, DINER], "overlap"),                       # not sorted
    ([(DINER[0], len(SCRIPT) + 1)], "out of range"),
    ([(-1, 5)], "out of range"),
    ([(5, 5)], "out of range"),                       # empty
])
def test_bad_blocks(client, repo, llm, spans, why):
    r = _start(client, _blocks(*spans))
    assert r.status_code == 400 and why in r.json()["detail"], r.text
    assert not llm.sent and not rb.BATCH_FILE.exists()


def test_no_blocks_bad_action_and_custom_without_instruction(client, repo, llm):
    assert _start(client, []).status_code == 400
    assert _start(client, _blocks(DINER), action="nope").status_code == 400
    r = _start(client, _blocks(DINER), action="custom", instruction="  ")
    assert r.status_code == 400 and "instruction" in r.json()["detail"]


def test_draft_uncut_needs_every_block_uncut(client, repo, llm):
    r = _start(client, _blocks(DINER, TODO), action="draft_uncut")
    assert r.status_code == 400 and "block 1" in r.json()["detail"] and "not an uncut block" in r.json()["detail"]
    r = _start(client, _blocks(TODO, ALONE), action="draft_uncut")
    assert r.status_code == 202, r.text
    b = _wait(client)
    assert b["done"] == 2
    # todo is kept for review (the single rewrite's rule)
    assert b["results"][0]["suggestion"].startswith("PANEL uncut todo\n")


def test_no_llm_configured(client, repo, llm, monkeypatch):
    monkeypatch.setattr(config.settings.api, "model", "")
    r = _start(client, _blocks(DINER))
    assert r.status_code == 400 and "no LLM configured" in r.json()["detail"]


# ---------------------------------------------------------------------------
# processing
# ---------------------------------------------------------------------------

def test_sequential_in_order_with_echo_cut(client, repo, llm):
    r = _start(client, _blocks(DINER, TODO, ALONE), model="cydonia", instruction="rainy")
    assert r.status_code == 202, r.text
    d = r.json()
    assert d["total"] == 3 and d["status"] == "running" and d["model"] == "cydonia"
    assert d["snapshotHash"] == rb.text_hash(SCRIPT) and "text" not in d
    b = _wait(client)
    assert b["status"] == "done" and b["done"] == 3 and b["failed"] == b["refused"] == 0
    # one call per block, in script order, each against the snapshot
    assert len(llm.sent) == 3
    blk = [_user(s).split("<<<BLOCK>>>")[1].split("<<<END>>>")[0] for s in llm.sent]
    assert [("Kim sits in a booth" in x, "TODO: describe" in x, "Kim alone." in x) for x in blk] == [
        (True, False, False), (False, True, False), (False, False, True)]
    assert all("EXTRA INSTRUCTION: rainy" in _user(s) and s["model"] == "cydonia" for s in llm.sent)
    res = b["results"]
    assert [r["index"] for r in res] == [0, 1, 2] and [r["label"] for r in res] == ["b0", "b1", "b2"]
    for r, (s, e) in zip(res, (DINER, TODO, ALONE)):
        assert r["status"] == "done" and r["start"] == s and r["end"] == e
        assert r["original"] == SCRIPT[s:e]
        # the echoed context after <<<END>>> is cut; the block's trailing blank line kept
        assert r["suggestion"].endswith("// rewritten\n" + ("\n" if SCRIPT[s:e].endswith("\n\n") else ""))
        assert "echo" not in r["suggestion"]
        assert r["plan"]["ok"] is True and isinstance(r["durationMs"], int)
    # each block was checked on the snapshot with only that block replaced
    plans = [c for c in _calls(repo) if "--uncut" in c["argv"] and "// rewritten" in c["text"]]
    assert all(c["text"].count("// rewritten") == 1 for c in plans)


def test_since_returns_only_changed_results(client, repo, llm):
    _start(client, _blocks(DINER, ALONE))
    b = _wait(client)
    seq = b["seq"]
    assert client.get(f"{URL}?since={seq}").json()["batch"]["results"] == []
    assert len(client.get(f"{URL}?since=0").json()["batch"]["results"]) == 2


def test_a_failing_block_does_not_stop_the_batch(client, repo, llm):
    llm.fail_on = ("TODO: describe",)
    _start(client, _blocks(DINER, TODO, ALONE))
    b = _wait(client)
    assert b["status"] == "done" and b["done"] == 2 and b["failed"] == 1
    bad = b["results"][1]
    assert bad["status"] == "failed" and "the LLM failed" in bad["error"] and bad["suggestion"] is None


def test_structure_check_flags_a_changed_panel(client, repo, llm):
    llm.reply = lambda user: "PANEL\nfoo\nPANEL\nbar"
    _start(client, _blocks(DINER), action="tighten_dialogue")
    r = _wait(client)["results"][0]
    assert r["status"] == "done" and r["plan"]["ok"] is False
    assert "changed the panel structure (expected 1 panel, got 2)" in r["plan"]["error"]


def test_refused_minor_blocks_never_reach_the_model(client, repo, llm):
    _start(client, _blocks(DINER, MINOR, UNKNOWN, ALONE), action="tighten_dialogue")
    b = _wait(client)
    assert b["status"] == "done" and b["done"] == 2 and b["refused"] == 2
    st = [r["status"] for r in b["results"]]
    assert st == ["done", "refused", "refused", "done"]
    assert "li is a minor" in b["results"][1]["error"] and "Not sent to the model" in b["results"][1]["error"]
    assert "bo has no age" in b["results"][2]["error"]
    assert len(llm.sent) == 2
    assert not any("cast: kim(casual), li" in _user(s).split("<<<BLOCK>>>")[1] for s in llm.sent)
    assert not any("cast: kim, bo" in _user(s).split("<<<BLOCK>>>")[1] for s in llm.sent)


def test_unreachable_llm_fails_the_job(client, repo, llm):
    llm.connect_error = True
    spans = [_span(SCRIPT, n, n) for n in (9, 10, 11, 12)] + [TODO]
    _start(client, _blocks(*spans))
    b = _wait(client)
    assert b["status"] == "failed" and "could not reach the LLM" in b["error"]
    assert b["failed"] == 3 and [r["status"] for r in b["results"]][3:] == ["pending", "pending"]


# ---------------------------------------------------------------------------
# one at a time, stop, clear, restart
# ---------------------------------------------------------------------------

def test_one_batch_at_a_time_and_stop(client, repo, llm):
    llm.gate = threading.Event()
    assert _start(client, _blocks(DINER, TODO, ALONE)).status_code == 202
    assert llm.entered.wait(10)
    r = client.post("/api/comics/scripts/other/rewrite-batch", json={"text": SCRIPT, "blocks": _blocks(DINER), "action": "enrich_description"})
    assert r.status_code == 409 and "test" in r.json()["detail"]
    assert client.delete(URL).status_code == 409   # running: stop first
    running = client.get(URL).json()["batch"]
    assert running["status"] == "running" and running["results"][0]["status"] == "running"
    assert client.post(f"{URL}/stop").status_code == 200
    llm.gate.set()
    b = _wait(client)
    assert b["status"] == "stopped"
    # the block in flight was cancelled: back to pending, like the rest
    assert [r["status"] for r in b["results"]] == ["pending", "pending", "pending"]
    assert len(llm.sent) == 1
    assert client.post(f"{URL}/stop").status_code == 409
    rb._worker.join(5)
    # finished: cleared, then another batch may start
    assert client.delete(URL).json() == {"ok": True}
    assert client.get(URL).json() == {"batch": None} and not rb.BATCH_FILE.exists()
    llm.gate = None
    assert _start(client, _blocks(DINER)).status_code == 202
    assert _wait(client)["done"] == 1


def test_persisted_after_every_block(client, repo, llm):
    _start(client, _blocks(DINER, ALONE))
    _wait(client)
    saved = json.loads(rb.BATCH_FILE.read_text())
    assert saved["text"] == SCRIPT and saved["status"] == "done"
    assert [r["status"] for r in saved["results"]] == ["done", "done"]


def test_restart_resumes_pending_blocks(client, repo, llm):
    # what a server killed mid-batch leaves behind: block 0 done, block 1 running, block 2 pending
    job = {
        "id": "abc123", "script": "test", "action": "enrich_description", "instruction": None, "kind": "panel",
        "model": "stored-model", "removeTodo": False, "status": "running", "error": None, "startedAt": 1.0,
        "endedAt": None, "snapshotHash": rb.text_hash(SCRIPT), "seq": 5, "text": SCRIPT,
        "results": [
            {"index": 0, "label": "a", "kind": "panel", "start": DINER[0], "end": DINER[1], "status": "done",
             "original": SCRIPT[DINER[0]:DINER[1]], "suggestion": "kept", "plan": {"ok": True, "error": None, "line": None},
             "error": None, "durationMs": 10, "seq": 3},
            {"index": 1, "label": "b", "kind": "panel", "start": TODO[0], "end": TODO[1], "status": "running",
             "original": SCRIPT[TODO[0]:TODO[1]], "suggestion": None, "plan": None, "error": None, "durationMs": None, "seq": 4},
            {"index": 2, "label": "c", "kind": "panel", "start": ALONE[0], "end": ALONE[1], "status": "pending",
             "original": SCRIPT[ALONE[0]:ALONE[1]], "suggestion": None, "plan": None, "error": None, "durationMs": None, "seq": 1},
        ],
    }
    rb.BATCH_FILE.write_text(json.dumps(job))
    # a new process: loading puts the running block back to pending...
    with rb._lock:
        rb._load()
        assert [r["status"] for r in rb._job["results"]] == ["done", "pending", "pending"]
    # ...and resume (startup, or the first request) carries on with it
    rb.resume()
    b = _wait(client)
    assert b["id"] == "abc123" and b["status"] == "done" and b["done"] == 3
    assert b["results"][0]["suggestion"] == "kept"
    assert len(llm.sent) == 2 and "TODO: describe" in _user(llm.sent[0])


def test_text_hash_matches_the_client():
    # frontend/src/components/comics/batch.test.ts checks the same values for batchApply.ts textHash
    assert rb.text_hash("") == "0:811c9dc5"
    assert rb.text_hash("a") == "1:e40c292c"
    assert rb.text_hash("PAGE\n😀") == "7:fbf9b471"
