"""Train LoRAs: datasets on this Mac, training on the remote trainer.

Datasets live in DATA_DIR/training/<slug>/ as img_NNN.png plus img_NNN.txt
holding only the trigger word (trigger-only captions, as for the sf_* LoRAs)
and a meta.json {slug, trigger, characterId}. Images come from uploads,
imported project panels, or a background "generate N" job that paints the
character's appearance (LoRA-free) over a pose/angle/expression/shot grid.

Training is one job at a time, persisted in DATA_DIR/training_job.json and
restart-proof like the Comics runs: push the dataset → render the ai-toolkit
config → launch detached on the trainer (backend/training.py) → each
GET /jobs/current polls the trainer's log (throttled) for the tqdm "N/steps"
progress → when run.py exits 0, pull <name>.safetensors into SwarmUI's
Models/Lora/<loraFolder>/, refresh SwarmUI's model list and set the
character's lora. A restart while the trainer runs loses nothing: the next
poll picks the job up from its pid and log. A restart during the short
push phase marks the job failed (start it again); one during "launching"
adopts the job from the pid the launcher wrote next to the log. Each job has
its own remote dir (automanga-training/<name>/<job id>/), and the job lock is
never held across ssh/scp: steps snapshot the job, talk to the trainer
unlocked, then re-check that the job is still current before merging.
"""
import asyncio
import binascii
import io
import json
import logging
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import training as tr
from ..core import config
from ..core.config import DATA_DIR, LoraConfig, atomic_write_json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/training", tags=["training"])

DATASETS_DIR = DATA_DIR / "training"
JOB_FILE = DATA_DIR / "training_job.json"
JOB_LOG = DATA_DIR / "training_job.log"          # local mirror of the trainer's log
SWARM_LORA_DIR = Path(os.environ.get("AUTOMANGA_SWARM_LORA_DIR",
                                     Path.home() / "SwarmUI" / "Models" / "Lora")).expanduser()
MIN_IMAGES = 15
MAX_DATASET_IMAGES = 200
MAX_UPLOAD_BYTES = 25 * 1024 * 1024   # per image
MAX_IMAGE_PIXELS = 40_000_000
DEFAULT_STEPS = 1500
DEFAULT_LORA_WEIGHT = 0.8
POLL_INTERVAL = 2.0          # seconds between trainer polls (GETs in between reuse the last one)
SEED_BASE, SEED_STEP = 1000, 7919
LOG_LINES = 400              # max log lines per response

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_]{1,62}$")
_TRIGGER_RE = re.compile(r"^[a-z][a-z0-9]{2,31}$")
_IMAGE_RE = re.compile(r"^img_(\d{3,5})\.png$")

_lock = threading.RLock()                 # job file read-modify-write only; never across ssh
_poll_lock = threading.Lock()             # one trainer poll at a time
_worker: Optional[threading.Thread] = None
_last_poll = 0.0
_gen: Dict[str, Dict[str, Any]] = {}            # slug → generation status
_gen_tasks: Dict[str, "asyncio.Task"] = {}


def _remote() -> tr.Remote:
    try:
        return tr.Remote(config.settings.training)
    except tr.RemoteError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------

def _dataset_dir(slug: str) -> Path:
    if not _SLUG_RE.fullmatch(slug or ""):
        raise HTTPException(status_code=400, detail="dataset names use a-z, 0-9, _ and - only")
    return DATASETS_DIR / slug


