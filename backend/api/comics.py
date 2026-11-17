"""Comics: run the .comic script converter (automanga.js in the Comics repo)
from the web UI.

The Comics repo (COMICS_DIR, default ~/Projects/Comics) holds the scripts in
scripts/*.comic and the converter; its output lands in out/<name>/. This
router lists and edits the scripts, runs one conversion at a time (SwarmUI
paints one panel at a time anyway) detached from the server, serves its log
incrementally, and serves the page
PNGs comic.js renders. Script names are restricted to [a-z0-9_-] so no
request can reach outside the repo.
"""
import json
import logging
import os
import re
import shlex
import shutil
import signal
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..core.config import DATA_DIR, atomic_write_json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/comics", tags=["comics"])

COMICS_DIR = Path(os.environ.get("COMICS_DIR", Path.home() / "Projects" / "Comics")).expanduser()
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,80}$")
_PAGE_FILE_RE = re.compile(r"^(page|draft)_\d{2}\.png$")
_MODES = {"paint": [], "no-paint": ["--no-paint"], "dry-run": ["--dry-run"]}
_LOG_LIMIT = 5000           # max lines returned per poll


def _scripts_dir() -> Path:
    return COMICS_DIR / "scripts"


def _script_path(name: str) -> Path:
    if not _NAME_RE.fullmatch(name or ""):
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
    running = _running_run()
    if running and running["script"] == name:
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
    if not _PAGE_FILE_RE.fullmatch(file):
        raise HTTPException(status_code=400, detail="not a page file")
    path = _out_dir(name) / file
    if not path.exists():
        raise HTTPException(status_code=404, detail="page not rendered")
    return FileResponse(path, media_type="image/png")


# ---------------------------------------------------------------------------
# Runs (one at a time, detached, restart-proof)
#
# The converter runs in its own session (start_new_session) under /bin/sh,
# which appends all output to out/<name>/automanga.run.log and writes the
# exit code to automanga.run.log.exit when node ends. Nothing streams
# through a pipe (no line-length limit, no dependency on this process), so
# restarting the server neither kills the conversion nor loses its log.
# The current run is persisted to DATA_DIR/comics_run.json and picked up
# again on start; its status is derived from the pid and the .exit file.
# ---------------------------------------------------------------------------

RUN_FILE = DATA_DIR / "comics_run.json"
_LINE_LIMIT = 4000          # chars per returned line (one giant line stays usable)
_procs: Dict[int, subprocess.Popen] = {}   # children of this server, for reaping
_line_index: Dict[str, "_LogIndex"] = {}   # log path → newline offsets
_verified: Dict[tuple, bool] = {}          # (pid, run id) → pid is that run


class _LogIndex:
    """Byte offsets of line starts in a growing log, extended incrementally
    so a poll only reads what was appended since the last one."""

    def __init__(self, path: Path):
        self.path = path
        self.starts: List[int] = [0]
        self.scanned = 0
        self.ident = None

    def refresh(self) -> int:
        try:
            st = self.path.stat()
        except OSError:
            return 0
        if self.ident != (st.st_ino, st.st_dev) or st.st_size < self.scanned:
            # replaced or truncated (a new run): start over
            self.starts, self.scanned = [0], 0
            self.ident = (st.st_ino, st.st_dev)
        if st.st_size > self.scanned:
            with open(self.path, "rb") as f:
                f.seek(self.scanned)
                while True:
                    chunk = f.read(1 << 20)
                    if not chunk:
                        break
                    base = self.scanned
                    i = chunk.find(b"\n")
                    while i != -1:
                        self.starts.append(base + i + 1)
                        i = chunk.find(b"\n", i + 1)
                    self.scanned += len(chunk)
        return self.scanned

    def lines(self, since: int, include_partial: bool):
        """(lines[since:], total) — complete lines, plus the unterminated
        tail once the run has ended."""
        size = self.refresh()
        complete = len(self.starts) - 1
        has_tail = include_partial and self.starts[-1] < size
        total = complete + (1 if has_tail else 0)
        since = max(0, since)
        if total - since > _LOG_LIMIT:
            since = total - _LOG_LIMIT   # far behind: send the newest lines only
        if since >= total:
            return [], total
        begin = self.starts[since]
        end = size if has_tail else self.starts[complete]
        with open(self.path, "rb") as f:
            f.seek(begin)
            blob = f.read(end - begin)
        out = blob.decode("utf-8", errors="replace").split("\n")
        if not has_tail:
            out = out[:-1]   # split leaves "" after the final newline
        return [l.rstrip("\r")[:_LINE_LIMIT] for l in out], total


def _log_path(script: str) -> Path:
    return _out_dir(script) / "automanga.run.log"


def _load_run() -> Optional[Dict[str, Any]]:
    try:
        run = json.loads(RUN_FILE.read_text(encoding="utf-8"))
        return run if isinstance(run, dict) and run.get("pid") else None
    except FileNotFoundError:
        return None
    except Exception as e:
        logger.warning("unreadable %s: %s", RUN_FILE, e)
        return None


def _save_run(run: Dict[str, Any]) -> None:
    atomic_write_json(RUN_FILE, run, indent=2)


