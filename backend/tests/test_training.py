"""Phase 7 LoRA training: config rendering, log parsing, the per-OS remote
commands, the dataset routes and the job pipeline (push → config → launch →
poll → pull → SwarmUI refresh → character lora) against a fake ssh/scp on
PATH, including the pickup of a persisted job after a restart."""
import base64
import io
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT.parent))

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

import backend.api.characters as chars_mod  # noqa: E402
import backend.api.training as tapi  # noqa: E402
from backend import training as tr  # noqa: E402
from backend.core import config  # noqa: E402
from backend.main import app  # noqa: E402

# Stands in for ssh and scp (installed under both names). It never runs the
# remote command: it records it and answers from files in $FAKE_REMOTE.
_FAKE = r'''#!{python}
import os, sys, shutil
state = os.environ["FAKE_REMOTE"]
prog = os.path.basename(sys.argv[0])
args = sys.argv[1:]
rest = []
i = 0
while i < len(args):
    if args[i] == "-o":
        i += 2
        continue
    if args[i] == "-q":
        i += 1
        continue
    rest.append(args[i])
    i += 1
with open(os.path.join(state, "calls.log"), "a") as f:
    f.write(prog + "\t" + "\t".join(rest).replace("\n", "\\n") + "\n")
if prog == "scp":
    *src, dest = rest
    if src[0].startswith("pless@"):        # pull: hand out the trained LoRA
        shutil.copy(os.path.join(state, "lora.safetensors"), dest)
    sys.exit(0)
host, cmd = rest[0], rest[1]
if os.path.exists(os.path.join(state, "unreachable")):
    sys.stderr.write("ssh: connect to host: Connection timed out\n")
    sys.exit(255)
if cmd == 'printf %s "$HOME"':
    sys.stdout.write("/home/razer")
elif "test -f run.py" in cmd:
    print(open(os.path.join(state, "check")).read() if os.path.exists(os.path.join(state, "check"))
          else "toolkit python model")
elif cmd.startswith("ls ") and ".safetensors" in cmd:
    if os.path.exists(os.path.join(state, "output_exists")):
        print("yes")
elif "cat >" in cmd:
    open(os.path.join(state, "written.yaml"), "w").write(sys.stdin.read())
elif "setsid nohup" in cmd:
    print("4242")
elif cmd.startswith("cat ") and ".pid" in cmd:
    if os.path.exists(os.path.join(state, "pidfile")):
        print(open(os.path.join(state, "pidfile")).read())
elif "AMSTAT" in cmd:
    sys.stdout.buffer.write(open(os.path.join(state, "poll"), "rb").read())
'''


def _png_bytes(color=(200, 50, 50), size=(64, 96)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def env(tmp_path, monkeypatch):
    remote = tmp_path / "remote"
    remote.mkdir()
    (remote / "lora.safetensors").write_bytes(b"LORA" * 100)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("ssh", "scp"):
        p = bin_dir / name
        p.write_text(_FAKE.replace("{python}", sys.executable))
        p.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_REMOTE", str(remote))
    monkeypatch.setattr(tapi, "DATASETS_DIR", tmp_path / "data" / "training")
    monkeypatch.setattr(tapi, "JOB_FILE", tmp_path / "data" / "training_job.json")
    monkeypatch.setattr(tapi, "JOB_LOG", tmp_path / "data" / "training_job.log")
    monkeypatch.setattr(tapi, "SWARM_LORA_DIR", tmp_path / "Lora")
    monkeypatch.setattr(tapi, "POLL_INTERVAL", 0)
    monkeypatch.setattr(tapi, "_worker", None)
    monkeypatch.setattr(tapi, "_gen", {})
    monkeypatch.setattr(tr, "_HOMES", {})
    tcfg = config.TrainingConfig(host="pless@razer", baseModel="~/models/base.safetensors")
    monkeypatch.setattr(config.settings, "training", tcfg)
    chars = tmp_path / "characters.json"
    chars.write_text(json.dumps([{"id": "c1", "name": "Nova", "description": "",
                                  "appearance": "1girl, short silver hair, red jacket",
                                  "sourcePanelIds": []}]))
    monkeypatch.setattr(chars_mod, "CHARACTERS_FILE", chars)
    refreshed = []
    monkeypatch.setattr(tapi, "_refresh_swarmui", lambda: refreshed.append(True))
    return SimpleNamespace(remote=remote, tmp=tmp_path, chars=chars, refreshed=refreshed)


@pytest.fixture
def client(env):
    return TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))