def _meta(slug: str) -> Dict[str, Any]:
    d = _dataset_dir(slug)
    try:
        return json.loads((d / "meta.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="dataset not found")


def _images(d: Path) -> List[Path]:
    return sorted((p for p in d.glob("img_*.png") if _IMAGE_RE.fullmatch(p.name)),
                  key=lambda p: int(_IMAGE_RE.fullmatch(p.name).group(1)))


def _next_index(d: Path) -> int:
    nums = [int(_IMAGE_RE.fullmatch(p.name).group(1)) for p in _images(d)]
    return (max(nums) + 1) if nums else 1


def _add_image(slug: str, data: bytes) -> str:
    """Store one image as PNG with its trigger caption; returns the file name.
    Blocking (decode + encode): call it from async code via asyncio.to_thread."""
    from PIL import Image
    meta = _meta(slug)
    d = _dataset_dir(slug)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"images are limited to {MAX_UPLOAD_BYTES >> 20} MB")
    if len(_images(d)) >= MAX_DATASET_IMAGES:
        raise HTTPException(status_code=400, detail=f"a dataset holds at most {MAX_DATASET_IMAGES} images")
    try:
        img = Image.open(io.BytesIO(data))
        if img.width * img.height > MAX_IMAGE_PIXELS:
            raise ValueError("too many pixels")
        img.load()
    except Exception:
        raise HTTPException(status_code=400, detail="not an image (or too large)")
    if img.mode not in ("RGB", "L"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        rgba = img.convert("RGBA")
        bg.paste(rgba, mask=rgba.split()[-1])
        img = bg
    with _lock:
        if len(_images(d)) >= MAX_DATASET_IMAGES:
            raise HTTPException(status_code=400, detail=f"a dataset holds at most {MAX_DATASET_IMAGES} images")
        n = _next_index(d)
        name = f"img_{n:03d}.png"
        img.convert("RGB").save(d / name, format="PNG")
        (d / f"img_{n:03d}.txt").write_text(meta["trigger"], encoding="utf-8")
    return name


def _dataset_view(slug: str) -> Dict[str, Any]:
    meta = _meta(slug)
    d = _dataset_dir(slug)
    images = [{"file": p.name, "url": f"/api/training/datasets/{slug}/image/{p.name}",
               "mtime": int(p.stat().st_mtime)} for p in _images(d)]
    return {**meta, "count": len(images), "images": images, "minImages": MIN_IMAGES,
            "generation": _gen.get(slug)}


@router.get("/settings")
async def training_settings():
    return config.settings.training.model_dump()


@router.get("/datasets")
async def list_datasets(character_id: Optional[str] = None):
    out = []
    if DATASETS_DIR.exists():
        for d in sorted(DATASETS_DIR.iterdir()):
            if not (d / "meta.json").exists() or not _SLUG_RE.fullmatch(d.name):
                continue
            try:
                meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
            except Exception:
                continue
            if character_id and meta.get("characterId") != character_id:
                continue
            out.append({**meta, "count": len(_images(d))})
    return {"datasets": out}


class CreateDatasetRequest(BaseModel):
    slug: str
    trigger: str
    characterId: Optional[str] = None


@router.post("/datasets")
async def create_dataset(req: CreateDatasetRequest):
    d = _dataset_dir(req.slug)
    if not _TRIGGER_RE.fullmatch(req.trigger or ""):
        raise HTTPException(status_code=400,
                            detail="the trigger is one lowercase word of 3-32 letters/digits (e.g. amnova)")
    if (d / "meta.json").exists():
        raise HTTPException(status_code=409, detail="a dataset with this name exists")
    d.mkdir(parents=True, exist_ok=True)
    atomic_write_json(d / "meta.json", {"slug": req.slug, "trigger": req.trigger,
                                        "characterId": req.characterId,
                                        "created": time.time()}, indent=2)
    return _dataset_view(req.slug)


@router.get("/datasets/{slug}")
async def get_dataset(slug: str):
    return _dataset_view(slug)


@router.get("/datasets/{slug}/image/{file}")
async def dataset_image(slug: str, file: str):
    d = _dataset_dir(slug)
    if not _IMAGE_RE.fullmatch(file):
        raise HTTPException(status_code=400, detail="not a dataset image")
    if not (d / file).exists():
        raise HTTPException(status_code=404, detail="image not found")
    return FileResponse(d / file, media_type="image/png")


@router.delete("/datasets/{slug}/image/{file}")
async def delete_image(slug: str, file: str):
    d = _dataset_dir(slug)
    _meta(slug)
    if not _IMAGE_RE.fullmatch(file):
        raise HTTPException(status_code=400, detail="not a dataset image")
    (d / file).unlink(missing_ok=True)
    (d / file.replace(".png", ".txt")).unlink(missing_ok=True)
    return _dataset_view(slug)


@router.post("/datasets/{slug}/upload")
async def upload_images(slug: str, files: List[UploadFile] = File(...)):
    _meta(slug)
    d = _dataset_dir(slug)
    if len(_images(d)) + len(files) > MAX_DATASET_IMAGES:
        raise HTTPException(status_code=400, detail=f"a dataset holds at most {MAX_DATASET_IMAGES} images")
    added = []
    for f in files:
        data = await f.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"{f.filename}: images are limited to "
                                                        f"{MAX_UPLOAD_BYTES >> 20} MB")
        added.append(await asyncio.to_thread(_add_image, slug, data))
    return {**_dataset_view(slug), "added": added}


class ImportPanelsRequest(BaseModel):
    projectId: str
    panelIds: List[str] = []      # empty: every panel with an image


def _decode_data_url(ref: str) -> bytes:
    import base64
    payload = ref.partition(",")[2]
    if len(payload) > MAX_UPLOAD_BYTES * 4 // 3 + 4:
        raise HTTPException(status_code=413, detail=f"images are limited to {MAX_UPLOAD_BYTES >> 20} MB")
    try:
        return base64.b64decode(payload)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="a panel image is not valid base64")