def _is_our_process(run: Dict[str, Any]) -> bool:
    """After a restart (or reboot) the persisted pid may belong to someone
    else: trust it only if its command line is our /bin/sh, which names
    the run's log file. Checked once per run."""
    key = (int(run["pid"]), run["id"])
    if key not in _verified:
        try:
            out = subprocess.run(["ps", "-o", "command=", "-p", str(key[0])],
                                 capture_output=True, text=True, timeout=5).stdout
            _verified[key] = run["log"] in out
        except Exception:
            _verified[key] = True   # can't tell: don't declare a live run dead
    return _verified[key]


def _pid_alive(run: Dict[str, Any]) -> bool:
    pid = int(run["pid"])
    proc = _procs.get(pid)
    if proc is not None:
        # our own child: poll() reaps it (a zombie still answers kill(0))
        if proc.poll() is None:
            return True
        _procs.pop(pid, None)
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return _is_our_process(run)


def _exit_code(run: Dict[str, Any]) -> Optional[int]:
    try:
        return int(Path(run["log"] + ".exit").read_text().strip())
    except (OSError, ValueError):
        return None


def _status(run: Dict[str, Any]):
    """(status, exit_code, ended) of a persisted run."""
    code = _exit_code(run)
    if run.get("stopped"):
        return "stopped", code, run.get("ended")
    if code is not None:
        try:
            ended = Path(run["log"] + ".exit").stat().st_mtime
        except OSError:
            ended = None
        return ("done" if code == 0 else "failed"), code, ended
    if _pid_alive(run):
        return "running", None, None
    # gone without an exit code: killed from outside (reboot, kill -9)
    return "failed", None, run.get("ended")


def _snapshot(run: Dict[str, Any], since: int = 0) -> Dict[str, Any]:
    status, code, ended = _status(run)
    log = Path(run["log"])
    idx = _line_index.get(run["log"])
    if idx is None:
        idx = _line_index[run["log"]] = _LogIndex(log)
    lines, total = idx.lines(since, include_partial=status != "running")
    summary = None
    try:
        summary = _summary(_script_path(run["script"]))
    except Exception:
        pass
    return {"id": run["id"], "script": run["script"], "mode": run["mode"],
            "face": run["face"], "status": status, "exit_code": code,
            "started": run["started"], "ended": ended,
            "lines": lines, "next": total,
            "project_id": summary and summary["project_id"]}


def _running_run() -> Optional[Dict[str, Any]]:
    run = _load_run()
    return run if run and _status(run)[0] == "running" else None


class StartRunRequest(BaseModel):
    script: str
    mode: str = "paint"      # paint | no-paint | dry-run
    face: bool = False


@router.post("/runs")
async def start_run(req: StartRunRequest):
    path = _script_path(req.script)
    if not path.exists():
        raise HTTPException(status_code=404, detail="script not found")
    if req.mode not in _MODES:
        raise HTTPException(status_code=400, detail=f"mode must be one of {sorted(_MODES)}")
    busy = _running_run()
    if busy:
        raise HTTPException(status_code=409, detail=f"already converting {busy['script']}")
    node = _node()
    args = [node, str(COMICS_DIR / "automanga.js"), str(path), *_MODES[req.mode]]
    if req.face:
        args.append("--face")

    log = _log_path(req.script)
    log.parent.mkdir(parents=True, exist_ok=True)
    exit_file = Path(str(log) + ".exit")
    exit_file.unlink(missing_ok=True)
    # truncate: one log per run
    log.write_text("$ node automanga.js " + " ".join([f"scripts/{path.name}", *args[3:]]) + "\n",
                   encoding="utf-8")
    q = shlex.quote
    # exit code via tmp + mv so a poll never reads a half-written file
    shell = (" ".join(q(a) for a in args) + f" >> {q(str(log))} 2>&1; "
             f"echo $? > {q(str(exit_file) + '.tmp')}; "
             f"mv -f {q(str(exit_file) + '.tmp')} {q(str(exit_file))}")

    env = dict(os.environ)
    env["PATH"] = os.pathsep.join([str(Path(node).parent), env.get("PATH", "")])
    env.setdefault("AUTOMANGA_URL", f"http://127.0.0.1:{os.environ.get('AUTOMANGA_PORT', '5180')}")
    try:
        proc = subprocess.Popen(["/bin/sh", "-c", shell], cwd=str(COMICS_DIR), env=env,
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError as e:
        logger.exception("comic run failed to start")
        raise HTTPException(status_code=500, detail=f"could not start the converter: {e}")
    _procs[proc.pid] = proc
    run = {"id": uuid.uuid4().hex, "script": req.script, "mode": req.mode,
           "face": req.face, "pid": proc.pid, "log": str(log), "started": time.time()}
    _save_run(run)
    return _snapshot(run)


@router.get("/runs/current")
async def current_run(since: int = 0):
    run = _load_run()
    return {"run": _snapshot(run, since) if run else None}


@router.post("/runs/current/stop")
async def stop_run():
    run = _running_run()
    if not run:
        raise HTTPException(status_code=409, detail="nothing is running")
    run["stopped"] = True
    run["ended"] = time.time()
    _save_run(run)
    try:
        with open(run["log"], "a", encoding="utf-8") as f:
            f.write("stopped\n")
    except OSError:
        pass
    # the converter runs comic.js as a child; the whole session is one
    # process group (start_new_session), so one signal stops all of it
    try:
        os.killpg(int(run["pid"]), signal.SIGTERM)
    except ProcessLookupError:
        pass
    return {"run": _snapshot(run)}
