"""LoRA training on a remote trainer (the Razer) with ai-toolkit.

``Remote`` drives the trainer over ssh/scp (BatchMode, so a missing key fails
fast instead of prompting). A job is detached on the trainer: launched under
setsid + nohup, it survives both the ssh connection and a restart of this
server. The trainer's shell writes the exit code to ``<log>.exit`` when
run.py ends, so status is derived from the pid (checked against its command
line, which names the log) and that file, the same scheme as the Comics
runs in backend/api/comics.py.

Only Linux trainers are implemented; ``os`` is kept in the settings so a
Windows trainer (Start-Process -PassThru) can be added without a migration.

The config is rendered from training_templates/sdxl_lora.yaml.tmpl, the
recipe of the sf_* LoRAs. Values are substituted as JSON scalars, which are
valid YAML, so no YAML library is needed.
"""
import json
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

TEMPLATE = Path(__file__).parent / "training_templates" / "sdxl_lora.yaml.tmpl"
SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
SUPPORTED_OS = ("linux",)
READ_LIMIT = 1 << 20          # max log bytes fetched per poll
_STAT_RE = re.compile(r"^AMSTAT (\S+) ([01])$")
_HOMES: Dict[str, str] = {}   # host → $HOME, read once per process


class RemoteError(RuntimeError):
    """The trainer could not be reached or a remote step failed."""


def _q(s: str) -> str:
    return shlex.quote(str(s))


# ---------------------------------------------------------------------------
# Config rendering and log parsing (pure functions, unit-tested directly)
# ---------------------------------------------------------------------------

_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]+")


def clean_text(text: str) -> str:
    """Prompt text without control characters (newlines, tabs, escapes from
    the character's appearance field become a single space)."""
    return re.sub(r" {2,}", " ", _CONTROL_RE.sub(" ", str(text or ""))).strip()


def render_config(*, name: str, trigger: str, folder_path: str, base_model: str,
                  steps: int, prompts: List[str], sampling: bool = False) -> str:
    prompts = [clean_text(p) for p in prompts]
    values = {
        "name": name, "trigger": trigger, "folder_path": folder_path,
        "base_model": base_model, "steps": int(steps),
        "disable_sampling": not sampling,
        "prompt_1": prompts[0], "prompt_2": prompts[1] if len(prompts) > 1 else prompts[0],
    }
    text = TEMPLATE.read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", json.dumps(value, ensure_ascii=False))
    left = re.findall(r"\{\{\w+\}\}", text)
    if left:
        raise ValueError(f"template placeholders not filled: {left}")
    return text


def log_lines(raw: str) -> Tuple[List[str], str]:
    """(complete lines, unterminated tail) of a trainer log. tqdm redraws its
    bar with carriage returns: only the last redraw of a line is kept."""
    parts = raw.split("\n")
    tail = parts.pop()

    def last(seg: str) -> str:
        pieces = [p for p in seg.split("\r") if p.strip()]
        return pieces[-1].rstrip() if pieces else ""

    return [l for l in (last(p) for p in parts) if l], last(tail)


_PROGRESS_RE = re.compile(r"(\d+)/(\d+)\s*\[")


def parse_progress(raw: str, steps: int) -> Optional[int]:
    """The training step from the last tqdm bar whose total is ``steps``
    ("sf_x:  12%|█▏   | 180/1500 [01:23<10:00, ...]"). Other bars (latent
    caching, sampling) have other totals and are ignored."""
    step = None
    for m in _PROGRESS_RE.finditer(raw):
        if int(m.group(2)) == int(steps):
            step = int(m.group(1))
    return step


# ---------------------------------------------------------------------------
# Remote
# ---------------------------------------------------------------------------

