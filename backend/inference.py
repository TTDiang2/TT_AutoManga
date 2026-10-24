"""Optional local ONNX upscaling — print-resolution output without SwarmUI.

Models are pinned by URL + SHA-256 in ``INFERENCE_MODELS`` and download
lazily into ``data/models/<model_id>/`` on first use. onnxruntime (+numpy)
is an OPTIONAL dependency: install ``backend/requirements-inference.txt``;
without it every entry point raises ``InferenceUnavailable`` and the API
layer answers 503 with an install hint.

Model notes: Real-ESRGAN family models are BSD-3-Clause upstream
(realesrgan-anime-6b is the anime default); quicksrnet-small ships via
Qualcomm AI Hub. Tiling follows the standard overlap-and-blend approach.

Public surface:
    available()          -> bool (onnxruntime importable)
    list_models()        -> manifest summary for the API
    upscale_bytes(png, model_id, tile) -> upscaled PNG bytes
"""
import hashlib
import io
import logging
import threading
from pathlib import Path
from typing import Dict, Optional

from .core.config import DATA_DIR

logger = logging.getLogger(__name__)

MODELS_DIR = DATA_DIR / "models"

# Real-ESRGAN NCNN-family ONNX exports: 1x3xHxW float32 RGB in [0,1], x4 out.
# Manifest facts (urls/bytes/sha256) cross-checked against the studied
# reference implementation; see docs/plans/2026-10-24-novelai-local-web-study.md
INFERENCE_MODELS: Dict[str, Dict] = {
    "realesrgan-anime-6b": {
        "scale": 4,
        "description": "Real-ESRGAN x4plus anime6B — general anime art (default, 18 MB)",
        "files": [{"name": "model.onnx",
                   "url": "https://huggingface.co/skillsafe-ai/realesrgan-x4plus-anime-6b/resolve/c001be50fae1c7a2bae8b2b4dec5e6fcbdbcca96/model.onnx?download=true",
                   "bytes": 17939975,
                   "sha256": "9a029dae374b2cd4c3eb2dbbed857e22e6d785687c767aa12828e7356b9fb378"}],
    },
    "realesr-animevideov3": {
        "scale": 4,
        "description": "Real-ESRGAN animevideov3 — fastest, smallest footprint (2.5 MB)",
        "files": [{"name": "model.onnx",
                   "url": "https://huggingface.co/skillsafe-ai/realesr-animevideov3/resolve/185e9142d439d17e3fb99395600fb7d08af09de5/model.onnx?download=true",
                   "bytes": 2492908,
                   "sha256": "78baa685a1a92cac6e14ab2af2a8ad0ef56fa48629563b1414e3a7acc54d86e2"}],
    },
}

_LOCK = threading.Lock()
_SESSIONS: Dict[str, "object"] = {}   # model_id -> onnxruntime session


class InferenceUnavailable(Exception):
    """onnxruntime (or numpy) is not installed."""


class ModelError(Exception):
    """Model manifest/download/verification failure."""


def available() -> bool:
    try:
        import onnxruntime  # noqa: F401
        import numpy  # noqa: F401
        return True
    except ImportError:
        return False


def _providers() -> list:
    import onnxruntime as ort
    available_providers = ort.get_available_providers()
    preferred = [p for p in ("CUDAExecutionProvider", "DmlExecutionProvider",
                             "CPUExecutionProvider") if p in available_providers]
    return preferred or ["CPUExecutionProvider"]


def _verify(path: Path, expected_sha: str) -> None:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    if h.hexdigest() != expected_sha:
        path.unlink(missing_ok=True)
        raise ModelError(f"downloaded model failed SHA-256 verification: {path.name}")


