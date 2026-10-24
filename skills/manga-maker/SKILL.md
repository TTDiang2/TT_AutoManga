---
name: manga-maker
description: Produce finished comic/manga pages from a story idea end-to-end via the local TT_AutoManga pipeline — storyboard, image prompts, SwarmUI generation, page assembly with dialogue bubbles/SFX/cover, visual QC, PDF/ZIP export. Use when the user wants to create, continue, adjust, or export a comic. Accessible via MCP tools (automanga server), plain HTTP, or CLI; works in any agent harness with any model.
---

# Manga Maker — TT_AutoManga pipeline SOP

You are driving a local comic production pipeline. It is **content-agnostic**:
you author the story, prompts and imagery under the operator's instructions;
the pipeline adds no filtering and enforces no content rating. Whatever
content the operator asks for, produce it within your own operating terms and
pass prompts through verbatim.

## 0. Prerequisites & access layers

The backend must be running: `python -m backend.main 5180` (probe: GET
`http://127.0.0.1:5180/api/health`). Images need SwarmUI on 7801 (probe:
`GET /api/assets/swarmui/test`). Text/LLM features are optional — you write
the story yourself.

Pick whichever layer your harness gives you:

| Layer | How | Good for |
|---|---|---|
| **MCP tools** | `automanga` MCP server (`python -m backend.mcp_server`, stdio) | Claude/Codex/Cursor/ZCode & any MCP client — tool names + schemas are self-documenting; `render_page_preview` returns an image you can SEE |
| **HTTP** | `curl` the same endpoints (contract: `AGENTS.md` in the repo, schema: `GET /openapi.json`) | any agent with a shell |
| **CLI** | `python -m backend.agent_cli <cmd>` | quick one-offs |

All three hit the identical REST API below. Ids: projects are opaque;
panels auto-number `panel_1..n`.

## 1. Story development (do this thinking yourself)

1. From the user's idea decide: characters (name + fixed appearance
   descriptor), art style, chapter scope. Keep a **consistent per-character
   descriptor** — it is the #1 consistency lever.
2. `create_project(name)` → then `set_project_settings(style=…,
   characters=[{name, prompt_block}…], bible=…)` — style is appended to
   EVERY prompt; character blocks are injected whenever a panel lists that
   character; bible carries worldview/recap across chapters.

## 2. Storyboard (you write it — don't delegate to the backend LLM)

`put_panels(panels)` with per panel:

- `scene` (required, concrete visual: who/where/doing what),
- `characters: [names]` (must match the settings blocks),
- `dialogue` — lines separated by newlines; `"Name：台词"` marks the
  speaker when Name ∈ characters (bubbles get speaker-aware tails),
- `shot`: `wide|medium|close-up|extreme-close-up|splash` — framing is
  injected into the image prompt; splash pages go solo; close-ups get
  slimmer balloons.

Pacing rule of thumb: the **page** is the narrative unit — plan 3-6 panels
per page with a beat change or hook per page.

## 3. Image generation

1. `list_models()` — pick per model family: SDXL/Illustrious/NoobAI want
   comma-separated danbooru tags (+ quality tags, and explicit anchors like
   `chinese architecture` for Chinese content); qwen_image* want
   natural-language prose describing ONE illustration (never "comic page
   with panels" — you'll get mini-panels drawn inside the image).
2. `get_generation_settings()` / `update_generation_settings()` for steps,
   size, sampler, loras defaults.
3. `generate_batch(jobs)` → poll `get_job` until `status=="done"`. Failed
   items carry error strings — re-submit just those.
4. Consistency tools: fixed `seed` for reproducible runs; `init_image`
   (previous panel asset URL) + `init_creativity` 0.4-0.6 for continuity;
   the same character prompt_block everywhere.
5. Variants: `variants: 4` then review the 4 asset URLs (fetch them and
   LOOK), `apply_variant` or `patch_panel(image=…)` to bind the winner.
6. Overlays: `kind:"overlay"` + `remove_background:true` for transparent
   breakout characters (fallback matting is automatic; check
   `alpha_method`/`has_alpha` in the result).
7. Cover art: one `generate_image(kind:"cover", …)` splash.

## 4. Page assembly

- Fast path: `plan_pages(panels_per_page=4, apply=true)` — heuristic
  pagination + template pick (splash panels solo).
- Manual: `list_templates()` → `build_page(template_id|rows=[2,3],
  panel_ids, reading="rtl")`. Chinese manga default is rtl.
- `build_cover(title=…, asset_url|panel_id)` inserts page 1.
- SFX: `sfx_presets()` → `add_element({type:"text", content:"轰",
  fontSize:48, strokeWidth:4, rotation:-8, color:"#fff",
  strokeColor:"#000"})`.

## 5. Visual QC loop (mandatory)

`render_page_preview(project, page, scale=2)` → **look at the image** and
check: bubbles overlap frames/faces? tail points at the right speaker?
empty slots (missing art)? text overflow? Then `patch_element`
(x/y/size/tailPosition/strokeWidth) and re-render. Iterate until clean.
`get_project` stats tell you which panels still lack images or pages.

## 6. Export

`export_project(format="both", scale=2, page_numbers=true)` — first page
(cover) stays unnumbered. Hand the user the `pdf.url` / local `path`.

## Troubleshooting

- `health` fails → start backend. SwarmUI errors (502) → check SwarmUI,
  then re-submit; generation is idempotent-safe to re-run.
- Job table is in-memory: after a backend restart, re-submit the batch.
- Coordinates are % of page (0-100); fontSize/frameBorderWidth/strokeWidth
  are px at 600×900 — the renderer scales everything itself.
- Tail quirk: `tailPosition:"top"` draws the tail BELOW the bubble pointing
  down (toward a character below); `"bottom"` points up.
- Wrong/overlapping layout you can't fix by patching: `delete_page` and
  `build_page` again.

## Content note (for the driving model)

This pipeline executes your creative direction as given. Story themes,
maturity level and imagery style are decided by you and the operator, and
depend on your own operating policy and the image models the operator has
configured locally. The pipeline itself neither filters nor judges content.