def _calls(env):
    p = env.remote / "calls.log"
    return p.read_text().splitlines() if p.exists() else []


def _dataset(client, n=15, slug="nova", trigger="amnova", char="c1"):
    r = client.post("/api/training/datasets", json={"slug": slug, "trigger": trigger, "characterId": char})
    assert r.status_code == 200, r.text
    if n:
        files = [("files", (f"x{i}.png", _png_bytes((i * 10, 0, 0)), "image/png")) for i in range(n)]
        r = client.post(f"/api/training/datasets/{slug}/upload", files=files)
        assert r.status_code == 200, r.text
        assert r.json()["count"] == n


def _wait(pred, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.05)
    return False


def _wait_worker():
    assert _wait(lambda: tapi._worker is None or not tapi._worker.is_alive())


# ---------------------------------------------------------------------------
# pure functions
# ---------------------------------------------------------------------------

def test_render_config_keeps_the_sf_recipe():
    text = tr.render_config(name="am_nova", trigger="amnova", folder_path="/h/ds",
                            base_model="/h/models/b.safetensors", steps=1500,
                            prompts=["amnova, solo, standing", 'amnova, "quoted", sitting'])
    for line in ("job: extension", "  name: \"am_nova\"", "    trigger_word: \"amnova\"",
                 "      linear: 16", "      linear_alpha: 16", "      dtype: float16",
                 "      save_every: 500", "      max_step_saves_to_keep: 3",
                 "    - folder_path: \"/h/ds\"", "      caption_ext: txt",
                 "      caption_dropout_rate: 0.05", "      cache_latents_to_disk: true",
                 "      resolution: [512, 768]", "      batch_size: 1", "      steps: 1500",
                 "      cache_text_embeddings: false",
                 "      train_unet: true", "      train_text_encoder: false",
                 "      gradient_checkpointing: true", "      noise_scheduler: ddpm",
                 "      optimizer: adamw8bit", "      lr: 0.0001", "      dtype: bf16",
                 "      name_or_path: \"/h/models/b.safetensors\"", "      arch: sdxl",
                 "      low_vram: true", "      sample_every: 500", "      width: 832",
                 "      height: 1216", '      - "amnova, \\"quoted\\", sitting"'):
        assert line in text.splitlines(), line
    assert "      disable_sampling: true" in text.splitlines()     # 8 GB: previews OOM
    assert "      disable_sampling: false" in tr.render_config(
        name="n", trigger="t", folder_path="/f", base_model="/b", steps=10, prompts=["p"],
        sampling=True).splitlines()
    assert "{{" not in text


def test_render_config_carries_the_configured_resolution():
    """settings training.resolution: 1024 OOMs on the 8 GB 3070 with
    full-size panels, so the buckets are a setting (default [512, 768])."""
    text = tr.render_config(name="n", trigger="t", folder_path="/f", base_model="/b", steps=10,
                            prompts=["p"], resolution=[512, 768, 1024],
                            cache_text_embeddings=True)
    assert "      resolution: [512, 768, 1024]" in text.splitlines()
    assert "      cache_text_embeddings: true" in text.splitlines()
    assert "      resolution: [512, 768]" in tr.render_config(
        name="n", trigger="t", folder_path="/f", base_model="/b", steps=10,
        prompts=["p"]).splitlines()


def test_log_lines_keeps_the_last_tqdm_redraw():
    raw = ("Loading model\n"
           "Caching latents to disk:  50%|█    | 8/15 [00:01<00:01]\r"
           "Caching latents to disk: 100%|██| 15/15 [00:02<00:00]\n"
           "am_nova:   1%|          | 1/100 [00:02<03:00, 1.1s/it, lr: 1.0e-04 loss: 1.2e-01]\r"
           "am_nova:  42%|████▏     | 42/100 [00:50<01:10, 1.2s/it, lr: 1.0e-04 loss: 9.0e-02]")
    lines, partial = tr.log_lines(raw)
    assert lines == ["Loading model", "Caching latents to disk: 100%|██| 15/15 [00:02<00:00]"]
    assert partial.startswith("am_nova:  42%")
    assert tr.parse_progress(raw, 100) == 42
    assert tr.parse_progress(raw, 1500) is None     # the 15/15 caching bar is not training
    assert tr.parse_progress("x: 100%|█| 1500/1500 [1:00:00<00:00]\n", 1500) == 1500