def _model_file(model_id: str) -> Path:
    """Manifest entry -> local verified file path (downloading if needed)."""
    import httpx

    model = INFERENCE_MODELS.get(model_id)
    if not model:
        raise ModelError(f"unknown model: {model_id}")
    target_dir = MODELS_DIR / model_id
    entries = []
    for spec in model["files"]:
        path = target_dir / spec["name"]
        if not (path.exists() and path.stat().st_size == spec["bytes"]):
            target_dir.mkdir(parents=True, exist_ok=True)
            logger.info("downloading model %s (%d bytes)", spec["name"], spec["bytes"])
            with httpx.Client(follow_redirects=True, timeout=600.0) as client:
                with client.stream("GET", spec["url"]) as resp:
                    resp.raise_for_status()
                    tmp = path.with_suffix(path.suffix + ".part")
                    with open(tmp, "wb") as f:
                        for chunk in resp.iter_bytes(1 << 20):
                            f.write(chunk)
            _verify(tmp, spec["sha256"])
            tmp.replace(path)
        entries.append(path)
    return entries[0]


def _session(model_id: str):
    if not available():
        raise InferenceUnavailable(
            "onnxruntime is not installed — pip install -r backend/requirements-inference.txt")
    with _LOCK:
        sess = _SESSIONS.get(model_id)
        if sess is None:
            import onnxruntime as ort
            path = _model_file(model_id)
            sess = ort.InferenceSession(str(path), providers=_providers())
            _SESSIONS[model_id] = sess
            logger.info("loaded upscale model %s (providers=%s)",
                        model_id, sess.get_providers())
        return sess


def upscale_bytes(png_bytes: bytes, model_id: str = "realesrgan-anime-6b",
                  tile: int = 512) -> bytes:
    """Upscale a PNG by the model's factor using overlap tiles (memory-safe
    on print-size images)."""
    import numpy as np
    from PIL import Image

    if model_id not in INFERENCE_MODELS:
        raise ModelError(f"unknown model: {model_id}")
    sess = _session(model_id)
    scale = INFERENCE_MODELS[model_id]["scale"]

    img = Image.open(io.BytesIO(png_bytes))
    if img.mode != "RGB":
        img = img.convert("RGB")
    arr = np.asarray(img, dtype=np.float32) / 255.0   # HWC
    h, w, _ = arr.shape

    tile = max(64, int(tile))
    overlap = 32
    out = np.zeros((h * scale, w * scale, 3), dtype=np.float32)
    weight = np.zeros((h * scale, w * scale, 1), dtype=np.float32)
    input_name = sess.get_inputs()[0].name

    ys = list(range(0, max(1, h - overlap), tile - overlap)) or [0]
    xs = list(range(0, max(1, w - overlap), tile - overlap)) or [0]
    for y0 in ys:
        for x0 in xs:
            y1, x1 = min(y0 + tile, h), min(x0 + tile, w)
            patch = arr[y0:y1, x0:x1]
            ph, pw, _ = patch.shape
            blob = patch.transpose(2, 0, 1)[None]          # 1x3xh xw
            result = sess.run(None, {input_name: blob})[0]
            out_patch = np.clip(result[0].transpose(1, 2, 0), 0.0, 1.0)
            # blend the overlap zone instead of hard seams
            yy, xx = y0 * scale, x0 * scale
            oh, ow = out_patch.shape[:2]
            region = out[yy:yy + oh, xx:xx + ow]
            wgt = weight[yy:yy + oh, xx:xx + ow]
            edge_x = min(x0, w - x1) > 0
            edge_y = min(y0, h - y1) > 0
            m = np.ones((oh, ow, 1), dtype=np.float32)
            ramp = np.linspace(0.05, 1.0, overlap, dtype=np.float32)
            if edge_y:
                m[:overlap, :, 0] *= ramp[:, None]
            if edge_x:
                m[:, :overlap, 0] *= ramp[None, :]
            region += out_patch * m
            wgt += m
            out[yy:yy + oh, xx:xx + ow] = region
            weight[yy:yy + oh, xx:xx + ow] = wgt

    out = np.where(weight > 0, out / np.maximum(weight, 1e-6), out)
    result_img = Image.fromarray((out * 255.0).round().astype("uint8"), "RGB")
    buf = io.BytesIO()
    result_img.save(buf, format="PNG")
    return buf.getvalue()
