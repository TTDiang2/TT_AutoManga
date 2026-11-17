"""In-process async job table for batch generation.

Jobs live in memory only (lost on restart); generation is idempotent so the
agent can simply re-submit. See design doc §D6.
"""
import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class JobItem:
    payload: Dict[str, Any]
    status: str = "pending"          # pending|running|done|error
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class Job:
    id: str
    total: int
    items: List[JobItem] = field(default_factory=list)
    status: str = "queued"           # queued|running|done
    created_at: str = ""
    concurrency: int = 1
    finished_at: Optional[float] = None   # time.time() when the last item ended


_jobs: Dict[str, Job] = {}
_semaphores: Dict[str, asyncio.Semaphore] = {}

FINISHED_JOB_TTL_S = 3600


def _prune_finished(now: Optional[float] = None) -> None:
    """Drop finished jobs older than an hour (their results hold whole
    generation records; the table would otherwise grow forever)."""
    now = time.time() if now is None else now
    for jid, job in list(_jobs.items()):
        if job.finished_at is not None and now - job.finished_at > FINISHED_JOB_TTL_S:
            _jobs.pop(jid, None)
            _semaphores.pop(jid, None)


def create_job(payloads: List[Dict[str, Any]], concurrency: int = 1) -> Job:
    _prune_finished()
    job = Job(id=uuid.uuid4().hex, total=len(payloads),
              items=[JobItem(payload=p) for p in payloads],
              created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              concurrency=max(1, min(4, concurrency)))
    _jobs[job.id] = job
    _semaphores[job.id] = asyncio.Semaphore(job.concurrency)
    return job


def job_snapshot(job_id: str) -> Optional[Dict[str, Any]]:
    job = _jobs.get(job_id)
    if not job:
        return None
    done = sum(1 for i in job.items if i.status in ("done", "error"))
    if done == job.total:
        job.status = "done"
    elif done > 0 or job.status == "queued":
        job.status = "running"
    return {"job_id": job.id, "status": job.status, "total": job.total,
            "done": done, "created_at": job.created_at,
            "items": [{"index": n, "panel_id": i.payload.get("panel_id"),
                       "status": i.status, "result": i.result, "error": i.error}
                      for n, i in enumerate(job.items)]}


async def run_job(job_id: str, worker: Callable[[Dict[str, Any]], Any]) -> None:
    job = _jobs.get(job_id)
    if job is None:
        return
    sem = _semaphores[job_id]
    job.status = "running"

    async def _one(item: JobItem):
        async with sem:
            item.status = "running"
            try:
                item.result = await worker(item.payload)
                item.status = "done"
            except Exception as e:
                item.error = str(e)
                item.status = "error"

    await asyncio.gather(*[_one(i) for i in job.items])
    job.status = "done"
    job.finished_at = time.time()