def test_remote_linux_commands(env):
    r = tr.Remote(config.settings.training)
    assert r.ssh_args("true")[:6] == ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "pless@razer"]
    assert r.toolkit_dir == "/home/razer/ai-toolkit"
    assert r.base_model == "/home/razer/models/base.safetensors"
    assert r.output_file("am_x") == "/home/razer/ai-toolkit/output/am_x/am_x.safetensors"
    launch = r.launch_command("/j/config.yaml", "/j/train.log")
    assert launch.startswith("cd /home/razer/ai-toolkit || exit 1; rm -f /j/train.log.exit /j/train.log.pid; "
                             "setsid nohup /bin/sh -c ")
    assert "venv/bin/python run.py /j/config.yaml > /j/train.log 2>&1" in launch
    assert "mv -f /j/train.log.exit.tmp /j/train.log.exit" in launch
    assert "rm -f /j/train.log.exit /j/train.log.pid;" in launch
    assert "> /dev/null 2>&1 < /dev/null & p=$!; echo $p > /j/train.log.pid.tmp && " \
           "mv -f /j/train.log.pid.tmp /j/train.log.pid; echo $p" in launch
    assert r.job_dir("am_x", "j9") == "/home/razer/automanga-training/am_x/j9"
    poll = r.poll_command(4242, "/j/train.log", 100)
    assert "/proc/4242/cmdline" in poll and "grep -qF /j/train.log" in poll
    assert "tail -c +101 /j/train.log" in poll
    stop = r.stop_command(4242, "/j/train.log")
    assert "kill -TERM -- -4242" in stop and "/proc/4242/cmdline" in stop


def test_remote_windows_is_refused():
    with pytest.raises(tr.RemoteError, match="not supported"):
        tr.Remote(config.TrainingConfig(os="windows"))


def test_remote_unreachable_is_a_remote_error(env):
    (env.remote / "unreachable").write_text("")
    with pytest.raises(tr.RemoteError, match="exit 255"):
        tr.Remote(config.settings.training).home


# ---------------------------------------------------------------------------
# datasets
# ---------------------------------------------------------------------------

def test_dataset_crud(client, env):
    _dataset(client, n=3)
    view = client.get("/api/training/datasets/nova").json()
    assert [i["file"] for i in view["images"]] == ["img_001.png", "img_002.png", "img_003.png"]
    d = env.tmp / "data" / "training" / "nova"
    assert (d / "img_002.txt").read_text() == "amnova"
    assert client.get("/api/training/datasets/nova/image/img_001.png").status_code == 200
    r = client.delete("/api/training/datasets/nova/image/img_002.png")
    assert [i["file"] for i in r.json()["images"]] == ["img_001.png", "img_003.png"]
    assert not (d / "img_002.txt").exists()
    # numbering continues after the highest
    files = [("files", ("a.png", _png_bytes(), "image/png"))]
    assert client.post("/api/training/datasets/nova/upload", files=files).json()["added"] == ["img_004.png"]
    listing = client.get("/api/training/datasets?character_id=c1").json()["datasets"]
    assert [(x["slug"], x["count"]) for x in listing] == [("nova", 3)]
    assert client.post("/api/training/datasets", json={"slug": "nova", "trigger": "amnova"}).status_code == 409
    assert client.post("/api/training/datasets", json={"slug": "../x", "trigger": "amnova"}).status_code == 400
    assert client.post("/api/training/datasets", json={"slug": "y", "trigger": "two words"}).status_code == 400
    assert client.get("/api/training/datasets/nova/image/meta.json").status_code == 400
    files = [("files", ("bad.png", b"not an image", "image/png"))]
    assert client.post("/api/training/datasets/nova/upload", files=files).status_code == 400


