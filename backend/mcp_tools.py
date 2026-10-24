"""Thin async HTTP layer over the /api/agent/* endpoints.

One function per MCP tool, no MCP dependency — the MCP server
(backend/mcp_server.py) wraps these with typed signatures, and the tests
exercise them through an injected httpx.MockTransport. The base URL comes
from AUTOMANGA_URL (default http://127.0.0.1:5180).
"""
import os
from typing import Any, Dict, List, Optional

import httpx

BASE_URL = os.environ.get("AUTOMANGA_URL", "http://127.0.0.1:5180").rstrip("/")

# tests inject a MockTransport here; None means "real network"
_TRANSPORT: Optional[httpx.AsyncBaseTransport] = None


class ToolError(Exception):
    """Raised when the backend answers non-2xx; carries its detail message."""


async def _call(method: str, path: str, *, json: Any = None,
                params: Any = None, raw: bool = False) -> Any:
    # trust_env=False: the backend is always local; a system proxy must
    # never intercept 127.0.0.1 (same reasoning as openai_client.py)
    async with httpx.AsyncClient(timeout=600.0, transport=_TRANSPORT,
                                 trust_env=False) as client:
        resp = await client.request(method, f"{BASE_URL}{path}",
                                    json=json, params=params)
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise ToolError(f"{method} {path} -> HTTP {resp.status_code}: {detail}")
    if raw:
        return resp.content
    if not resp.content:
        return {}
    return resp.json()


# ------------------------------------------------------------------ system

async def health() -> Dict[str, Any]:
    """Backend liveness. Call this first; if it fails start the backend
    (python -m backend.main 5180)."""
    return await _call("GET", "/api/health")


# ------------------------------------------------------------------ projects

