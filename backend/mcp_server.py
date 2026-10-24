"""MCP server exposing TT_AutoManga's agent API as tools (stdio transport).

Any MCP client (Claude Desktop, Claude Code, ZCode, Cursor, Codex, custom)
can drive the whole comic pipeline through this server without reading any
documentation first: tool names, typed arguments and descriptions are the
contract. Multimodal clients additionally *see* rendered pages — the
render_page_preview tool returns image content.

Run:    python -m backend.mcp_server
Config: AUTOMANGA_URL (default http://127.0.0.1:5180); the backend
        (python -m backend.main 5180) must be running.

The pipeline is content-agnostic: story text, prompts and imagery are
authored by the driving model under the operator's instructions and passed
through verbatim to the configured SwarmUI backend. This server adds no
filtering and enforces no rating — content decisions belong to the operator,
the model they drive it with, and their local image-generation setup.

Works with mcp SDK 1.x (FastMCP) and 2.x (MCPServer).
"""
import base64
import inspect
import logging
import sys
from typing import Any, Dict, List, Optional

try:  # mcp 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

from . import mcp_tools
from .mcp_tools import ToolError

# stdio transport: the protocol lives on stdout — logs must go to stderr
logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger("automanga.mcp")

# constructor kwargs differ between SDK generations — pass only what this
# installation supports
_CANDIDATE_KWARGS: Dict[str, Any] = dict(
    name="automanga",
    title="TT_AutoManga",
    description=(
        "End-to-end comic production: storyboard panels, generate images via "
        "SwarmUI, assemble pages with auto dialogue bubbles, preview-render, "
        "export PDF/ZIP. Content-agnostic local pipeline."
    ),
    instructions=(
        "Typical flow: health -> create_project -> put_panels (scene/characters/"
        "dialogue per panel; optional shot framing; 'Name：台词' marks speakers) "
        "-> set_project_settings (style + character prompt blocks + story bible) "
        "-> list_models to pick model/format -> generate_batch -> poll get_job -> "
        "plan_pages(apply) -> render_page_preview and LOOK at each page, fix with "
        "patch_element -> build_cover -> export_project. Prompts and story content "
        "are yours to author; nothing is filtered."
    ),
)


def _make_server() -> Any:
    supported = inspect.signature(_Server.__init__).parameters
    kwargs = {k: v for k, v in _CANDIDATE_KWARGS.items() if k in supported}
    return _Server(**kwargs)


mcp = _make_server()


def _tool(fn, *, name: str, desc: str):
    wrapped = mcp.tool(name=name, description=desc)(fn)
    return wrapped


# ---- system / projects / panels ----
_tool(mcp_tools.health, name="health",
      desc="Check the TT_AutoManga backend is up. Call first; if it fails, "
           "the backend must be started (python -m backend.main 5180).")
_tool(mcp_tools.create_project, name="create_project",
      desc="Create a comic project; returns the project with its id. "
           "Panels may be supplied now or later via put_panels.")
_tool(mcp_tools.list_projects, name="list_projects",
      desc="List all projects with progress stats (images missing, pages).")
_tool(mcp_tools.get_project, name="get_project",
      desc="Full project JSON (panels, pages, settings incl. story bible) "
           "plus completion stats.")
_tool(mcp_tools.put_panels, name="put_panels",
      desc="Write the whole storyboard. Panel = {id?, scene (required), "
           "characters: [names], dialogue, shot?: wide|medium|close-up|"
           "extreme-close-up|splash}. Dialogue lines 'Name：台词' mark the "
           "speaker when Name is in that panel's characters.")
_tool(mcp_tools.patch_panel, name="patch_panel",
      desc="Update one panel (e.g. swap its bound image to another variant).")
_tool(mcp_tools.set_project_settings, name="set_project_settings",
      desc="Set project style profile (appended to every prompt), character "
           "prompt blocks for consistent characters, and a free-text story "
           "bible for cross-chapter continuity.")