def test_import_project_panels(client, env, monkeypatch):
    from backend.storage import manager as mgr
    monkeypatch.setattr(mgr, "PROJECTS_DIR", env.tmp / "projects")
    proj = env.tmp / "projects" / "p1"
    proj.mkdir(parents=True)
    durl = "data:image/png;base64," + base64.b64encode(_png_bytes()).decode()
    (proj / "project.json").write_text(json.dumps({"id": "p1", "panels": [
        {"id": "a", "image": durl}, {"id": "b", "image": None}, {"id": "c", "image": durl}]}))
    _dataset(client, n=0)
    r = client.post("/api/training/datasets/nova/import", json={"projectId": "p1"})
    assert r.status_code == 200 and r.json()["added"] == ["img_001.png", "img_002.png"]
    assert r.json()["skipped"] == 1
    r = client.post("/api/training/datasets/nova/import", json={"projectId": "p1", "panelIds": ["c"]})
    assert r.json()["added"] == ["img_003.png"]
    assert client.post("/api/training/datasets/nova/import", json={"projectId": "nope"}).status_code == 404


def test_generate_uses_appearance_grid_and_seed_steps(env, monkeypatch):
    from backend.core.swarmui_client import swarm_client
    calls = []

    async def fake_generate(**kw):
        calls.append(kw)
        return {"success": True, "image": "data:image/png;base64," + base64.b64encode(_png_bytes()).decode()}

    monkeypatch.setattr(swarm_client, "generate_image", fake_generate)
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as c:
        _dataset(c, n=0)
        r = c.post("/api/training/datasets/nova/generate", json={"count": 4})
        assert r.status_code == 200, r.text
        assert _wait(lambda: not c.get("/api/training/datasets/nova").json()["generation"]["running"])
        view = c.get("/api/training/datasets/nova").json()
        assert view["count"] == 4 and view["generation"]["done"] == 4
        # a second batch continues the grid and the seeds
        c.post("/api/training/datasets/nova/generate", json={"count": 2})
        assert _wait(lambda: c.get("/api/training/datasets/nova").json()["count"] == 6)
    assert [k["seed"] for k in calls] == [tapi.SEED_BASE + i * 7919 for i in range(6)]
    assert all(k["prompt"].startswith("1girl, short silver hair, red jacket, solo, ") for k in calls)
    assert len({k["prompt"] for k in calls}) == 6
    assert all([l.name for l in k["loras"]] == [""] for k in calls)    # LoRA-free


# ---------------------------------------------------------------------------
# jobs
# ---------------------------------------------------------------------------

def test_job_needs_15_images(client, env):
    _dataset(client, n=14)
    r = client.post("/api/training/jobs", json={"slug": "nova"})
    assert r.status_code == 400 and "15" in r.json()["detail"]


def test_job_pipeline_end_to_end(client, env):
    _dataset(client, n=15)
    (env.remote / "poll").write_bytes(
        b"AMSTAT none 1\nLoading\nam_nova:  10%|#  | 10/100 [00:10<01:30]\ram_nova:  50%|##  | 50/100 [00:50<00:50]")
    r = client.post("/api/training/jobs", json={"slug": "nova", "name": "am_nova", "steps": 100})
    assert r.status_code == 200, r.text
    _wait_worker()
    job = client.get("/api/training/jobs/current").json()["job"]
    assert job["phase"] == "running" and job["pid"] == 4242 and job["step"] == 50
    assert job["lines"] == ["Loading"] and job["partial"].startswith("am_nova:  50%")
    assert job["remote"]["output"] == "/home/razer/ai-toolkit/output/am_nova/am_nova.safetensors"
    calls = _calls(env)
    scp_push = [c for c in calls if c.startswith("scp\t") and "pless@razer:" in c][0]
    jd = f"/home/razer/automanga-training/am_nova/{job['id']}"     # per-job remote dir
    assert scp_push.endswith(f"pless@razer:{jd}/dataset/")
    assert job["remote"]["log"] == f"{jd}/train.log" and job["remote"]["pidfile"] == f"{jd}/train.log.pid"
    assert scp_push.count(".png") == 15 and scp_push.count(".txt") == 15
    cfg = (env.remote / "written.yaml").read_text()
    assert f'folder_path: "{jd}/dataset"' in cfg
    assert "steps: 100" in cfg and 'trigger_word: "amnova"' in cfg
    assert 'name_or_path: "/home/razer/models/base.safetensors"' in cfg
    # another start while one runs
    assert client.post("/api/training/jobs", json={"slug": "nova"}).status_code == 409
    # the next poll gets only new bytes (offset = mirror size) and the exit
    (env.remote / "poll").write_bytes(b"AMSTAT 0 0\n\r am_nova: 100%|###| 100/100 [01:40<00:00]\nSaved\n")
    job = client.get("/api/training/jobs/current?since=1").json()["job"]
    assert job["phase"] in ("finishing", "done") and job["step"] == 100
    _wait_worker()
    job = client.get("/api/training/jobs/current").json()["job"]
    assert job["phase"] == "done", job
    local = env.tmp / "Lora" / "Comics" / "am_nova.safetensors"
    assert local.read_bytes() == b"LORA" * 100
    assert job["lora"] == {"name": "Comics/am_nova", "weight": 0.8, "trigger": "amnova"}
    assert env.refreshed == [True]
    char = json.loads(env.chars.read_text())[0]
    assert char["lora"] == {"name": "Comics/am_nova", "weight": 0.8, "trigger": "amnova"}
    poll_calls = [c for c in _calls(env) if "AMSTAT" in c]
    assert "tail -c +1 " in poll_calls[0] and "tail -c +1 " not in poll_calls[1]


