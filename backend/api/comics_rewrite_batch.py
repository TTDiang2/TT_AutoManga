"""Comics tab "Batch AI": the AI rewrite of comics_rewrite.py over many blocks of one script (every scene, page or
panel, or a chosen few), as one server-side job.

POST /api/comics/scripts/{name}/rewrite-batch takes the editor's text and the block list the client computed from
it (its outline), validates the blocks (sorted, non-overlapping, within the text; draft_uncut only when every
block is uncut) and rewrites them one at a time, in order, in a background thread: one LLM call at a time, one
batch at a time on the whole server (409 names the running one's script). Every block is rewritten against the
same snapshot text, exactly as the single rewrite would (the minor pre-check first: a refused block never
reaches the model), so a block's failure never stops the others.

Nothing is saved to the script: the client reviews the suggestions and applies the accepted ones in its editor.

Restart-proof: the job, its snapshot text included, is written to DATA_DIR/rewrite_batch.json (atomically) on
every change. A server that starts (or first hears of the batch) with a running job in that file puts its
running block back to pending and carries on.
"""
import asyncio
import json
import logging
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import comics as cm
from . import comics_rewrite as rw
from ..core.config import DATA_DIR, atomic_write_json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/comics", tags=["comics"])

BATCH_FILE = DATA_DIR / "rewrite_batch.json"
MAX_BLOCKS = 500
MAX_CONSECUTIVE_LLM_FAILURES = 3   # the LLM is unreachable (connection errors): the job fails instead of trying them all
_KINDS = ("scene", "page", "panel", "selection")

_lock = threading.RLock()
_job: Optional[Dict[str, Any]] = None
_loaded = False
_worker: Optional[threading.Thread] = None
_stop = threading.Event()
_cancel: Dict[str, Any] = {}       # {"loop", "task"} of the block being rewritten, to stop it mid-call


class BatchBlock(BaseModel):
    start: int
    end: int
    label: str = Field(default="", max_length=300)
    kind: str = Field(default="panel", max_length=20)


class BatchRequest(BaseModel):
    text: str = Field(max_length=rw.MAX_TEXT)
    blocks: List[BatchBlock]
    action: str
    instruction: Optional[str] = Field(default=None, max_length=2000)
    model: Optional[str] = Field(default=None, max_length=200)
    remove_todo: bool = False


def text_hash(text: str) -> str:
    """FNV-1a (32 bit) over the text's UTF-16 code units, with its length: "1234:9f3a01bc". The client computes
    the same (batchApply.ts textHash) to tell whether the editor still holds the snapshot."""
    h = 0x811C9DC5
    data = text.encode("utf-16-le")
    n = len(data) // 2
    for i in range(0, len(data), 2):
        h ^= data[i] | (data[i + 1] << 8)
        h = (h * 0x01000193) & 0xFFFFFFFF
    return f"{n}:{h:08x}"


# ---------------------------------------------------------------------------
# State: one job, in memory and in BATCH_FILE
# ---------------------------------------------------------------------------

def _save() -> None:
    if _job is not None:
        atomic_write_json(BATCH_FILE, _job)


def _bump(r: Optional[Dict[str, Any]] = None) -> None:
    """Something changed (a result r, or the job): a new seq for ?since=, and the file."""
    _job["seq"] += 1
    if r is not None:
        r["seq"] = _job["seq"]
    _save()