def _panel_bytes(ref: str) -> Optional[bytes]:
    if ref.startswith("data:"):
        return _decode_data_url(ref)
    if ref.startswith("/api/assets/file/"):
        from ..storage import asset_store as asset_store_mod
        p = asset_store_mod.asset_store.path_for(ref.rsplit("/", 1)[-1])
        if not p:
            return None
        if p.stat().st_size > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"images are limited to {MAX_UPLOAD_BYTES >> 20} MB")
        return p.read_bytes()
    return None


@router.post("/datasets/{slug}/import")
async def import_panels(slug: str, req: ImportPanelsRequest):
    _meta(slug)
    from ..storage.manager import InvalidProjectIdError, storage
    try:
        project = storage.load_project(req.projectId)
    except InvalidProjectIdError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    wanted = set(req.panelIds)
    added, skipped = [], 0
    for panel in project.get("panels", []):
        if wanted and panel.get("id") not in wanted:
            continue
        data = await asyncio.to_thread(_panel_bytes, panel.get("image") or "")
        if not data:
            skipped += 1
            continue
        added.append(await asyncio.to_thread(_add_image, slug, data))
    return {**_dataset_view(slug), "added": added, "skipped": skipped}


# -- generate --------------------------------------------------------------

POSES = ["standing, arms at sides", "arms crossed", "waving", "hands on hips", "sitting on a chair",
         "walking", "holding a coffee mug", "looking over shoulder"]
ANGLES = ["from front", "three-quarter view", "from side", "from slightly above", "from slightly below"]
EXPRESSIONS = ["neutral expression", "smiling", "laughing, closed eyes", "surprised, open mouth",
               "angry", "sad", "smirk", "blushing, shy smile"]
SHOTS = ["cowboy shot", "full body", "upper body", "portrait, close-up"]
GEN_NEGATIVE = ("multiple people, 2girls, 2boys, text, watermark, signature, lowres, bad anatomy, "
                "bad hands, extra fingers, child, loli, shota")