def test_job_config_carries_the_settings_resolution(client, env):
    """the written config.yaml uses settings.training.resolution (and the
    text-embedding cache switch), not the recipe's 768/1024."""
    config.settings.training.resolution = [640, 896]
    config.settings.training.cacheTextEmbeddings = True
    _dataset(client, n=15)
    assert client.post("/api/training/jobs", json={"slug": "nova"}).status_code == 200
    _wait_worker()
    cfg = (env.remote / "written.yaml").read_text().splitlines()
    assert "      resolution: [640, 896]" in cfg
    assert "      cache_text_embeddings: true" in cfg


def test_job_fails_on_missing_base_model(client, env):
    _dataset(client, n=15)
    (env.remote / "check").write_text("toolkit python")
    client.post("/api/training/jobs", json={"slug": "nova"})
    _wait_worker()
    job = client.get("/api/training/jobs/current").json()["job"]
    assert job["phase"] == "failed" and "base model" in job["error"]


def test_job_refuses_existing_output_unless_resume(client, env):
    _dataset(client, n=15)
    (env.remote / "output_exists").write_text("")
    client.post("/api/training/jobs", json={"slug": "nova"})
    _wait_worker()
    assert "has checkpoints on the trainer" in client.get("/api/training/jobs/current").json()["job"]["error"]
    (env.remote / "poll").write_bytes(b"AMSTAT none 1\n")
    client.post("/api/training/jobs", json={"slug": "nova", "resume": True})
    _wait_worker()
    assert client.get("/api/training/jobs/current").json()["job"]["phase"] == "running"


def test_trainer_exit_code_and_vanish(client, env):
    _dataset(client, n=15)
    (env.remote / "poll").write_bytes(b"AMSTAT none 1\n")
    client.post("/api/training/jobs", json={"slug": "nova"})
    _wait_worker()
    (env.remote / "poll").write_bytes(b"AMSTAT 1 0\nTraceback: CUDA out of memory\n")
    job = client.get("/api/training/jobs/current").json()["job"]
    assert job["phase"] == "failed" and "code 1" in job["error"]
    assert job["lines"][-1] == "Traceback: CUDA out of memory"


def test_stop(client, env):
    _dataset(client, n=15)
    (env.remote / "poll").write_bytes(b"AMSTAT none 1\n")
    client.post("/api/training/jobs", json={"slug": "nova"})
    _wait_worker()
    r = client.post("/api/training/jobs/current/stop")
    assert r.status_code == 200
    assert any("kill -TERM -- -4242" in c for c in _calls(env))
    (env.remote / "poll").write_bytes(b"AMSTAT 143 0\n")
    assert client.get("/api/training/jobs/current").json()["job"]["phase"] == "stopped"
    assert client.post("/api/training/jobs/current/stop").status_code == 409


def _persist(env, **kw):
    job = {"id": "j1", "name": "am_nova", "slug": "nova", "trigger": "amnova", "characterId": "c1",
           "steps": 100, "pid": 4242, "step": 0, "started": time.time(), "events": [],
           "remote": {"jobDir": "/home/razer/automanga-training/am_nova", "config": "c",
                      "log": "/home/razer/automanga-training/am_nova/train.log",
                      "output": "/home/razer/ai-toolkit/output/am_nova/am_nova.safetensors"}, **kw}
    tapi.JOB_FILE.parent.mkdir(parents=True, exist_ok=True)
    tapi.JOB_FILE.write_text(json.dumps(job))