async def create_project(name: str, panels: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    return await _call("POST", "/api/agent/projects",
                       json={"name": name, "panels": panels or []})


async def list_projects() -> Dict[str, Any]:
    """All projects with progress stats (panels with/without images, pages)."""
    return await _call("GET", "/api/agent/projects")


async def get_project(project_id: str) -> Dict[str, Any]:
    """Full project JSON (panels, pages, settings incl. story bible) + stats."""
    return await _call("GET", f"/api/agent/projects/{project_id}")


async def put_panels(project_id: str, panels: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Replace the whole storyboard. Each panel: {id?, scene (required),
    characters: [str], dialogue, shot?: wide|medium|close-up|
    extreme-close-up|splash, prompt: {...}}. Dialogue lines "Name：台词"
    mark the speaker when Name is in characters."""
    return await _call("PUT", f"/api/agent/projects/{project_id}/panels",
                       json={"panels": panels})


async def patch_panel(project_id: str, panel_id: str,
                      updates: Dict[str, Any]) -> Dict[str, Any]:
    """Partial-update one panel (scene/dialogue/characters/shot/image/prompt)."""
    return await _call("PATCH",
                       f"/api/agent/projects/{project_id}/panels/{panel_id}",
                       json=updates)


async def set_project_settings(
        project_id: str, style: Optional[str] = None,
        characters: Optional[List[Dict[str, str]]] = None,
        locations: Optional[List[Dict[str, str]]] = None,
        bible: Optional[str] = None) -> Dict[str, Any]:
    """Style profile (appended to every prompt), character prompt blocks
    ([{name, prompt_block}], injected when a panel lists that character), a
    location library (injected when a panel names that location via its
    `location` field), and a free-text story bible for cross-chapter
    continuity."""
    body: Dict[str, Any] = {}
    if style is not None:
        body["style"] = style
    if characters is not None:
        body["characters"] = characters
    if locations is not None:
        body["locations"] = locations
    if bible is not None:
        body["bible"] = bible
    return await _call("PUT", f"/api/agent/projects/{project_id}/settings",
                       json=body)


# ------------------------------------------------------------------ generation

async def get_generation_settings() -> Dict[str, Any]:
    """Effective SwarmUI defaults /generate falls back to (model, steps, cfg,
    width/height, sampler, prompt suffix, loras)."""
    return await _call("GET", "/api/agent/settings")


async def update_generation_settings(
        settings: Dict[str, Any]) -> Dict[str, Any]:
    """Update generation defaults (currentModel/currentSteps/currentCfgScale/
    currentWidth/currentHeight/currentSamplerName/promptSuffix/currentLoras).
    Persists; takes effect on the next generate call."""
    return await _call("PUT", "/api/agent/settings", json=settings)


async def list_models() -> Dict[str, Any]:
    """Installed SwarmUI models with architecture metadata. Danbooru-tag
    models (SDXL/Illustrious/NoobAI) want comma-separated tags; natural
    language models (qwen_image*) want prose — check `architecture`."""
    return await _call("GET", "/api/agent/models")


async def generate_image(
        prompt: str, project_id: Optional[str] = None,
        panel_id: Optional[str] = None,
        negative_prompt: str = "", seed: Optional[int] = None,
        width: Optional[int] = None, height: Optional[int] = None,
        steps: Optional[int] = None, cfg_scale: Optional[float] = None,
        loras: Optional[List[Dict[str, Any]]] = None,
        inject_characters: bool = True,
        remove_background: bool = False, variants: int = 1,
        apply_variant: int = 0, apply_to_panel: bool = True,
        kind: str = "panel", model: Optional[str] = None,
        prompt_format: Optional[str] = None,
        init_image: Optional[str] = None,
        init_creativity: Optional[float] = None,
        mask_image: Optional[str] = None) -> Dict[str, Any]:
    """Generate one image via SwarmUI. init_image (asset URL / data URL,
    creativity 0-1) runs img2img for continuity. variants 1-4 = N seeds;
    apply_variant picks which one binds to the panel. Returns asset URLs
    plus generation metadata (seed, prompt, alpha method)."""
    body: Dict[str, Any] = {"prompt": prompt, "negative_prompt": negative_prompt,
                            "remove_background": remove_background,
                            "variants": variants, "apply_variant": apply_variant,
                            "apply_to_panel": apply_to_panel, "kind": kind}
    for k, v in (("project_id", project_id), ("panel_id", panel_id),
                 ("seed", seed), ("width", width), ("height", height),
                 ("steps", steps), ("cfg_scale", cfg_scale),
                 ("loras", loras), ("model", model),
                 ("prompt_format", prompt_format),
                 ("init_image", init_image),
                 ("init_creativity", init_creativity),
                 ("mask_image", mask_image)):
        if v is not None:
            body[k] = v
    if not inject_characters:
        body["inject_characters"] = False
    return await _call("POST", "/api/agent/generate", json=body)


async def generate_batch(jobs: List[Dict[str, Any]],
                         project_id: Optional[str] = None,
                         concurrency: int = 1) -> Dict[str, Any]:
    """Queue many generate jobs (same fields as generate_image per job).
    Returns {job_id, total}; poll with get_job until status=="done"."""
    return await _call("POST", "/api/agent/generate-batch",
                       json={"jobs": jobs, "project_id": project_id,
                             "concurrency": concurrency})


async def get_job(job_id: str) -> Dict[str, Any]:
    """Batch job status; items carry per-image results or error strings."""
    return await _call("GET", f"/api/agent/jobs/{job_id}")


async def get_asset(asset_id: str) -> Dict[str, Any]:
    """Generation-time metadata for one asset (prompt, seed, model, alpha
    method) — use it to reproduce or tweak a panel after the fact."""
    return await _call("GET", f"/api/agent/assets/{asset_id}")


# ------------------------------------------------------------------ pages

async def list_templates() -> Dict[str, Any]:
    """All page templates (id, slots, dynamic flag, sizes) + other layout
    kinds (rows/custom/user)."""
    return await _call("GET", "/api/agent/templates")


async def plan_pages(project_id: str, panels_per_page: int = 4,
                     splash_panel_ids: Optional[List[str]] = None,
                     only_with_image: bool = True, apply: bool = False,
                     reading: str = "rtl", dynamic: bool = False,
                     bubbles_mode: str = "auto",
                     bubble_font_size: int = 14,
                     bubble_vertical: bool = True) -> Dict[str, Any]:
    """Heuristic pagination: chunk panels into pages (splash panels go solo),
    template picked per slot count. apply=true builds all pages at once;
    bubbles_mode="none" builds them without auto bubbles."""
    return await _call("POST", f"/api/agent/projects/{project_id}/plan-pages",
                       json={"panels_per_page": panels_per_page,
                             "splash_panel_ids": splash_panel_ids or [],
                             "only_with_image": only_with_image,
                             "apply": apply, "reading": reading,
                             "dynamic": dynamic,
                             "bubbles": {"mode": bubbles_mode,
                                         "fontSize": bubble_font_size,
                                         "vertical": bubble_vertical}})


async def build_page(project_id: str,
                     template_id: Optional[str] = None,
                     panel_ids: Optional[List[str]] = None,
                     reading: str = "rtl", dynamic: bool = False,
                     name: Optional[str] = None,
                     rows: Optional[List[int]] = None,
                     bubbles_mode: str = "auto",
                     bubble_font_size: int = 14,
                     bubble_vertical: bool = True,
                     dry_run: bool = False) -> Dict[str, Any]:
    """Assemble one page from a builtin template id (see list_templates) or a
    rows layout like [2,3] (columns per row). Fills slots in reading order
    and auto-creates dialogue bubbles (with speaker + tail heuristics);
    bubbles_mode="none" disables them. dry_run returns the page unsaved."""
    template: Dict[str, Any]
    if rows is not None:
        template = {"kind": "rows", "rows": rows}
    else:
        template = {"kind": "builtin", "id": template_id or "blank"}
    return await _call("POST", f"/api/agent/projects/{project_id}/pages",
                       json={"template": template, "panel_ids": panel_ids or [],
                             "reading": reading, "dynamic": dynamic,
                             "name": name, "dry_run": dry_run,
                             "bubbles": {"mode": bubbles_mode,
                                         "fontSize": bubble_font_size,
                                         "vertical": bubble_vertical}})


async def delete_page(project_id: str, page_id: str) -> Dict[str, Any]:
    return await _call("DELETE", f"/api/agent/projects/{project_id}/pages/{page_id}")


async def reorder_pages(project_id: str, page_ids: List[str]) -> Dict[str, Any]:
    """Set a new full page order; page_ids must list every existing page id."""
    return await _call("PUT", f"/api/agent/projects/{project_id}/pages/order",
                       json={"page_ids": page_ids})


async def build_cover(project_id: str, title: str,
                      subtitle: Optional[str] = None,
                      asset_url: Optional[str] = None,
                      panel_id: Optional[str] = None,
                      title_color: str = "#ffffff",
                      font_size: int = 64) -> Dict[str, Any]:
    """Cover page (full-bleed art + outlined title), inserted as page 1.
    Point asset_url at cover art you generated (kind="cover") or reuse a
    panel's image via panel_id."""
    body: Dict[str, Any] = {"title": title,
                            "title_color": title_color,
                            "font_size": font_size}
    if subtitle is not None:
        body["subtitle"] = subtitle
    if asset_url is not None:
        body["asset_url"] = asset_url
    if panel_id is not None:
        body["panel_id"] = panel_id
    return await _call("POST", f"/api/agent/projects/{project_id}/cover", json=body)


async def sfx_presets() -> Dict[str, Any]:
    """Curated onomatopoeia (zh/ja/en) + default SFX text styling."""
    return await _call("GET", "/api/agent/sfx-presets")


# ------------------------------------------------------------------ elements

async def add_element(project_id: str, page_id: str,
                      element: Dict[str, Any]) -> Dict[str, Any]:
    """Add an element (image/page-image/text/bubble/image-slot). SFX recipe:
    type text + fontSize ~48 + strokeWidth 4 + rotation -8."""
    return await _call("POST",
                       f"/api/agent/projects/{project_id}/pages/{page_id}/elements",
                       json=element)


async def patch_element(project_id: str, page_id: str, element_id: str,
                        updates: Dict[str, Any]) -> Dict[str, Any]:
    """Nudge/restyle an element (x/y/size/rotation/corners/tailPosition...).
    id and type are immutable."""
    return await _call("PATCH", f"/api/agent/projects/{project_id}/pages/{page_id}"
                       f"/elements/{element_id}", json=updates)


async def delete_element(project_id: str, page_id: str,
                         element_id: str) -> Dict[str, Any]:
    return await _call("DELETE", f"/api/agent/projects/{project_id}/pages/{page_id}"
                       f"/elements/{element_id}")


# ------------------------------------------------------------------ preview & export

async def render_preview(project_id: str, page_id: str,
                         scale: float = 2.0) -> bytes:
    """Render one page server-side to PNG bytes (scale 0.5-4). LOOK at the
    result to QC: overlapping bubbles, clipped faces, wrong speaker tails."""
    return await _call("GET",
                       f"/api/agent/projects/{project_id}/pages/{page_id}"
                       f"/preview.png",
                       params={"scale": scale}, raw=True)


async def export_project(project_id: str, format: str = "both",
                         scale: float = 2.0,
                         page_numbers: bool = False) -> Dict[str, Any]:
    """Export all pages (pdf|zip|both; page_numbers stamps every page but
    the first). Returns local paths + same-origin download URLs."""
    return await _call("POST", "/api/agent/export",
                       json={"project_id": project_id, "format": format,
                             "scale": scale, "page_numbers": page_numbers})


# ------------------------------------------------------------------ local inference

async def list_inference_models() -> Dict[str, Any]:
    """Local ONNX upscale models and whether onnxruntime is installed
    (optional dependency: backend/requirements-inference.txt)."""
    return await _call("GET", "/api/agent/inference-models")


async def upscale_image(asset_url: str, model: str = "realesrgan-anime-6b",
                        tile: int = 512) -> Dict[str, Any]:
    """Upscale an asset x4 with a local ONNX model (downloaded on first use,
    no SwarmUI involved); registers the result as a new asset. Use for
    print-resolution exports of key panels/covers."""
    return await _call("POST", "/api/agent/upscale",
                       json={"asset_url": asset_url, "model": model,
                             "tile": tile})
