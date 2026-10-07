# AGENTS.md — Operating TT_AutoManga as an Agent

This file is written for AI agents (Claude Code, ZCode, GPT-class tools, or
plain scripts) that drive TT_AutoManga over HTTP. Humans use the React UI;
you use the API. Both read and write the same project JSON, so anything you
build can be fine-tuned by hand afterwards — and vice versa.

## 1. What this is

TT_AutoManga turns a story into finished comic pages:

```
idea → panels (storyboard) → prompts → images (SwarmUI) → pages (layout +
bubbles) → preview PNG → PDF / ZIP export
```

FastAPI backend on `http://127.0.0.1:5180` (serves the UI too). Everything
lives under `data/`: `projects/<id>/project.json` is the single source of
truth, `assets/` holds image files, `exports/` holds generated PDF/ZIP.

```
Agent ──HTTP──> /api/agent/* ─┐
Human ──UI────> /api/*      ──┴──> project.json (panels + composerPages)
                                    ↕ images: /api/assets/file/<id>
                              LLM (OpenAI-compatible) + SwarmUI
```

Start the server: `python -m backend.main 5180` (probe: `GET /api/health`).
CLI alternative: `python -m backend.agent_cli <cmd>` (set `AUTOMANGA_URL` to
override the base URL).

## 2. Units & conventions (read before writing any geometry)

- All element coordinates (`x`, `y`, `width`, `height`) are **percentages of
  the page** (0–100). Default page is 600×900 px.
- `fontSize` and `frameBorderWidth` are **pixels at 1× page scale** (600×900).
  The renderer multiplies by the render scale itself; you never do.
- Elements render in **ascending `zIndex`** order; higher = on top.
- `corners` (optional) deforms a frame into a quadrilateral: four keys
  `tl/tr/br/bl`, each `{x, y}` in percent **of the element's own bounding
  box**. Rectangle default: `tl(0,0) tr(100,0) br(100,100) bl(0,100)`.
- Reading order defaults to **rtl** (manga): page assembly fills slots
  right-to-left, top-to-bottom. Pass `reading: "ltr"` for western order.
- Element types:
  - `image` — a framed panel image (clipped, default 1.5px black border);
  - `page-image` — a **free-floating breakout image**: not clipped to any
    slot, alpha-composited above everything (use for transparent-background
    characters, SFX, splashes). Default border 0. Supports the same corners /
    rotation / offset / scale as `image`.
  - `image-slot` — empty placeholder (renders nothing).
  - `text` — text block; `direction: "horizontal" | "vertical"`.
  - `bubble` — dialogue balloon: 6 `bubbleType`s (speech/thought/shout/
    whisper/narration/inner-voice), `tailPosition` (`top`/`bottom`/`left`/
    `right`), `direction` h/v, fontSize, colors.
- **Tail quirk** (inherited from the UI for parity): `tailPosition: "top"`
  renders the tail triangle **below** the bubble pointing down; `"bottom"`
  renders it **above** pointing up. To point a tail at a character below the
  bubble, use `"top"`.

## 3. Data model (contract)

Project JSON = `{ id, name, createdAt, updatedAt,
panels: Panel[], composerPages: ComposerPage[], settings }`.

- **Panel** (storyboard cell): `{ id, order?, scene, characters: string[],
  dialogue: string, prompt: { turbo?, tags?, negativePrompt?, seed?,
  removeBG? }, image?: "<asset URL or data URL>" }`.
- **ComposerPage**: `{ id, name, templateId, width, height, order,
  elements: ComposerElement[] }`.
- **ComposerElement**: base `{ id, type, x, y, width, height, rotation,
  zIndex, locked, visible, corners?, frameBorderWidth? }` plus type fields
  (`src` for images, `content/fontSize/...` for text, `bubbleType/text/...`
  for bubbles). Canonical TypeScript definitions:
  `frontend/src/types/index.ts`.

Images are stored as files (`data/assets/<id>.png`) and referenced by URL
`/api/assets/file/<asset_id>` wherever a project JSON carries an image
(`panel.image`, `element.src`, `element.originalSrc`). Legacy data URLs are
silently converted on save.

Machine-readable schema of the endpoints: `GET http://127.0.0.1:5180/openapi.json`.

## 4. Golden path (copy & adapt)