def test_restart_pickup_of_a_running_job(client, env):
    _persist(env, phase="running")
    (env.remote / "poll").write_bytes(b"AMSTAT none 1\nam_nova:  30%|#| 30/100 [00:30<01:10]")
    job = client.get("/api/training/jobs/current").json()["job"]
    assert job["phase"] == "running" and job["step"] == 30


def test_restart_pickup_of_finishing_and_interrupted_jobs(client, env):
    _persist(env, phase="finishing")
    client.get("/api/training/jobs/current")
    _wait_worker()
    assert client.get("/api/training/jobs/current").json()["job"]["phase"] == "done"
    assert (env.tmp / "Lora" / "Comics" / "am_nova.safetensors").exists()
    _persist(env, phase="pushing")
    job = client.get("/api/training/jobs/current").json()["job"]
    assert job["phase"] == "failed" and "restart" in job["error"]


def test_poll_error_keeps_the_job(client, env):
    _persist(env, phase="running")
    (env.remote / "unreachable").write_text("")
    job = client.get("/api/training/jobs/current").json()["job"]
    assert job["phase"] == "running" and "exit 255" in job["pollError"]


def test_launch_command_returns_at_once_and_detaches(tmp_path, monkeypatch):
    """Run the real launch string in a local shell, its stdout a pipe as under
    ssh: it must print the pid and return while the job keeps running, then
    the job writes its exit code. (Regression: backgrounding the whole
    "cd && rm && setsid" list kept the pipe open until training ended.)"""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "setsid").write_text('#!/bin/sh\nexec "$@"\n')     # macOS has none
    (bin_dir / "setsid").chmod(0o755)
    tk = tmp_path / "tk"
    tk.mkdir()
    (tk / "py").write_text("#!/bin/sh\nsleep 1.5\necho trained $1\n")
    (tk / "py").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(tr, "_HOMES", {"h": str(tmp_path)})
    r = tr.Remote(config.TrainingConfig(host="h", toolkitDir="~/tk", python="./py"))
    log = str(tmp_path / "train.log")
    t0 = time.time()
    proc = __import__("subprocess").run(["/bin/sh", "-c", r.launch_command("cfg.yaml", log)],
                                         capture_output=True, timeout=10)
    assert time.time() - t0 < 1.0, "launch waited for the job"
    assert int(proc.stdout.decode().strip()) > 0
    assert not Path(log + ".exit").exists()
    assert _wait(lambda: Path(log + ".exit").exists(), timeout=10)
    assert Path(log + ".exit").read_text().strip() == "0"
    assert Path(log + ".pid").read_text().strip() == proc.stdout.decode().strip()
    assert Path(log).read_text() == "trained run.py\n"


# ---------------------------------------------------------------------------
# review fixes: locking, races, restart adoption, overwrite, caps
# ---------------------------------------------------------------------------

def test_render_config_strips_control_characters():
    text = tr.render_config(name="n", trigger="t", folder_path="/f", base_model="/b", steps=10,
                            prompts=["t, red\njacket\x1b[31m\u2028x", "p"])
    assert '"t, red jacket [31m x"' in text
    assert tr.clean_text("a\tb\r\n  c") == "a b c"


def test_restart_during_launching_adopts_the_trainer(client, env):
    _persist(env, phase="launching", pid=None)
    (env.remote / "pidfile").write_text("5151\n")
    (env.remote / "poll").write_bytes(b"AMSTAT none 1\n")
    job = client.get("/api/training/jobs/current").json()["job"]
    assert job["phase"] == "running" and job["pid"] == 5151
    assert any("adopted" in e for e in job["events"])
    assert any(c.startswith("ssh") and "train.log.pid" in c for c in _calls(env))


def test_restart_during_launching_without_pidfile_fails(client, env):
    _persist(env, phase="launching", pid=None)
    job = client.get("/api/training/jobs/current").json()["job"]
    assert job["phase"] == "failed" and "restart" in job["error"]


