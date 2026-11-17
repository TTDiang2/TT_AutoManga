"""Comics: run the .comic script converter (automanga.js in the Comics repo)
from the web UI.

The Comics repo (COMICS_DIR, default ~/Projects/Comics) holds the scripts in
scripts/*.comic and the converter; its output lands in out/<name>/. This
router lists and edits the scripts, runs one conversion at a time (SwarmUI
paints one panel at a time anyway) and streams its log, and serves the page
PNGs comic.js renders. Script names are restricted to [a-z0-9_-] so no
request can reach outside the repo.
"""
import asyncio
import json
import logging
import os
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/comics", tags=["comics"])

COMICS_DIR = Path(os.environ.get("COMICS_DIR", Path.home() / "Projects" / "Comics")).expanduser()
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,80}$")
_PAGE_FILE_RE = re.compile(r"^(page|draft)_\d{2}\.png$")
_MODES = {"paint": [], "no-paint": ["--no-paint"], "dry-run": ["--dry-run"]}
_LOG_LIMIT = 5000


def _scripts_dir() -> Path:
    return COMICS_DIR / "scripts"


def _script_path(name: str) -> Path:
    if not _NAME_RE.match(name or ""):
        raise HTTPException(status_code=400, detail="script names use letters, digits, _ and - only")
    return _scripts_dir() / f"{name}.comic"


def _out_dir(name: str) -> Path:
    return COMICS_DIR / "out" / name


def _node() -> str:
    # the launch agent's PATH has no Homebrew: look there too
    found = shutil.which("node") or next(
        (p for p in ("/opt/homebrew/bin/node", "/usr/local/bin/node") if os.path.exists(p)), None)
    if not found:
        raise HTTPException(status_code=500, detail="node is not installed (needed to run the converter)")
    return found


def _summary(path: Path) -> Dict[str, Any]:
    """Title and counts from a script, without the converter (cheap enough for a listing)."""
    name = path.stem
    title, subtitle, pages, panels = None, None, 0, 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        t = line.strip()
        if t.startswith("//"):
            continue
        if title is None and t.lower().startswith("title:"):
            title = t.split(":", 1)[1].strip()
        if subtitle is None and t.lower().startswith("subtitle:"):
            subtitle = t.split(":", 1)[1].strip()
        if re.match(r"^PAGE\b", t):
            pages += 1
        elif re.match(r"^PANEL\b", t):
            panels += 1
    out = _out_dir(name)
    painted = len(list((out / "panels").glob("p??-??.png"))) if (out / "panels").exists() else 0
    project_id = None
    try:
        project_id = json.loads((out / "automanga.json").read_text()).get("project_id")
    except Exception:
        pass
    return {"name": name, "title": title or name, "subtitle": subtitle, "pages": pages, "panels": panels,
            "painted": painted, "project_id": project_id,
            "updated": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(path.stat().st_mtime))}


# ---------------------------------------------------------------------------
# Scripts
# ---------------------------------------------------------------------------

@router.get("/scripts")
async def list_scripts():
    if not (COMICS_DIR / "automanga.js").exists():
        raise HTTPException(status_code=404,
                            detail=f"no Comics repo with automanga.js at {COMICS_DIR} (set COMICS_DIR)")
    scripts = [_summary(p) for p in sorted(_scripts_dir().glob("*.comic"))]
    return {"comics_dir": str(COMICS_DIR), "scripts": scripts}


@router.get("/scripts/{name}")
async def get_script(name: str):
    path = _script_path(name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="script not found")
    return {**_summary(path), "text": path.read_text(encoding="utf-8")}


class SaveScriptRequest(BaseModel):
    text: str


@router.put("/scripts/{name}")
async def save_script(name: str, req: SaveScriptRequest):
    path = _script_path(name)
    if _current and _current.status == "running" and _current.script == name:
        raise HTTPException(status_code=409, detail="this script is being converted; save when the run ends")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".comic.tmp")
    tmp.write_text(req.text, encoding="utf-8")
    tmp.replace(path)
    return _summary(path)


@router.get("/scripts/{name}/pages")
async def list_pages(name: str):
    """The page PNGs comic.js rendered last: the painted pages or the dry-run drafts, whichever is newer."""
    _script_path(name)
    out = _out_dir(name)
    if not out.exists():
        return {"pages": []}
    sets = [sorted(out.glob(f"{kind}_*.png")) for kind in ("page", "draft")]
    sets = [s for s in sets if s]
    newest = max(sets, key=lambda s: max(p.stat().st_mtime for p in s)) if sets else []
    pages = [p.name for p in newest]
    return {"pages": [{"file": f, "url": f"/api/comics/scripts/{name}/file/{f}",
                       "mtime": int((out / f).stat().st_mtime)} for f in pages]}