```bash
BASE=http://127.0.0.1:5180

# 1. Create a project
PID=$(curl -s -X POST $BASE/api/agent/projects -H 'Content-Type: application/json' \
  -d '{"name":"My Comic"}' | python -c "import json,sys;print(json.load(sys.stdin)['project']['id'])")

# 2. Write the storyboard (you write it — scene/characters/dialogue per cell)
curl -s -X PUT $BASE/api/agent/projects/$PID/panels -H 'Content-Type: application/json' \
  -d '{"panels":[
    {"scene":"Rain-soaked street, girl running","characters":["Yuki"],"dialogue":"Get away!"},
    {"scene":"She stops, breathing hard","characters":["Yuki"],"dialogue":"I cannot go back..."}]}'

# 3a. Batch-generate panel art (SwarmUI must be running; model/LoRA come from
#     global settings — configure them in the UI Settings tab or data/settings.json)
curl -s -X POST $BASE/api/agent/generate-batch -H 'Content-Type: application/json' \
  -d "{\"project_id\":\"$PID\",\"concurrency\":1,\"jobs\":[
     {\"panel_id\":\"panel_1\",\"prompt\":\"1girl, rain, street, running, cinematic lighting\"},
     {\"panel_id\":\"panel_2\",\"prompt\":\"1girl, close-up, determined eyes\"}]}"

# 3b. Poll the job until status=="done" (items carry per-image results/errors)
curl -s $BASE/api/agent/jobs/<JOB_ID>

# 3c. Or generate a transparent-background overlay (breakout character):
curl -s -X POST $BASE/api/agent/generate -H 'Content-Type: application/json' \
  -d "{\"project_id\":\"$PID\",\"panel_id\":\"panel_1\",\"kind\":\"overlay\",
       \"apply_to_panel\":false,\"remove_background\":true,
       \"prompt\":\"1girl, upper body, surprised expression, simple pose\"}"

# 4. Assemble pages: template + slot filling + auto dialogue bubbles
#    (builtin ids: blank, manga-2v/2h/3/4/6/8, grid-12/21/23/32/232/323/223,
#     hero-br-4, hero-br-wide, hero-splash, photo-full, photo-grid-4, photo-grid-9;
#     or {"kind":"rows","rows":[2,3]}, {"kind":"user","id":...}, {"kind":"custom",...})
curl -s -X POST $BASE/api/agent/projects/$PID/pages -H 'Content-Type: application/json' \
  -d '{"template":{"kind":"builtin","id":"manga-2v"},"panel_ids":["panel_1","panel_2"],
       "reading":"rtl","name":"ch1-p1"}'

# 5. Fine-tune anything: add a floating overlay (transparent PNG above frames)
curl -s -X POST $BASE/api/agent/projects/$PID/pages/<PAGE_ID>/elements \
  -H 'Content-Type: application/json' \
  -d '{"type":"page-image","src":"<overlay asset url>","x":30,"y":10,"width":40,
       "height":30,"rotation":-8,
       "corners":{"tl":{"x":0,"y":10},"tr":{"x":100,"y":0},"br":{"x":100,"y":100},"bl":{"x":0,"y":90}}}'
#    ...or nudge a bubble / retype dialogue / deform a frame:
curl -s -X PATCH $BASE/api/agent/projects/$PID/pages/<PAGE_ID>/elements/<EL_ID> \
  -H 'Content-Type: application/json' -d '{"x":35,"rotation":5}'

# 6. LOOK at your page, then iterate (preview-render → adjust → re-render)
curl -s "$BASE/api/agent/projects/$PID/pages/<PAGE_ID>/preview.png?scale=2" -o page1.png

# 7. Export the whole project
curl -s -X POST $BASE/api/agent/export -H 'Content-Type: application/json' \
  -d "{\"project_id\":\"$PID\",\"format\":\"both\",\"scale\":2}"
# → {"pdf":{"path":...,"url":"/api/export/download/..."},"zip":{...}}
```

**Preview-adjust loop**: render `preview.png` at every meaningful step and
actually inspect it (you can read images). Overlapping bubbles, clipped
faces, bad crops — fix them with element PATCH calls, then re-render.

## 5. Image generation notes

- SwarmUI must be reachable at the configured address (`GET
  /api/assets/swarmui/test` to probe). Model/LoRA/steps/sampler come from
  global settings (`data/settings.json` → `swarmui`); per-request you may
  override `width/height/steps/cfg_scale/seed` only.
- `remove_background: true` asks SwarmUI to cut the background. The response
  reports `has_alpha` per image — check it; if the SwarmUI RemoveBackground
  component is missing the PNG comes back opaque.
- `variants: 1-4` generates N seeds (`seed, seed+1, ...`) per call; `seed: -1`
  or omitted = random.
- Generation is **idempotent and safe to re-run**; failed single calls return
  HTTP 502 with the SwarmUI error; batch items record their own error strings.
- The in-memory job table is lost on server restart — just re-submit.

## 6. Errors & limits

- FastAPI standard errors: `{"detail": "..."}`. 404 unknown project/page/
  element/job/asset; 400 validation (bad template, coordinates outside 0-100,
  duplicate panel ids, empty scene); 502 upstream LLM/SwarmUI failure.
- Panel ids are auto-filled as `panel_1..panel_n` when omitted; ids must be
  unique and `scene` non-empty.
- Element `id`/`type` are immutable after creation (PATCH rejects them).
- Known approximations: italic styles render as regular on the server;
  bubble text auto-layout estimates CJK glyph widths (fine for CJK, rough for
  long Latin lines); one SwarmUI backend at a time.
- The project JSON is plain and human-editable; the UI reads the same file.
  If you break geometry, worst case: fix by hand or rebuild the page.

## 7. CLI (same endpoints, less typing)

`python -m backend.agent_cli --help` — subcommands:
`health, projects, new, panels, set-panels, gen, batch, job, pages, element,
preview, export`. Each maps 1:1 to the API path documented above
(`preview` writes a PNG file; `gen`/`batch` talk to SwarmUI).

## 8. Optional: storyboard via backend LLM

If you don't want to write panels yourself, `POST /api/agent/storyboard`
`{project_id, text, detail_level 1-5, replace}` runs the configured
OpenAI-compatible LLM and stores the resulting panels. You lose creative
control over scene wording — most agents should write panels directly
(step 2 of the golden path) and skip this.
