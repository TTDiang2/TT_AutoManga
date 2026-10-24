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

# 3a. Batch-generate panel art (SwarmUI must be running; steps/sampler come from
#     global settings — read/write them via GET/PUT /api/agent/settings, or the
#     UI Settings tab). Returns HTTP 202 {"job_id": "...", "total": N}.
#     Per job you may override: model, loras, prompt_format ("danbooru"|"prose"),
#     init_image (+init_creativity) for img2img, seed, width/height, and
#     inject_characters (auto style/character prompt injection, default on).
#     variants: 1-4 generates N seeds; apply_variant: i binds variant i to the
#     panel (default 0) — generate 4, look at them, PATCH panel.image if a
#     different one wins.
curl -s -X POST $BASE/api/agent/generate-batch -H 'Content-Type: application/json' \
  -d "{\"project_id\":\"$PID\",\"concurrency\":1,\"jobs\":[
     {\"panel_id\":\"panel_1\",\"prompt\":\"1girl, rain, street, running, cinematic lighting\"},
     {\"panel_id\":\"panel_2\",\"prompt\":\"1girl, close-up, determined eyes\",\"model\":\"qwen_image_2.1_int8_convrot\",\"prompt_format\":\"prose\"}]}"

# 3b. Poll the job until status=="done" (items carry per-image results/errors)
JOB_ID=<take "job_id" from the 202 response above>
curl -s $BASE/api/agent/jobs/$JOB_ID

# 3c. Or generate a transparent-background overlay (breakout character):
#     If SwarmUI's RemoveBackground is broken, the backend falls back to local
#     rembg / white-threshold matting and reports alpha_method per asset.
curl -s -X POST $BASE/api/agent/generate -H 'Content-Type: application/json' \
  -d "{\"project_id\":\"$PID\",\"panel_id\":\"panel_1\",\"kind\":\"overlay\",
       \"apply_to_panel\":false,\"remove_background\":true,
       \"prompt\":\"1girl, upper body, surprised expression, simple pose\"}"

# 3d. Discover installed models (name + architecture metadata):
curl -s $BASE/api/agent/models

# 3e. Tune generation defaults without the UI (takes effect on next /generate,
#     persists to data/settings.json):
curl -s -X PUT $BASE/api/agent/settings -H 'Content-Type: application/json' \
  -d '{"currentSteps":28,"currentWidth":832,"currentLoras":[{"name":"ink","weight":0.8}]}'

# 4. (Optional, recommended) Set a project style profile + character prompt
#    blocks. `style` is appended to EVERY panel prompt; a character block is
#    injected whenever a panel lists that character (project entries override
#    the global Characters library). Inspect with GET .../characters.
#    `bible` is a free-text story bible (worldview, recap, established
#    locations/props) — persisted with the project for cross-chapter
#    continuity; read it back via GET .../projects/$PID.
curl -s -X PUT $BASE/api/agent/projects/$PID/settings -H 'Content-Type: application/json' \
  -d '{"style":"chinese ink painting style, muted colors",
       "characters":[{"name":"Yuki","prompt_block":"1girl, white hair, blue eyes, blue kimono"}],
       "bible":"ch1: Yuki loses the jade pendant on the rain bridge"}'

# 5. Assemble pages: template + slot filling + auto dialogue bubbles
#    (builtin ids: blank, manga-2v/2h/3/4/6/8, grid-12/21/23/32/232/323/223,
#     hero-br-4, hero-br-wide, hero-splash, photo-full, photo-grid-4, photo-grid-9;
#     dynamic presets: dyn-2-slant, dyn-3-diag, dyn-hero-3, dyn-5-mix;
#     or {"kind":"rows","rows":[2,3]}, {"kind":"user","id":...}, {"kind":"custom",...})
#    "dynamic": true slants every non-hero frame (quadrilateral corners) for a
#     more cinematic page. List all templates + slot counts dynamically:
curl -s $BASE/api/agent/templates
curl -s -X POST $BASE/api/agent/projects/$PID/pages -H 'Content-Type: application/json' \
  -d '{"template":{"kind":"builtin","id":"manga-2v"},"panel_ids":["panel_1","panel_2"],
       "reading":"rtl","name":"ch1-p1","dynamic":true}'

# 6. Fine-tune anything: add a floating overlay (transparent PNG above frames)
curl -s -X POST $BASE/api/agent/projects/$PID/pages/<PAGE_ID>/elements \
  -H 'Content-Type: application/json' \
  -d '{"type":"page-image","src":"<overlay asset url>","x":30,"y":10,"width":40,
       "height":30,"rotation":-8,
       "corners":{"tl":{"x":0,"y":10},"tr":{"x":100,"y":0},"br":{"x":100,"y":100},"bl":{"x":0,"y":90}}}'
#    ...or nudge a bubble / retype dialogue / deform a frame:
curl -s -X PATCH $BASE/api/agent/projects/$PID/pages/<PAGE_ID>/elements/<EL_ID> \
  -H 'Content-Type: application/json' -d '{"x":35,"rotation":5}'

# 7. LOOK at your page, then iterate (preview-render → adjust → re-render)
curl -s "$BASE/api/agent/projects/$PID/pages/<PAGE_ID>/preview.png?scale=2" -o page1.png

# 8. Register locally-processed images as assets (e.g. your own matting/crop
#    output) without binding them to a panel:
curl -s -X POST $BASE/api/assets/file -F file=@dragon_alpha.png -F kind=overlay

# 9. Export the whole project
curl -s -X POST $BASE/api/agent/export -H 'Content-Type: application/json' \
  -d "{\"project_id\":\"$PID\",\"format\":\"both\",\"scale\":2}"