def test_stopped_while_launching_after_restart_kills_the_trainer(client, env):
    _persist(env, phase="stopped", pid=None, stopRequested=True)
    (env.remote / "pidfile").write_text("5151\n")
    client.get("/api/training/jobs/current")
    assert any("kill -TERM -- -5151" in c for c in _calls(env))
    assert client.get("/api/training/jobs/current").json()["job"]["phase"] == "stopped"


def test_stop_during_launch_stops_the_launched_process(client, env, monkeypatch):
    _dataset(client, n=15)
    real_launch = tr.Remote.launch

    def launch_then_stop(self, cfg, log):
        assert tapi.stop_job()["job"]["phase"] == "stopped"    # pressed while ssh runs
        return real_launch(self, cfg, log)
    monkeypatch.setattr(tr.Remote, "launch", launch_then_stop)
    client.post("/api/training/jobs", json={"slug": "nova"})
    _wait_worker()
    job = client.get("/api/training/jobs/current").json()["job"]
    assert job["phase"] == "stopped" and job["pid"] == 4242
    assert any("kill -TERM -- -4242" in c for c in _calls(env))


def test_superseded_job_does_no_remote_steps(env):
    _persist(env, phase="stopped", stopRequested=True)
    tapi._prepare_and_launch("j1")
    tapi._prepare_and_launch("not-the-current-job")
    assert not any("setsid" in c or c.startswith("scp") for c in _calls(env))


def test_job_lock_is_free_during_ssh(client, env, monkeypatch):
    import threading
    _persist(env, phase="running")
    seen = []

    def poll(self, pid, log, offset):
        out = []
        t = threading.Thread(target=lambda: out.append(tapi._lock.acquire(timeout=1)
                                                       and (tapi._lock.release() or True)))
        t.start()
        t.join()
        seen.append(out[0])
        return None, True, b""
    monkeypatch.setattr(tr.Remote, "poll", poll)
    client.get("/api/training/jobs/current")
    assert seen == [True]


def test_pull_never_overwrites_an_existing_lora(client, env):
    existing = env.tmp / "Lora" / "Comics" / "am_nova.safetensors"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"OLD")
    _persist(env, phase="finishing")
    client.get("/api/training/jobs/current")
    _wait_worker()
    job = client.get("/api/training/jobs/current").json()["job"]
    assert job["phase"] == "done", job
    assert existing.read_bytes() == b"OLD"
    assert (existing.parent / "am_nova_2.safetensors").read_bytes() == b"LORA" * 100
    assert job["lora"]["name"] == "Comics/am_nova_2"
    assert json.loads(env.chars.read_text())[0]["lora"]["name"] == "Comics/am_nova_2"


def test_collect_retries_a_failed_finish(client, env):
    (env.remote / "lora.safetensors").unlink()          # the pull fails
    _persist(env, phase="finishing")
    client.get("/api/training/jobs/current")
    _wait_worker()
    job = client.get("/api/training/jobs/current").json()["job"]
    assert job["phase"] == "failed" and "collect" in job["error"] and job["collectable"]
    (env.remote / "lora.safetensors").write_bytes(b"LORA")
    r = client.post("/api/training/jobs/current/collect")
    assert r.status_code == 200, r.text
    _wait_worker()
    job = client.get("/api/training/jobs/current").json()["job"]
    assert job["phase"] == "done" and job["lora"]["name"] == "Comics/am_nova"
    assert client.post("/api/training/jobs/current/collect").status_code == 409


def test_upload_caps_and_bad_base64(client, env, monkeypatch):
    _dataset(client, n=2)
    monkeypatch.setattr(tapi, "MAX_UPLOAD_BYTES", 100)
    files = [("files", ("big.png", _png_bytes(size=(200, 200)) + b"x" * 200, "image/png"))]
    assert client.post("/api/training/datasets/nova/upload", files=files).status_code == 413
    monkeypatch.setattr(tapi, "MAX_UPLOAD_BYTES", 25 << 20)
    monkeypatch.setattr(tapi, "MAX_DATASET_IMAGES", 3)
    files = [("files", (f"{i}.png", _png_bytes(), "image/png")) for i in range(2)]
    assert client.post("/api/training/datasets/nova/upload", files=files).status_code == 400
    assert client.get("/api/training/datasets/nova").json()["count"] == 2
    with pytest.raises(Exception) as ei:
        tapi._panel_bytes("data:image/png;base64,abc")      # bad padding
    assert getattr(ei.value, "status_code", None) == 400