def _load() -> None:
    """The job from BATCH_FILE, once per process. A job left running (the server restarted mid-batch) has its
    running block put back to pending."""
    global _job, _loaded
    if _loaded:
        return
    _loaded = True
    try:
        job = json.loads(BATCH_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return
    except Exception as e:
        logger.warning("unreadable %s: %s", BATCH_FILE, e)
        return
    if not isinstance(job, dict) or not isinstance(job.get("results"), list) or "text" not in job:
        return
    _job = job
    if job.get("status") == "running":
        for r in job["results"]:
            if r.get("status") == "running":
                r["status"] = "pending"
                r["seq"] = job["seq"] = job.get("seq", 0) + 1
        _save()


def resume() -> None:
    """At startup (and on any batch request): load the job, and carry on with it if it was running."""
    with _lock:
        _load()
        if _job is not None and _job.get("status") == "running":
            _start_worker()


def _start_worker() -> None:
    global _worker
    if _worker is not None and _worker.is_alive():
        return
    _stop.clear()
    _worker = threading.Thread(target=_work, args=(_job["id"],), name="comics-rewrite-batch", daemon=True)
    _worker.start()


def _counts(job: Dict[str, Any]) -> Dict[str, int]:
    rs = job["results"]
    return {"total": len(rs), "done": sum(1 for r in rs if r["status"] == "done"),
            "failed": sum(1 for r in rs if r["status"] == "failed"),
            "refused": sum(1 for r in rs if r["status"] == "refused")}


def _public(job: Dict[str, Any], since: int = 0) -> Dict[str, Any]:
    out = {k: job.get(k) for k in ("id", "script", "action", "instruction", "kind", "status", "error", "model",
                                   "startedAt", "endedAt", "snapshotHash", "seq", "removeTodo")}
    out.update(_counts(job))
    out["results"] = [dict(r) for r in job["results"] if r.get("seq", 0) > since]
    out["partial"] = since > 0
    return out


# ---------------------------------------------------------------------------
# The worker: one block at a time
# ---------------------------------------------------------------------------

def _work(job_id: str) -> None:
    try:
        asyncio.run(_run(job_id))
    except Exception as e:   # a bug: the job fails rather than staying "running" forever
        logger.exception("comics rewrite batch crashed")
        with _lock:
            if _job is not None and _job["id"] == job_id and _job["status"] == "running":
                for r in _job["results"]:
                    if r["status"] == "running":
                        r["status"] = "pending"
                _job.update(status="failed", error=f"the batch crashed: {e}", endedAt=time.time())
                _bump()


def _next(job_id: str) -> Optional[Dict[str, Any]]:
    """The next pending block, marked running; None when the job ended, was stopped or replaced."""
    with _lock:
        if _job is None or _job["id"] != job_id or _job["status"] != "running":
            return None
        if _stop.is_set():
            _job.update(status="stopped", endedAt=time.time())
            _bump()
            return None
        r = next((r for r in _job["results"] if r["status"] == "pending"), None)
        if r is None:
            _job.update(status="done", endedAt=time.time())
            _bump()
            return None
        r["status"] = "running"
        _bump(r)
        return r


async def _run(job_id: str) -> None:
    with _lock:
        job = _job
        text, action = job["text"], job["action"]
        instruction, model, remove_todo = job.get("instruction"), job.get("model"), bool(job.get("removeTodo"))
        name = job["script"]
    path = cm._script_path(name)
    script = rw.Script(text)
    llm_failures = 0
    while True:
        r = _next(job_id)
        if r is None:
            return
        t0 = time.monotonic()
        update: Dict[str, Any] = {}
        task = None
        try:
            b = script.block(r["start"], r["end"], action)
            await rw.precheck(path, script, b, action)
            llm = rw.make_llm(model)
            task = asyncio.ensure_future(rw.rewrite(path, script, b, action, instruction, llm, remove_todo,
                                                    checked=True))
            with _lock:
                _cancel.update(loop=asyncio.get_running_loop(), task=task)
                stopping = _stop.is_set()
            if stopping:
                task.cancel()
            out = await task
            update = {"status": "done", "suggestion": out["suggestion"], "plan": out["plan"],
                      "durationMs": out["durationMs"], "model": out["model"]}
            llm_failures = 0
        except asyncio.CancelledError:
            update = {"status": "pending"}   # stopped mid-call: it was not rewritten
        except rw.Refused as e:
            update = {"status": "refused", "error": e.detail,
                      "plan": {"ok": False, "error": e.detail, "line": e.line}}
        except HTTPException as e:
            update = {"status": "failed", "error": str(e.detail)}
            low = str(e.detail).lower()
            if e.status_code == 502 and ("connect" in low or "refused" in low):
                llm_failures += 1
        except Exception as e:   # a bug in one block: the others still run
            logger.exception("comics rewrite batch: block %s failed", r["index"])
            update = {"status": "failed", "error": f"{e.__class__.__name__}: {e}"}
        finally:
            with _lock:
                _cancel.clear()
        update.setdefault("durationMs", int((time.monotonic() - t0) * 1000))
        with _lock:
            if _job is None or _job["id"] != job_id:
                return
            r.update(update)
            if llm_failures >= MAX_CONSECUTIVE_LLM_FAILURES:
                _job.update(status="failed", endedAt=time.time(),
                            error=f"stopped after {llm_failures} blocks in a row could not reach the LLM: {r['error']}")
            _bump(r)
            if _job["status"] != "running":
                return


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/scripts/{name}/rewrite-batch", status_code=202)
async def start_batch(name: str, req: BatchRequest):
    global _job
    cm._script_path(name)
    instruction = rw.check_action(req.action, req.instruction)
    if not req.blocks:
        raise HTTPException(status_code=400, detail="no blocks to rewrite")
    if len(req.blocks) > MAX_BLOCKS:
        raise HTTPException(status_code=400, detail=f"at most {MAX_BLOCKS} blocks per batch")
    script = rw.Script(req.text)
    prev_end = 0
    for i, blk in enumerate(req.blocks):
        if blk.kind not in _KINDS:
            raise HTTPException(status_code=400, detail=f"block {i + 1}: kind must be one of {list(_KINDS)}")
        if not (0 <= blk.start < blk.end <= script.len16):
            raise HTTPException(status_code=400, detail=f"block {i + 1} ({blk.label or blk.start}): offsets out of range")
        if blk.start < prev_end:
            raise HTTPException(status_code=400,
                                detail=f"block {i + 1} ({blk.label or blk.start}): blocks must be sorted and must not overlap")
        prev_end = blk.end
        try:
            script.block(blk.start, blk.end, req.action)
        except HTTPException as e:
            if req.action == "draft_uncut" and "uncut" in str(e.detail):
                raise HTTPException(status_code=400, detail=(
                    f"block {i + 1} ({blk.label or blk.start}) is not an uncut block: Draft uncut scene works only "
                    "when every block is inside a PAGE uncut / PANEL uncut block"))
            raise HTTPException(status_code=400, detail=f"block {i + 1} ({blk.label or blk.start}): {e.detail}")
    llm = rw.make_llm(req.model)
    with _lock:
        _load()
        if _job is not None and _job.get("status") == "running":
            raise HTTPException(status_code=409, detail=(
                f"a batch AI rewrite of {_job['script']} is running ({_counts(_job)['done']}/{len(_job['results'])}); "
                "one at a time"))
        if _worker is not None and _worker.is_alive():
            raise HTTPException(status_code=409, detail="the last batch is still stopping; try again in a moment")
        _job = {
            "id": uuid.uuid4().hex[:12], "script": name, "action": req.action, "instruction": instruction,
            "kind": req.blocks[0].kind if len({b.kind for b in req.blocks}) == 1 else "mixed",
            "model": llm.model, "removeTodo": req.remove_todo, "status": "running", "error": None,
            "startedAt": time.time(), "endedAt": None, "snapshotHash": text_hash(req.text), "seq": 1,
            "text": req.text,
            "results": [{"index": i, "label": b.label, "kind": b.kind, "start": b.start, "end": b.end,
                         "status": "pending", "original": script.block(b.start, b.end, req.action).original,
                         "suggestion": None, "plan": None, "error": None, "durationMs": None, "seq": 1}
                        for i, b in enumerate(req.blocks)],
        }
        _save()
        _start_worker()
        return _public(_job)


@router.get("/rewrite-batch/current")
async def current_batch(since: int = 0):
    resume()
    with _lock:
        return {"batch": _public(_job, since) if _job is not None else None}


@router.post("/rewrite-batch/current/stop")
async def stop_batch():
    resume()
    with _lock:
        if _job is None or _job["status"] != "running":
            raise HTTPException(status_code=409, detail="no batch is running")
        _stop.set()
        loop, task = _cancel.get("loop"), _cancel.get("task")
        if loop is not None and task is not None:
            loop.call_soon_threadsafe(task.cancel)
        if _worker is None or not _worker.is_alive():
            _job.update(status="stopped", endedAt=time.time())
            _bump()
        return _public(_job)


@router.delete("/rewrite-batch/current")
async def clear_batch():
    global _job
    resume()
    with _lock:
        if _job is not None and _job["status"] == "running":
            raise HTTPException(status_code=409, detail="the batch is running: stop it first")
        _job = None
        try:
            BATCH_FILE.unlink()
        except FileNotFoundError:
            pass
        return {"ok": True}