class Remote:
    def __init__(self, cfg: Any):
        self.host = cfg.host
        self.os = (cfg.os or "linux").lower()
        self._toolkit = cfg.toolkitDir
        self.python = cfg.python
        self._base_model = cfg.baseModel
        if self.os not in SUPPORTED_OS:
            raise RemoteError(f"trainer os {self.os!r} is not supported yet (only linux)")
        if not self.host:
            raise RemoteError("no trainer host configured (settings training.host)")

    # -- plumbing ----------------------------------------------------------
    def ssh_args(self, command: str) -> List[str]:
        return ["ssh", *SSH_OPTS, self.host, command]

    def run(self, command: str, timeout: float = 60, input: Optional[bytes] = None,
            check: bool = True) -> subprocess.CompletedProcess:
        try:
            proc = subprocess.run(self.ssh_args(command), input=input, capture_output=True,
                                  timeout=timeout)
        except subprocess.TimeoutExpired:
            raise RemoteError(f"ssh {self.host} timed out after {timeout:.0f}s")
        except OSError as e:
            raise RemoteError(f"could not run ssh: {e}")
        if check and proc.returncode != 0:
            err = (proc.stderr or b"").decode("utf-8", "replace").strip()[-400:]
            raise RemoteError(f"ssh {self.host} failed (exit {proc.returncode}): {err}")
        return proc

    def scp(self, sources: List[str], dest: str, timeout: float = 3600) -> None:
        args = ["scp", *SSH_OPTS, "-q", *sources, dest]
        try:
            proc = subprocess.run(args, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise RemoteError(f"scp timed out after {timeout:.0f}s")
        except OSError as e:
            raise RemoteError(f"could not run scp: {e}")
        if proc.returncode != 0:
            err = (proc.stderr or b"").decode("utf-8", "replace").strip()[-400:]
            raise RemoteError(f"scp failed (exit {proc.returncode}): {err}")

    @property
    def home(self) -> str:
        if self.host not in _HOMES:
            out = self.run('printf %s "$HOME"', timeout=20).stdout.decode().strip()
            if not out.startswith("/"):
                raise RemoteError(f"could not read $HOME on {self.host}")
            _HOMES[self.host] = out
        return _HOMES[self.host]

    def absolute(self, path: str) -> str:
        """~ and relative paths resolved against the trainer's home."""
        path = str(path or "")
        if path == "~" or path.startswith("~/"):
            return self.home + path[1:]
        return path if path.startswith("/") else f"{self.home}/{path}"

    @property
    def toolkit_dir(self) -> str:
        return self.absolute(self._toolkit).rstrip("/")

    @property
    def base_model(self) -> str:
        return self.absolute(self._base_model)

    def job_dir(self, name: str, job_id: Optional[str] = None) -> str:
        """Per-job working dir (dataset, config, log, pidfile): a stopped job's
        late steps can never touch the files of the job that replaced it."""
        base = f"{self.home}/automanga-training/{name}"
        return f"{base}/{job_id}" if job_id else base

    def output_file(self, name: str) -> str:
        # ai-toolkit: <training_folder>/<name>/<name>.safetensors (final save)
        return f"{self.toolkit_dir}/output/{name}/{name}.safetensors"

    # -- steps -------------------------------------------------------------
    def check(self) -> Dict[str, Any]:
        """Pre-flight: toolkit, python and base model exist."""
        tk, py, model = self.toolkit_dir, self.python, self.base_model
        cmd = (f"cd {_q(tk)} 2>/dev/null && test -f run.py && echo toolkit; "
               f"cd {_q(tk)} 2>/dev/null && test -x {_q(py)} && echo python; "
               f"test -f {_q(model)} && echo model")
        found = self.run(cmd, timeout=30, check=False).stdout.decode().split()
        return {"toolkit": "toolkit" in found, "python": "python" in found, "model": "model" in found}

    def output_exists(self, name: str) -> bool:
        """True when output/<name> holds checkpoints, which ai-toolkit would
        resume from. (It writes output/<name>/config.yaml at start, so a job
        that failed before its first save leaves only that: not a resume.)"""
        d = self.toolkit_dir + "/output/" + name
        out = self.run(f"ls {_q(d)}/*.safetensors > /dev/null 2>&1 && echo yes",
                       timeout=30, check=False).stdout.decode().strip()
        return out == "yes"

    def push_dataset(self, files: List[Path], name: str, job_id: Optional[str] = None) -> str:
        """Replace the job's dataset on the trainer with ``files``; returns its path."""
        dest = self.job_dir(name, job_id) + "/dataset"
        self.run(f"rm -rf {_q(dest)} && mkdir -p {_q(dest)}", timeout=30)
        self.scp([str(f) for f in files], f"{self.host}:{dest}/")
        return dest

    def write_file(self, path: str, text: str) -> None:
        self.run(f"mkdir -p {_q(str(Path(path).parent))} && cat > {_q(path)}",
                 input=text.encode("utf-8"), timeout=30)

    @staticmethod
    def pidfile(log: str) -> str:
        return log + ".pid"

    def launch_command(self, config: str, log: str) -> str:
        inner = (f"{_q(self.python)} run.py {_q(config)} > {_q(log)} 2>&1; "
                 f"echo $? > {_q(log + '.exit.tmp')}; mv -f {_q(log + '.exit.tmp')} {_q(log + '.exit')}")
        pid, tmp = self.pidfile(log), self.pidfile(log) + ".tmp"
        # ";" not "&&": the "&" must background only setsid. Backgrounding a
        # whole "a && b && setsid ..." list forks a subshell that keeps ssh's
        # stdout open, so ssh would not return until training ended. setsid
        # gives the job its own session (no SIGHUP when ssh goes away) and
        # its stdio points away from the ssh channel. The pid also goes to
        # <log>.pid, so a server restart mid-launch can adopt the job.
        return (f"cd {_q(self.toolkit_dir)} || exit 1; rm -f {_q(log + '.exit')} {_q(pid)}; "
                f"setsid nohup /bin/sh -c {_q(inner)} > /dev/null 2>&1 < /dev/null & "
                f"p=$!; echo $p > {_q(tmp)} && mv -f {_q(tmp)} {_q(pid)}; echo $p")

    def launch(self, config: str, log: str) -> int:
        out = self.run(self.launch_command(config, log), timeout=30).stdout.decode().strip()
        try:
            return int(out.splitlines()[-1])
        except (IndexError, ValueError):
            raise RemoteError(f"launch returned no pid: {out[-200:]!r}")

    def read_pidfile(self, log: str) -> Optional[int]:
        """The pid the launcher recorded next to ``log``; None when it never
        got that far."""
        out = self.run(f"cat {_q(self.pidfile(log))} 2>/dev/null; true",
                       timeout=30).stdout.decode().strip()
        try:
            return int(out.splitlines()[-1])
        except (IndexError, ValueError):
            return None

    @staticmethod
    def _alive_test(pid: int, log: str) -> str:
        # the pid is ours only if its command line names our log (pid reuse)
        return (f"[ -r /proc/{int(pid)}/cmdline ] && "
                f"tr '\\0' ' ' < /proc/{int(pid)}/cmdline | grep -qF {_q(log)}")

    def poll_command(self, pid: int, log: str, offset: int) -> str:
        # alive first, then the exit file: a job that ends in between still
        # shows its exit code
        return (f"if {self._alive_test(pid, log)}; then a=1; else a=0; fi; "
                f"c=$(cat {_q(log + '.exit')} 2>/dev/null); "
                f"echo \"AMSTAT ${{c:-none}} $a\"; "
                f"tail -c +{int(offset) + 1} {_q(log)} 2>/dev/null | head -c {READ_LIMIT}")

    def poll(self, pid: int, log: str, offset: int) -> Tuple[Optional[int], bool, bytes]:
        """(exit code or None, alive, log bytes from ``offset``)."""
        out = self.run(self.poll_command(pid, log, offset), timeout=30).stdout
        head, _, data = out.partition(b"\n")
        m = _STAT_RE.match(head.decode("utf-8", "replace").strip())
        if not m:
            raise RemoteError(f"unexpected poll output: {head[:200]!r}")
        code = None if m.group(1) == "none" else int(m.group(1)) if m.group(1).lstrip("-").isdigit() else -1
        return code, m.group(2) == "1", data

    def stop_command(self, pid: int, log: str) -> str:
        # the job is its own process group (setsid): signal the whole group
        return (f"if {self._alive_test(pid, log)}; then "
                f"kill -TERM -- -{int(pid)} 2>/dev/null || kill -TERM {int(pid)}; fi; true")

    def stop(self, pid: int, log: str) -> None:
        self.run(self.stop_command(pid, log), timeout=30)

    def pull(self, remote_path: str, local_path: Path, overwrite: bool = True) -> None:
        if not overwrite and local_path.exists():
            raise RemoteError(f"{local_path} exists; refusing to overwrite it")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = local_path.with_name(local_path.name + ".part")
        tmp.unlink(missing_ok=True)
        self.scp([f"{self.host}:{remote_path}"], str(tmp))
        if not overwrite and local_path.exists():
            tmp.unlink(missing_ok=True)
            raise RemoteError(f"{local_path} appeared meanwhile; refusing to overwrite it")
        tmp.replace(local_path)


def free_lora_path(directory: Path, name: str) -> Path:
    """``directory/<name>.safetensors``, or the first free ``<name>_2``,
    ``<name>_3``… so a pull never replaces an existing LoRA."""
    path = directory / f"{name}.safetensors"
    n = 2
    while path.exists() or path.with_name(path.name + ".part").exists():
        path = directory / f"{name}_{n}.safetensors"
        n += 1
    return path