@router.get("/scripts/{name}/file/{file}")
async def page_file(name: str, file: str):
    _script_path(name)
    if not _PAGE_FILE_RE.match(file):
        raise HTTPException(status_code=400, detail="not a page file")
    path = _out_dir(name) / file
    if not path.exists():
        raise HTTPException(status_code=404, detail="page not rendered")
    return FileResponse(path, media_type="image/png")


# ---------------------------------------------------------------------------
# Runs (one at a time)
# ---------------------------------------------------------------------------

class Run:
    def __init__(self, script: str, mode: str, face: bool):
        self.id = uuid.uuid4().hex
        self.script, self.mode, self.face = script, mode, face
        self.status = "running"            # running | done | failed | stopped
        self.exit_code: Optional[int] = None
        self.lines: List[str] = []
        self.started = time.time()
        self.ended: Optional[float] = None
        self.proc: Optional[asyncio.subprocess.Process] = None

    def snapshot(self, since: int = 0) -> Dict[str, Any]:
        summary = None
        try:
            summary = _summary(_script_path(self.script))
        except Exception:
            pass
        return {"id": self.id, "script": self.script, "mode": self.mode, "face": self.face,
                "status": self.status, "exit_code": self.exit_code,
                "started": self.started, "ended": self.ended,
                "lines": self.lines[since:], "next": len(self.lines),
                "project_id": summary and summary["project_id"]}


_current: Optional[Run] = None
_tasks: set = set()


async def _execute(run: Run, cmd: List[str]) -> None:
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join([str(Path(cmd[0]).parent), env.get("PATH", "")])
    env.setdefault("AUTOMANGA_URL", f"http://127.0.0.1:{os.environ.get('AUTOMANGA_PORT', '5180')}")
    try:
        run.proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=str(COMICS_DIR), env=env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        async for raw in run.proc.stdout:
            run.lines.append(raw.decode("utf-8", errors="replace").rstrip())
            if len(run.lines) > _LOG_LIMIT:
                del run.lines[: len(run.lines) - _LOG_LIMIT]
        run.exit_code = await run.proc.wait()
        if run.status == "running":
            run.status = "done" if run.exit_code == 0 else "failed"
    except Exception as e:
        logger.exception("comic run failed")
        run.lines.append(f"error: {e}")
        run.status = "failed"
    finally:
        run.ended = time.time()


class StartRunRequest(BaseModel):
    script: str
    mode: str = "paint"      # paint | no-paint | dry-run
    face: bool = False


@router.post("/runs")
async def start_run(req: StartRunRequest):
    global _current
    path = _script_path(req.script)
    if not path.exists():
        raise HTTPException(status_code=404, detail="script not found")
    if req.mode not in _MODES:
        raise HTTPException(status_code=400, detail=f"mode must be one of {sorted(_MODES)}")
    if _current and _current.status == "running":
        raise HTTPException(status_code=409, detail=f"already converting {_current.script}")
    cmd = [_node(), str(COMICS_DIR / "automanga.js"), str(path), *_MODES[req.mode]]
    if req.face:
        cmd.append("--face")
    run = Run(req.script, req.mode, req.face)
    run.lines.append("$ node automanga.js " + " ".join([f"scripts/{path.name}", *cmd[3:]]))
    _current = run
    task = asyncio.create_task(_execute(run, cmd))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return run.snapshot()


@router.get("/runs/current")
async def current_run(since: int = 0):
    return {"run": _current.snapshot(since) if _current else None}


@router.post("/runs/current/stop")
async def stop_run():
    if not _current or _current.status != "running" or not _current.proc:
        raise HTTPException(status_code=409, detail="nothing is running")
    _current.status = "stopped"
    _current.lines.append("stopped")
    # the converter runs comic.js as a child: stop that first (once the parent
    # is gone the child is re-parented and -P no longer finds it)
    proc = await asyncio.create_subprocess_exec("pkill", "-TERM", "-P", str(_current.proc.pid))
    await proc.wait()
    try:
        _current.proc.terminate()
    except ProcessLookupError:
        pass
    return {"run": _current.snapshot()}