# ---- generation ----
_tool(mcp_tools.get_generation_settings, name="get_generation_settings",
      desc="Read SwarmUI generation defaults (model/steps/cfg/size/sampler/"
           "loras/prompt suffix).")
_tool(mcp_tools.update_generation_settings, name="update_generation_settings",
      desc="Update generation defaults; persists and applies to subsequent "
           "generate calls.")
_tool(mcp_tools.list_models, name="list_models",
      desc="Installed image models with architecture metadata. Tag-style "
           "models want comma-separated danbooru tags; qwen-style models "
           "want natural-language prose prompts.")
_tool(mcp_tools.generate_image, name="generate_image",
      desc="Generate one image. Supports img2img continuity (init_image + "
           "init_creativity), transparent backgrounds (remove_background), "
           "and 1-4 seed variants with apply_variant to pick the winner.")
_tool(mcp_tools.generate_batch, name="generate_batch",
      desc="Queue many generate_image jobs at once (each job takes the same "
           "fields); returns job_id, poll with get_job.")
_tool(mcp_tools.get_job, name="get_job",
      desc="Poll a batch job until status=='done'; items carry per-image "
           "asset URLs or error strings.")
_tool(mcp_tools.get_asset, name="get_asset",
      desc="Read one asset's generation metadata (prompt, seed, model) to "
           "reproduce or tweak it later.")

# ---- pages ----
_tool(mcp_tools.list_templates, name="list_templates",
      desc="All page templates with slot counts, plus rows/custom layout "
           "kinds.")
_tool(mcp_tools.plan_pages, name="plan_pages",
      desc="Heuristic pagination: chunk panels into pages (splash panels go "
           "solo), template chosen per slot count; apply=true builds them.")
_tool(mcp_tools.build_page, name="build_page",
      desc="Assemble one page from template_id (or rows like [2,3]); fills "
           "slots in reading order (default rtl manga) and auto-creates "
           "dialogue bubbles with speaker/tail heuristics.")
_tool(mcp_tools.delete_page, name="delete_page", desc="Delete one page.")
_tool(mcp_tools.reorder_pages, name="reorder_pages",
      desc="Set a new full page order (must list every page id exactly once).")
_tool(mcp_tools.build_cover, name="build_cover",
      desc="Build the cover page (full-bleed art + outlined title, inserted "
           "as page 1) from generated cover art or an existing panel.")
_tool(mcp_tools.sfx_presets, name="sfx_presets",
      desc="Curated onomatopoeia words (zh/ja/en) + default SFX text styling.")

# ---- elements ----
_tool(mcp_tools.add_element, name="add_element",
      desc="Add a page element (text/bubble/image/page-image). SFX recipe: "
           "text, fontSize~48, strokeWidth 4, rotation -8.")
_tool(mcp_tools.patch_element, name="patch_element",
      desc="Fine-tune an element: position, size, rotation, corners, "
           "tailPosition, strokeWidth...")
_tool(mcp_tools.delete_element, name="delete_element",
      desc="Remove an element from a page.")

# ---- preview & export ----
_tool(mcp_tools.export_project, name="export_project",
      desc="Export all pages to PDF and/or ZIP; returns file paths and "
           "download URLs.")


@mcp.tool(name="render_page_preview",
          description="Render one page to an image and LOOK at it: QC for "
                      "overlapping bubbles, clipped faces, wrong speaker "
                      "tails, empty slots. Returns PNG image content.",
          structured_output=False)
async def render_page_preview(project_id: str, page_id: str,
                              scale: float = 2.0) -> List[Any]:
    from mcp.types import ImageContent
    png = await mcp_tools.render_preview(project_id, page_id, scale)
    return [
        ImageContent(type="image",
                     data=base64.b64encode(png).decode(),
                     mimeType="image/png"),
    ]


def main() -> None:
    logger.info("TT_AutoManga MCP server starting (backend at %s)",
                mcp_tools.BASE_URL)
    mcp.run("stdio")


if __name__ == "__main__":
    main()