# → {"pages_dir": "...", "pdf": {"path": "...", "url": "/api/export/download/..."},
#    "zip": {"path": "...", "url": "/api/export/download/..."}}
# (format "pdf" or "zip" returns only that key; download URLs are same-origin GETs)
```

**Preview-adjust loop**: render `preview.png` at every meaningful step and
actually inspect it (you can read images). Overlapping bubbles, clipped
faces, bad crops — fix them with element PATCH calls, then re-render.

## 5. Model & prompt format guide (read before generating)

Pick the prompt format per model — mismatched formats are the #1 quality killer
(western furniture in Chinese stories, literal-minded tag errors, etc.):

- **Danbooru-tag models** (SDXL family: `*Illustrious*`, `NoobAI`, …):
  comma-separated tags, quality tags at the end
  (`masterpiece, best quality`). Chinese content needs explicit anchor tags:
  `chinese dragon` (NOT plain `dragon` — you will get bat wings),
  `dragon throne`, `chinese architecture`, `tang dynasty`, `chinese clothes`,
  `paper lantern`, `ink (medium)`. Tags are literal: `deer antlers` may summon
  an entire deer — phrase carefully. Keep a **fixed descriptor block per
  character** repeated in every prompt for consistency.
- **Natural-language models** (`qwen_image*`): write full Chinese/English
  prose. They understand culture natively (棋盘→围棋, 蟠龙宝座, 汉字可读) and
  render Chinese text. Rules: describe a **single illustration** — never write
  分镜/分格/comic page, or the model draws mini-panels inside one image;
  keep character descriptions as a consistent prose block per character.

`GET /api/agent/models` lists installed models with `architecture` metadata.
Per-request overrides (`model`, `loras`, `prompt_format`, `init_image`,
`init_creativity`) beat global settings; batch jobs can mix models.
`prompt_format` also controls how auto-injection joins text (`, ` for tags,
`。` for prose) and is recorded in the asset metadata.

**Automatic injection** (on by default, `inject_characters: false` to disable):
project `settings.style` is appended to every panel prompt; for each character
named on the panel, its `prompt_block` (project → global Characters library)
is appended. Set them via `PUT /api/agent/projects/{id}/settings`.

**Consistency & continuity tools**: fixed seeds make style-reproducible runs;
`init_image` (+`init_creativity` 0-1) runs img2img against an asset or data
URL — feed the previous panel (low creativity ~0.4-0.6) or a character sheet
in for continuity.

## 6. Image generation notes

- SwarmUI must be reachable at the configured address (`GET
  /api/assets/swarmui/test` to probe). Steps/sampler/LoRA come from global
  settings (`data/settings.json` → `swarmui`); model/loras may be overridden
  per request.
- `remove_background: true` asks SwarmUI to cut the background. If SwarmUI's
  remover is missing or broken, the backend falls back to local `rembg`
  (if installed) or white-threshold matting; each asset reports
  `alpha_method` (`swarmui|rembg|threshold`) and `has_alpha` — check them.
  For the threshold path, prompt for a plain white background.
- `variants: 1-4` generates N seeds (`seed, seed+1, ...`) per call; `seed: -1`
  or omitted = random.
- Generation is **idempotent and safe to re-run**; failed single calls return
  HTTP 502 with the SwarmUI error; batch items record their own error strings.
- `GET /api/agent/assets/{asset_id}` returns the generation-time metadata
  recorded for every asset (prompt, seed, model, alpha method) — your memory
  for reproducing or tweaking a panel after the fact.
- The in-memory job table is lost on server restart — just re-submit.
- `POST /api/assets/file` registers arbitrary image bytes (e.g. your own
  post-processing output) as a reusable asset.

## 7. Errors & limits

- FastAPI standard errors: `{"detail": "..."}`. 404 unknown project/page/
  element/job/asset; 400 validation (bad template, coordinates outside 0-100,
  duplicate panel ids, empty scene, unsafe id); 502 upstream LLM/SwarmUI
  failure.
- Panel ids are auto-filled as `panel_1..panel_n` when omitted; ids must be
  unique and `scene` non-empty.
- Project/folder ids become directory names on disk, so they must match
  `[A-Za-z0-9_-]{1,128}` — anything else is rejected with 400 (server-side
  generated ids always comply).
- Element `id`/`type` are immutable after creation (PATCH rejects them).
- Known approximations: italic styles render as regular on the server;
  bubble text auto-layout estimates CJK glyph widths (fine for CJK, rough for
  long Latin lines); one SwarmUI backend at a time.
- `GET /api/settings/` returns the LLM `api_key` masked (`****` + last 4);
  saving it back unchanged keeps the stored key (only a freshly typed value
  replaces it).
- The project JSON is plain and human-editable; the UI reads the same file.
  If you break geometry, worst case: fix by hand or rebuild the page.

## 8. CLI (same endpoints, less typing)

`python -m backend.agent_cli --help` — subcommands:
`health, projects, new, panels, set-panels, gen, batch, job, pages, element,
preview, export`. Each maps 1:1 to the API path documented above
(`preview` writes a PNG file; `gen`/`batch` talk to SwarmUI).

## 9. Optional: storyboard via backend LLM

If you don't want to write panels yourself, `POST /api/agent/storyboard`
`{project_id, text, detail_level 1-5, replace}` runs the configured
OpenAI-compatible LLM and stores the resulting panels. You lose creative
control over scene wording — most agents should write panels directly
(step 2 of the golden path) and skip this.