def grid_prompt(appearance: str, i: int) -> str:
    """The i-th dataset prompt: a different pose/angle/expression/shot mix for
    each i (strides chosen so neighbours differ in every slot)."""
    parts = [appearance.strip().rstrip(","), "solo", POSES[i % len(POSES)],
             ANGLES[(i * 2) % len(ANGLES)], EXPRESSIONS[(i * 3 + 1) % len(EXPRESSIONS)],
             SHOTS[(i + i // len(SHOTS)) % len(SHOTS)], "looking at viewer", "plain light grey background"]
    return ", ".join(p for p in parts if p)


def _character(character_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not character_id:
        return None
    from . import characters as chars_mod
    return next((c for c in chars_mod._load_characters() if c.get("id") == character_id), None)


class GenerateRequest(BaseModel):
    count: int = Field(default=24, ge=1, le=64)
    characterId: Optional[str] = None     # default: the dataset's character


async def _generate(slug: str, appearance: str, count: int, start: int) -> None:
    from ..core.swarmui_client import swarm_client
    st = _gen[slug]
    try:
        for k in range(count):
            i = start + k
            # a name-less LoraConfig: a non-empty list keeps generate_image
            # from falling back to settings.swarmui.currentLoras, and adds no tag
            res = await swarm_client.generate_image(
                prompt=grid_prompt(appearance, i), negative_prompt=GEN_NEGATIVE,
                width=832, height=1216, seed=SEED_BASE + i * SEED_STEP,
                loras=[LoraConfig(name="", weight=0)])
            if res.get("success") and res.get("image", "").startswith("data:"):
                try:
                    await asyncio.to_thread(
                        lambda: _add_image(slug, _decode_data_url(res["image"])))
                    st["done"] += 1
                except HTTPException as e:
                    st["failed"] += 1
                    st["errors"] = (st["errors"] + [str(e.detail)])[-5:]
            else:
                st["failed"] += 1
                st["errors"] = (st["errors"] + [str(res.get("error"))[:300]])[-5:]
    except asyncio.CancelledError:
        st["errors"] = (st["errors"] + ["cancelled"])[-5:]
        raise
    except Exception as e:   # noqa: BLE001 — reported in the status
        logger.exception("dataset generation failed")
        st["errors"] = (st["errors"] + [str(e)[:300]])[-5:]
    finally:
        st["running"] = False
        st["ended"] = time.time()


@router.post("/datasets/{slug}/generate")
async def generate_images(slug: str, req: GenerateRequest):
    meta = _meta(slug)
    if any(s.get("running") for s in _gen.values()):
        raise HTTPException(status_code=409, detail="a dataset is already being generated")
    char = _character(req.characterId or meta.get("characterId"))
    if char is None:
        raise HTTPException(status_code=400, detail="no character for this dataset")
    appearance = (char.get("appearance") or char.get("description") or "").strip()
    if not appearance:
        raise HTTPException(status_code=400, detail="the character has no appearance text")
    d = _dataset_dir(slug)
    start = meta.get("generated", 0)
    meta["generated"] = start + req.count     # the next batch continues the grid and seeds
    atomic_write_json(d / "meta.json", meta, indent=2)
    _gen[slug] = {"running": True, "total": req.count, "done": 0, "failed": 0, "errors": [],
                  "started": time.time(), "ended": None}
    _gen_tasks[slug] = asyncio.create_task(_generate(slug, appearance, req.count, start))
    return _dataset_view(slug)


@router.post("/datasets/{slug}/generate/stop")
async def stop_generation(slug: str):
    task = _gen_tasks.get(slug)
    if not task or task.done():
        raise HTTPException(status_code=409, detail="nothing is being generated")
    task.cancel()
    return {"stopped": True}


# ---------------------------------------------------------------------------
# Training jobs (one at a time, persisted, restart-proof)
# ---------------------------------------------------------------------------

def _load_job() -> Optional[Dict[str, Any]]:
    try:
        job = json.loads(JOB_FILE.read_text(encoding="utf-8"))
        return job if isinstance(job, dict) and job.get("id") else None
    except FileNotFoundError:
        return None
    except Exception as e:
        logger.warning("unreadable %s: %s", JOB_FILE, e)
        return None


def _save_job(job: Dict[str, Any]) -> None:
    atomic_write_json(JOB_FILE, job, indent=2)


def _event(job: Dict[str, Any], text: str) -> None:
    job.setdefault("events", []).append(f"{time.strftime('%H:%M:%S')} {text}")
    job["events"] = job["events"][-50:]


def _fail(job: Dict[str, Any], error: str) -> None:
    job["phase"] = "failed"
    job["error"] = error
    job["ended"] = time.time()
    _event(job, f"failed: {error}")
    _save_job(job)


_ACTIVE = ("pushing", "launching", "running", "finishing")


def _worker_alive() -> bool:
    return _worker is not None and _worker.is_alive()


def _spawn(target, job_id: str) -> None:
    global _worker
    _worker = threading.Thread(target=target, args=(job_id,), daemon=True,
                               name=f"training-{target.__name__}")
    _worker.start()


def _current(job_id: str) -> Optional[Dict[str, Any]]:
    job = _load_job()
    return job if job and job["id"] == job_id else None


class _Superseded(Exception):
    """The job was stopped or replaced while a worker step ran."""


def _check_current(job_id: str, phase: str) -> Dict[str, Any]:
    """The job, still current, in ``phase`` and not stopped; else _Superseded.
    Called before every remote step of a worker."""
    with _lock:
        job = _current(job_id)
    if not job or job["phase"] != phase or job.get("stopRequested"):
        raise _Superseded()
    return job


def _prepare_and_launch(job_id: str) -> None:
    """push → render config → launch (a worker thread). The job lock is only
    taken to read and merge job state, never across ssh/scp."""
    try:
        job = _check_current(job_id, "pushing")
        remote = tr.Remote(config.settings.training)
        found = remote.check()
        missing = [k for k, ok in found.items() if not ok]
        if missing:
            raise tr.RemoteError("missing on the trainer: " + ", ".join(
                {"toolkit": f"ai-toolkit run.py in {remote.toolkit_dir}",
                 "python": f"{remote.python} in {remote.toolkit_dir}",
                 "model": f"base model {remote.base_model}"}[k] for k in missing))
        job = _check_current(job_id, "pushing")
        if not job.get("resume") and remote.output_exists(job["name"]):
            raise tr.RemoteError(f"{remote.toolkit_dir}/output/{job['name']} has checkpoints on the trainer "
                                 "(ai-toolkit would resume it): pick another name, or start with resume")
        d = DATASETS_DIR / job["slug"]
        files = [f for p in _images(d) for f in (p, p.with_suffix(".txt")) if f.exists()]
        job = _check_current(job_id, "pushing")
        folder = remote.push_dataset(files, job["name"], job_id)
        jd = remote.job_dir(job["name"], job_id)
        trig = job["trigger"]
        prompts = [f"{trig}, {job.get('appearance') or 'solo'}, standing, smiling, cowboy shot, "
                   "plain light grey background",
                   f"{trig}, solo, sitting, laughing, upper body, night, city background"]
        cfg_text = tr.render_config(name=job["name"], trigger=trig, folder_path=folder,
                                    base_model=remote.base_model, steps=job["steps"], prompts=prompts,
                                    sampling=config.settings.training.sampling)
        cfg_path, log = f"{jd}/config.yaml", f"{jd}/train.log"
        job = _check_current(job_id, "pushing")
        remote.write_file(cfg_path, cfg_text)
        with _lock:
            job = _current(job_id)
            if not job or job["phase"] != "pushing" or job.get("stopRequested"):
                return       # stopped meanwhile
            job.update(phase="launching", remote={"jobDir": jd, "config": cfg_path, "log": log,
                                                  "pidfile": tr.Remote.pidfile(log),
                                                  "output": remote.output_file(job["name"])})
            _event(job, f"pushed {len(files) // 2} images to {folder}; config {cfg_path}")
            _save_job(job)
        pid = remote.launch(cfg_path, log)
        with _lock:
            job = _current(job_id)
            stopped = not job or bool(job.get("stopRequested"))
            if job:
                job["pid"] = pid
                _event(job, f"launched on {remote.host} (pid {pid})")
                if not stopped:
                    job["phase"] = "running"
                _save_job(job)
        if stopped:   # stopped (or replaced) while launching: don't orphan the GPU process
            remote.stop(pid, log)
            with _lock:
                job = _current(job_id)
                if job:
                    _event(job, "stopped right after launch")
                    _save_job(job)
    except _Superseded:
        return
    except Exception as e:   # noqa: BLE001
        logger.exception("training launch failed")
        with _lock:
            job = _current(job_id)
            if job and job["phase"] in ("pushing", "launching"):
                _fail(job, str(e))


def _adopt(job_id: str) -> None:
    """After a restart while "launching": the launcher may have started the
    trainer. Read its pidfile and adopt the process (or stop it, if a stop
    was requested), else fail the job. Remote I/O outside the lock."""
    with _lock:
        job = _current(job_id)
        if not job or job.get("pid") or job.get("adoptChecked"):
            return
        log = (job.get("remote") or {}).get("log")
    pid = err = None
    if log:
        try:
            pid = tr.Remote(config.settings.training).read_pidfile(log)
        except tr.RemoteError as e:
            err = str(e)
    if err:          # trainer unreachable: try again on the next poll
        with _lock:
            job = _current(job_id)
            if job:
                job["pollError"] = err
                _save_job(job)
        return
    stop = False
    with _lock:
        job = _current(job_id)
        if not job or job.get("pid") or job.get("adoptChecked"):
            return
        job["adoptChecked"] = True
        if pid is None:
            if job["phase"] == "launching":
                _fail(job, "interrupted by a server restart before the trainer started; start again")
            else:
                _save_job(job)
            return
        job["pid"] = pid
        if job.get("stopRequested"):
            stop = True
            _event(job, f"found the trainer (pid {pid}) after a restart; stopping it")
        else:
            job["phase"] = "running"
            _event(job, f"adopted the trainer (pid {pid}) after a server restart")
        _save_job(job)
    if stop:
        try:
            tr.Remote(config.settings.training).stop(pid, log)
        except tr.RemoteError as e:
            logger.warning("could not stop adopted trainer pid %s: %s", pid, e)


def _refresh_swarmui() -> None:
    base = config.settings.swarmui.address.strip().rstrip("/")
    base = base if base.startswith("http") else f"http://{base}"
    with httpx.Client(timeout=120.0, follow_redirects=True) as c:
        sid = c.post(f"{base}/API/GetNewSession", json={}).json().get("session_id", "")
        r = c.post(f"{base}/API/TriggerRefresh", json={"session_id": sid, "strong": True})
        r.raise_for_status()


def _set_character_lora(character_id: str, lora: Dict[str, Any]) -> bool:
    from . import characters as chars_mod
    value = chars_mod.CharacterLora.model_validate(lora).model_dump()
    with chars_mod.CHARACTERS_LOCK:
        chars = chars_mod._load_characters()
        for c in chars:
            if c.get("id") == character_id:
                c["lora"] = value
                c["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                chars_mod._save_characters(chars)
                return True
    return False


def _finish(job_id: str) -> None:
    """pull the LoRA → refresh SwarmUI → set the character's lora (a worker
    thread). Never overwrites an existing LoRA file: the name gets _2, _3…"""
    try:
        job = _check_current(job_id, "finishing")
        remote = tr.Remote(config.settings.training)
        folder = config.settings.training.loraFolder.strip("/") or "Comics"
        prev = Path(job["loraFile"]) if job.get("loraFile") else None
        if prev is not None and prev.exists():
            local = prev                  # a retried collect: this job's own file
        else:
            local = tr.free_lora_path(SWARM_LORA_DIR / folder, job["name"])
            remote.pull(job["remote"]["output"], local, overwrite=False)
        lora = {"name": f"{folder}/{local.stem}", "weight": DEFAULT_LORA_WEIGHT,
                "trigger": job["trigger"]}
        with _lock:
            job = _current(job_id)
            if not job:
                return
            job.update(loraFile=str(local), lora=lora)
            note = f" (as {local.stem}: {job['name']} existed)" if local.stem != job["name"] else ""
            _event(job, f"pulled {local} ({local.stat().st_size // 1024} KB){note}")
            _save_job(job)
        _check_current(job_id, "finishing")
        try:
            _refresh_swarmui()
            msg = "SwarmUI model list refreshed"
        except Exception as e:   # noqa: BLE001 — the file is in place; a manual refresh will do
            msg = f"SwarmUI refresh failed ({e}); refresh it by hand"
        char_msg = None
        if job.get("characterId"):
            ok = _set_character_lora(job["characterId"], lora)
            char_msg = "character lora set" if ok else "character not found; lora not set"
        with _lock:
            job = _current(job_id)
            if not job:
                return
            _event(job, msg)
            if char_msg:
                _event(job, char_msg)
            job.update(phase="done", ended=time.time())
            job.pop("collectable", None)
            _save_job(job)
    except _Superseded:
        return
    except Exception as e:   # noqa: BLE001
        logger.exception("training finish failed")
        with _lock:
            job = _current(job_id)
            if job and job["phase"] == "finishing":
                job["collectable"] = True      # POST /jobs/current/collect retries
                _fail(job, f"could not collect the LoRA: {e}")


def _poll(job_id: str) -> None:
    """One trainer poll: append new log bytes to the mirror, update step and
    phase. Throttled to POLL_INTERVAL; one at a time; the ssh call runs
    without the job lock and its result is merged only into the same job."""
    global _last_poll
    if not _poll_lock.acquire(blocking=False):
        return                          # another request is polling right now
    try:
        if time.time() - _last_poll < POLL_INTERVAL:
            return
        _last_poll = time.time()
        with _lock:
            job = _current(job_id)
            if not job or job["phase"] != "running":
                return
            pid, log = job["pid"], job["remote"]["log"]
        offset = JOB_LOG.stat().st_size if JOB_LOG.exists() else 0
        try:
            code, alive, data = tr.Remote(config.settings.training).poll(pid, log, offset)
        except tr.RemoteError as e:
            with _lock:
                job = _current(job_id)
                if job and job["phase"] == "running":
                    job["pollError"] = str(e)
                    _save_job(job)
            return
        with _lock:
            job = _current(job_id)
            if not job or job["phase"] != "running":
                return
            job.pop("pollError", None)
            if data:
                with open(JOB_LOG, "ab") as f:
                    f.write(data)
            raw = JOB_LOG.read_bytes().decode("utf-8", errors="replace") if JOB_LOG.exists() else ""
            step = tr.parse_progress(raw[-200_000:], job["steps"])
            if step is not None:
                job["step"] = step
            if code is not None and not job.get("stopRequested"):
                if code == 0:
                    job["step"] = job["steps"]
                    job["phase"] = "finishing"
                    _event(job, "training finished")
                else:
                    _fail(job, f"trainer exited with code {code} (see the log)")
                    return
            elif code is not None or (not alive and job.get("stopRequested")):
                job.update(phase="stopped", ended=time.time())
                _event(job, "stopped")
            elif not alive:
                _fail(job, "the trainer process is gone without an exit code (killed or rebooted)")
                return
            _save_job(job)
    finally:
        _poll_lock.release()


def _advance() -> Optional[Dict[str, Any]]:
    """Bring the persisted job up to date (also the restart pickup). Blocking
    (ssh): from async code call it via asyncio.to_thread."""
    with _lock:
        job = _load_job()
        if not job:
            return None
        phase, job_id = job["phase"], job["id"]
        worker = _worker_alive()
        if phase == "pushing" and not worker:
            _fail(job, "interrupted by a server restart before the trainer started; start again")
            return job
    adopt = not worker and not job.get("pid") and not job.get("adoptChecked") \
        and (job.get("remote") or {}).get("log") \
        and (phase == "launching" or (phase == "stopped" and job.get("stopRequested")))
    if adopt:
        _adopt(job_id)
    elif phase == "running":
        _poll(job_id)
    with _lock:
        job = _load_job()
        if job and job["phase"] == "finishing" and not _worker_alive():
            _spawn(_finish, job["id"])
        return job


def _snapshot(job: Dict[str, Any], since: int = 0) -> Dict[str, Any]:
    raw = JOB_LOG.read_bytes().decode("utf-8", errors="replace") if JOB_LOG.exists() else ""
    lines, partial = tr.log_lines(raw)
    total = len(lines)
    since = max(0, min(since, total))
    if total - since > LOG_LINES:
        since = total - LOG_LINES
    view = {k: v for k, v in job.items() if k not in ("appearance",)}
    view.update(lines=lines[since:], next=total, partial=partial,
                running=job["phase"] in _ACTIVE)
    return view


class StartJobRequest(BaseModel):
    slug: str
    name: Optional[str] = None         # LoRA file name (default: the slug, - → _)
    characterId: Optional[str] = None  # default: the dataset's character
    steps: int = Field(default=DEFAULT_STEPS, ge=10, le=10000)
    resume: bool = False               # allow an existing output/<name> on the trainer


@router.post("/jobs")
async def start_job(req: StartJobRequest):
    meta = _meta(req.slug)
    name = req.name or req.slug.replace("-", "_")
    if not _NAME_RE.fullmatch(name):
        raise HTTPException(status_code=400, detail="LoRA names use a-z, 0-9 and _ (2-63 chars)")
    count = len(_images(_dataset_dir(req.slug)))
    if count < MIN_IMAGES:
        raise HTTPException(status_code=400, detail=f"a dataset needs at least {MIN_IMAGES} images ({count} now)")
    if (_gen.get(req.slug) or {}).get("running"):
        raise HTTPException(status_code=409, detail="images are still being generated for this dataset")
    _remote()   # settings sanity (os, host) before anything is persisted
    char_id = req.characterId or meta.get("characterId")
    char = _character(char_id)
    await asyncio.to_thread(_advance)      # ssh: off the event loop, outside the lock
    with _lock:
        busy = _load_job()
        if busy and busy["phase"] in _ACTIVE:
            raise HTTPException(status_code=409, detail=f"already training {busy['name']}")
        JOB_LOG.unlink(missing_ok=True)
        job = {"id": uuid.uuid4().hex, "name": name, "slug": req.slug, "trigger": meta["trigger"],
               "characterId": char_id if char else None, "steps": req.steps, "resume": req.resume,
               "appearance": tr.clean_text((char or {}).get("appearance") or ""),
               "images": count, "phase": "pushing", "pid": None, "step": 0,
               "started": time.time(), "ended": None, "error": None, "events": []}
        _event(job, f"training {name} on {count} images, {req.steps} steps")
        _save_job(job)
        _spawn(_prepare_and_launch, job["id"])
    return {"job": _snapshot(job)}


@router.get("/jobs/current")
def current_job(since: int = 0):
    """The current (or last) job with the log lines from ``since``. A plain
    def: the trainer poll is a blocking ssh call, FastAPI runs it in a thread."""
    job = _advance()
    return {"job": _snapshot(job, since) if job else None}


@router.post("/jobs/current/stop")
def stop_job():
    with _lock:
        job = _load_job()
        if not job or job["phase"] not in ("pushing", "launching", "running"):
            raise HTTPException(status_code=409, detail="nothing is training")
        job["stopRequested"] = True
        running = job["phase"] == "running"
        if not running:
            # not launched yet: the launch worker sees the flag (or stops right after launching)
            job.update(phase="stopped", ended=time.time())
            _event(job, "stopped before launch")
        _save_job(job)
        job_id, pid, log = job["id"], job.get("pid"), (job.get("remote") or {}).get("log")
    if running:
        try:   # ssh outside the lock
            tr.Remote(config.settings.training).stop(pid, log)
        except tr.RemoteError as e:
            with _lock:
                job = _current(job_id)
                if job and job["phase"] == "running":
                    job.pop("stopRequested", None)
                    _save_job(job)
            raise HTTPException(status_code=502, detail=f"could not stop the trainer: {e}")
        with _lock:
            job = _current(job_id) or job
            _event(job, "stop sent")
            _save_job(job)
    return {"job": _snapshot(job)}


@router.post("/jobs/current/collect")
def collect_job():
    """Retry the finish (pull → SwarmUI refresh → character lora) of a job
    whose training succeeded but whose collection failed."""
    with _lock:
        job = _load_job()
        if not job or job["phase"] != "failed" or not job.get("collectable"):
            raise HTTPException(status_code=409, detail="no finished training to collect")
        if _worker_alive():
            raise HTTPException(status_code=409, detail="the previous step is still running")
        job.update(phase="finishing", error=None, ended=None)
        _event(job, "collecting again")
        _save_job(job)
        _spawn(_finish, job["id"])
    return {"job": _snapshot(job)}
