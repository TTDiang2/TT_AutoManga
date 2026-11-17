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
MCP alternative: `python -m backend.mcp_server` exposes the same API as 30
typed MCP tools (any MCP client; `render_page_preview` returns image
content). A portable workflow skill lives at `skills/manga-maker/SKILL.md`
(agentskills.io format).

### Access (login gate)

`/api/*` is behind one password and/or "Sign in with Google"
(`backend/core/auth.py`, `backend/api/auth_google.py`, middleware
`auth_gate` in `backend/main.py`). **Local callers are exempt**: a request
whose TCP peer is `127.0.0.1`/`::1`, whose `Host` is `localhost`, `127.0.0.1`
or `[::1]` (any port) and that carries no `X-Forwarded-For`, `Forwarded` or
`X-Real-IP` header never needs a session. That covers the
MCP tools, `agent_cli`, and the Comics converter (`automanga.js`, spawned by
`/api/comics` with `AUTOMANGA_URL=http://127.0.0.1:<port>`). Keep calling
`http://127.0.0.1:5180` directly, and don't add forwarding headers.
Everyone else needs the `am_session` cookie, which is what browsers get through
the reverse proxy (Caddy on `settings.auth.trustedProxy`, default
`192.168.1.11`, which is never treated as local).

- Host allowlist (DNS rebinding guard): every request, SPA included, whose
  `Host` is not `localhost`/`127.0.0.1`/`[::1]`, one of this machine's own
  names or LAN addresses (detected at startup) or a name in
  `data/settings.json` → `auth.allowedHosts` (default `[]`) gets 400. Before
  exposing a public name through Caddy (which forwards the original Host),
  add it there, e.g. `"allowedHosts": ["manga.madebypless.dk"]`.
- A local reverse proxy (e.g. `vite` dev server on :5173 proxying `/api`):
  without `xfwd: true` it sends no `X-Forwarded-For`, so its requests count
  as local only because `changeOrigin` rewrites Host to `localhost:5180`.
  Anything else it relays (a LAN browser on a `vite --host` server) is then
  treated as local too: set `xfwd: true` on the proxy when it serves other
  machines.
- Set or change the password on the server:
  `.venv/bin/python -m backend.core.auth set-password`. Add `--stdin` to read
  it from the first line of stdin. `logout-all` signs every device out, and
  `status` shows what is configured (never a secret). The password lives in
  `data/auth.json` (chmod 600) as a scrypt hash, a 32-byte secret and a
  version. Changing the password or running `logout-all` bumps the version.
- Sign in with Google (OpenID Connect; setup: `docs/GOOGLE_LOGIN.md`):
  - The OAuth client id and secret live only in `data/auth.json`
    (`set-google`, `--stdin` reads "id\nsecret"; `clear-google`), never in
    settings.json, and no API returns them.
  - `settings.auth.publicUrl` (default `""` = off) is the https URL browsers
    use; the redirect URI is always `<publicUrl>/api/auth/google/callback`
    (never derived from Host). `set-public-url <url>` sets it and adds its
    host to `allowedHosts`.
  - `settings.auth.googleAllowedEmails` (exact, lowercased; `allow-email` /
    `deny-email`, or Settings → Access). Removing an address ends its
    sessions at once.
  - `settings.auth.passwordLogin` (default `true`). `false`: remote
    `POST /api/auth/login` gets 403 `password login is disabled`. Local
    callers and the CLI still work, so the owner can't be locked out.
  - The CLI settings commands edit `data/settings.json` on disk; restart the
    server afterwards (it holds settings in memory).
  - `GET /api/auth/google/start?next=/path` (public) 302s to Google with
    PKCE S256, state, nonce and `prompt=select_account`. On any Host other
    than publicUrl's it 302s to publicUrl's start first. state, nonce,
    verifier and next ride in a signed HttpOnly `am_oauth` cookie
    (Path `/api/auth/google`, 10 min), not server memory.
  - `GET /api/auth/google/callback` (public) checks state, exchanges the
    code (client_secret_post + code_verifier), checks the ID token's claims
    (iss, aud/azp, exp, nonce, email_verified, allowlist; no signature check,
    since the token comes straight from Google over TLS), then sets
    `am_session` with `email` and 302s to `next`. `next` must be a relative
    `/path` (not `//`, no `\`), else `/`. On failure it 302s to
    `/?login_error=denied|not_allowed|invalid|misconfigured|rate`. Failures
    count against the login rate limiter.
- Endpoints:
  - `GET /api/auth/status` returns `{configured, authenticated, local,
    passwordLogin, google, googleUrl, email}`. `passwordLogin`: the password
    form works for this caller. `google`: the Google button works on this
    page (client stored, publicUrl set, and this Host is publicUrl's).
    `googleUrl`: publicUrl, when Google is set up but this is another host
    (e.g. the LAN IP). `email`: the session's Google account, if any.
  - `GET /api/auth/google` (gated) returns `{configured, publicUrl,
    redirectUri, allowedEmails, passwordLogin, password}`.
  - `PUT /api/auth/google/allowed {emails: [...]}` (gated): 400 on an
    invalid address, 409 when emptying the list while password login is off.
  - `PUT /api/auth/password-login {enabled}` (gated): turning it off gets 409
    unless a Google client, publicUrl and at least one allowed email exist.
  - `POST /api/auth/login {password}` logs in. 5 failures within 15 min
    lock that IP out (429 with `Retry-After`) for 15 min, each further
    lockout doubling up to 1 h; a successful login resets the IP. No global
    cap. Each attempt is counted before the password check, so parallel
    bursts are limited too.
  - `POST /api/auth/logout` signs this device out.
  - `POST /api/auth/logout-all` and
    `POST /api/auth/password {current, new}` need a session or a local
    caller.
- Responses from the gate:
  - remote without a session: 401 `authentication required`;
  - remote while no password is set: 503;
  - a POST/PUT/PATCH/DELETE whose `Origin` host differs from `Host`: 403,
    local callers included (CSRF).
  - Always public: the SPA shell, `/assets` and `/api/health`. There is no
    `/docs`, `/redoc` or `/openapi.json`; the schema is
    `GET /api/openapi.json`, behind the gate.
- `AUTOMANGA_DATA_DIR=<dir>` relocates `data/` (settings, projects, assets,
  auth) for a throwaway second instance.

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
  - `text` — text block; `direction: "horizontal" | "vertical"`; optional
    `strokeWidth` (0-20) + `strokeColor` draw an outline (the SFX look).
  - `bubble` — dialogue balloon: 6 `bubbleType`s (speech/thought/shout/
  whisper/narration/inner-voice), `tailPosition` (`top`/`bottom`/`left`/
  `right`), `direction` h/v, fontSize, colors, optional `speaker` (set by
  assembly from "Name：台词" dialogue).
- **Tail quirk** (inherited from the UI for parity): `tailPosition: "top"`
  renders the tail triangle **below** the bubble pointing down; `"bottom"`
  renders it **above** pointing up. To point a tail at a character below the
  bubble, use `"top"`.
- **Optional bubble lettering fields** (absent = the behaviour above,
  unchanged):
  - `tailTip: {x, y}` — a pointed tail aimed at that point, in fractions of
    the bubble's own box (unrotated; may be <0 or >1, e.g. `{x: 0.3, y: 1.8}`
    = below the bubble, left of centre). Overrides `tailPosition`; thought
    bubbles get three circles; narration has no tail. Validated to -2..3
    (at most 2 box sizes beyond the box); pages saved through
    `/api/projects/save` or `PUT …/composer-pages` are clamped into that
    range, and the renderer clamps too.
    One geometry in `backend/render/tails.py` and
    `frontend/src/components/composer/tailGeometry.ts`, both checked against
    `backend/tests/fixtures/tail_cases.json`.
  - `textAlign: "left" | "center" | "right"` — narration aligns to the box's
    padded edge, other shapes to the edge of the centred text block.
  - `markup: "stars"` — `*word*` is set as emphasis (bold, sheared italic;
    horizontal text only). Opt-in: without it stars are drawn literally.
- **Glyph fallback**: the server renderer draws text run by run through a
  font chain (`fonts.get_font_chain`: the lettering font, then symbol fonts —
  Arial Unicode, Apple Symbols, Segoe UI Symbol, DejaVu — then the CJK/Latin
  system fallbacks), so ♪ or CJK the lettering font lacks no longer render
  as boxes. Needs `fonttools` (in requirements.txt).

## 3. Data model (contract)

Project JSON = `{ id, name, createdAt, updatedAt,
panels: Panel[], composerPages: ComposerPage[], settings }`.

- **Panel** (storyboard cell): `{ id, order?, scene, characters: string[],
  dialogue: string, shot?: "wide|medium|close-up|extreme-close-up|splash",
  location?: "<name in project settings.locations>",
  prompt: { turbo?, tags?, negativePrompt?, seed?, removeBG? },
  image?: "<asset URL or data URL>" }`.
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

Machine-readable schema of the endpoints: `GET http://127.0.0.1:5180/api/openapi.json`
(behind the login gate; local callers pass).

## 4. Golden path (copy & adapt)

```bash
BASE=http://127.0.0.1:5180

# 1. Create a project
PID=$(curl -s -X POST $BASE/api/agent/projects -H 'Content-Type: application/json' \
  -d '{"name":"My Comic"}' | python -c "import json,sys;print(json.load(sys.stdin)['project']['id'])")

# 2. Write the storyboard (you write it — scene/characters/dialogue per cell).
#    Optional per-panel fields:
#    - "shot": wide|medium|close-up|extreme-close-up|splash — camera framing;
#      injected into the image prompt AND used by assembly (close-ups get
#      slimmer balloons; splash panels go solo in plan-pages).
#    - Dialogue lines "Name：台词" (or "Name: ") mark the speaker when Name
#      is in that panel's characters — the bubble records `speaker`, and with
#      2+ speakers in one panel the tails point opposite ways (check preview).
curl -s -X PUT $BASE/api/agent/projects/$PID/panels -H 'Content-Type: application/json' \
  -d '{"panels":[
    {"scene":"Rain-soaked street, girl running","characters":["Yuki"],
     "dialogue":"Yuki：Get away!","shot":"wide"},
    {"scene":"Her face, rain and tears","characters":["Yuki"],
     "dialogue":"I cannot go back...","shot":"close-up"}]}'

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
#    `locations` is the same mechanism for recurring places (a panel opts in
#    via its `location` field); `bible` is a free-text story bible (worldview,
#    recap, established locations/props) — persisted with the project for
#    cross-chapter continuity; read it back via GET .../projects/$PID.
curl -s -X PUT $BASE/api/agent/projects/$PID/settings -H 'Content-Type: application/json' \
  -d '{"style":"chinese ink painting style, muted colors",
       "characters":[{"name":"Yuki","prompt_block":"1girl, white hair, blue eyes, blue kimono"}],
       "locations":[{"name":"rain bridge","prompt_block":"old wooden bridge, heavy rain, lanterns"}],
       "bible":"ch1: Yuki loses the jade pendant on the rain bridge"}'

# 5. Assemble pages: template + slot filling + auto dialogue bubbles
#    (builtin ids: blank, manga-2v/2h/3/4/6/8, grid-12/21/23/32/232/323/223,
#     hero-br-4, hero-br-wide, hero-splash, photo-full, photo-grid-4, photo-grid-9;
#     webtoon long-strip: webtoon-3, webtoon-4-mix, webtoon-6 (800px column pages);
#     dynamic presets: dyn-2-slant, dyn-3-diag, dyn-hero-3, dyn-5-mix;
#     or {"kind":"rows","rows":[2,3]}, {"kind":"user","id":...}, {"kind":"custom",...})
#    "dynamic": true slants every non-hero frame (quadrilateral corners) for a
#     more cinematic page. List all templates + slot counts dynamically:
curl -s $BASE/api/agent/templates
curl -s -X POST $BASE/api/agent/projects/$PID/pages -H 'Content-Type: application/json' \
  -d '{"template":{"kind":"builtin","id":"manga-2v"},"panel_ids":["panel_1","panel_2"],
       "reading":"rtl","name":"ch1-p1","dynamic":true}'
# 5b. Heuristic pagination: chunk imaged panels into pages (splash panels go
#     solo), template picked by slot count; apply=true builds them all:
curl -s -X POST $BASE/api/agent/projects/$PID/plan-pages -H 'Content-Type: application/json' \
  -d '{"panels_per_page":4,"apply":true}'
# 5c. Pages are not append-only: delete a page, or set a new full order
#     (page_ids must be a permutation of all existing page ids):
curl -s -X DELETE $BASE/api/agent/projects/$PID/pages/<PAGE_ID>
curl -s -X PUT $BASE/api/agent/projects/$PID/pages/order -H 'Content-Type: application/json' \
  -d '{"page_ids":["<page2>","<page1>"]}'
# 5d. Cover page: full-bleed art + outlined title, inserted as page 1.
#     Generate art first (POST /generate kind="cover"), or reuse a panel:
curl -s -X POST $BASE/api/agent/projects/$PID/cover -H 'Content-Type: application/json' \
  -d '{"title":"雨桥物语","subtitle":"第一卷","panel_id":"panel_1"}'
# 5e. SFX: styled text elements (fontSize + strokeWidth outline + rotation).
#     Preset onomatopoeia library:
curl -s $BASE/api/agent/sfx-presets

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
  -d "{\"project_id\":\"$PID\",\"format\":\"both\",\"scale\":2,\"page_numbers\":true}"
# → {"pages_dir": "...", "pdf": {"path": "...", "url": "/api/export/download/..."},
#    "zip": {"path": "...", "url": "/api/export/download/..."}}
#    page_numbers stamps bottom-center numbers on every page but the first.
# (format "pdf" or "zip" returns only that key; download URLs are same-origin GETs)
# Once downloaded, delete AutoManga's copy (the file, and its _pages/ folder
# when no PDF/ZIP of that name is left):
curl -s -X DELETE $BASE/api/export/download/manga_1a2b3c4d_20261117_120000.pdf
```

Exports are pruned on every new export: `data/exports/` keeps nothing older
than 7 days and at most the 20 newest exports per project (grouped by the
name's `manga_<project id, first 8>` / `collection_<collection id, first 8>` /
`composer` prefix; other files there are left alone).

### Collections (episodes of a series)

A collection groups projects as the ordered episodes of a series
(`data/collections.json`; a project may be in several; deleting a project
removes it from every collection; ids of vanished projects are skipped with a
warning and reported under `missing`). Single-project export is unchanged.

```bash
curl -s $BASE/api/collections        # [{id, name, description, projectIds, cover, auto,
                                     #   episodes: [{id, name, pages, firstPageId, cover}],
                                     #   missing, pages, coverUrl}]
curl -s -X POST $BASE/api/collections -H 'Content-Type: application/json' \
  -d "{\"name\":\"Jade & Haile\",\"projectIds\":[\"$P1\",\"$P2\"]}"
# full new order (existing projects, no duplicates); cover = the page the
# generated collection cover uses ({projectId, pageId} or null)
curl -s -X PATCH $BASE/api/collections/$CID -H 'Content-Type: application/json' \
  -d "{\"name\":\"...\",\"description\":\"...\",\"projectIds\":[\"$P2\",\"$P1\"],
       \"cover\":{\"projectId\":\"$P1\",\"pageId\":\"$PG\"}}"
curl -s -X DELETE $BASE/api/collections/$CID        # projects untouched
# group "<Title> — <Subtitle>" names (also " - "), or identical names, >= 2
# per title, ordered by "Episode 3" / "Ep. 3" / "Part Two" / "Part II" in the
# subtitle, else by name. Creates/refreshes `auto: true` collections only; a
# collection you created or edited (auto false) is never touched.
curl -s -X POST $BASE/api/collections/auto-group
# → {created: [...], updated: [...], unchanged: [...], skipped: [...], collections}
```

**Collection export** (background job, one at a time → 409 while one runs):

```bash
curl -s -X POST $BASE/api/collections/$CID/export -H 'Content-Type: application/json' \
  -d '{"format":"both","scale":2,"pageNumbers":true,"episodeTitlePages":true,"cover":true}'
# → 202 {id, status:"running", done:0, total:N, warnings:[...]}
curl -s $BASE/api/collections/exports/$JOB
# → {status: running|done|error, done, total, error, warnings,
#    pdf: {url, name} | null, zip: {url, name} | null}
```

`cover` adds a generated page 1 (collection name over the chosen cover page,
else the first episode's first page); `episodeTitlePages` (default on) puts a
generated page before each episode (collection name, the episode's subtitle,
a thumbnail of its first page); `pageNumbers` numbers every page
continuously across the collection, the cover excepted. Titles use font
family `title` when `data/fonts/` has one. Pages render one at a time, so
length does not matter. Files are `collection_<id8>_<timestamp>.pdf|.zip` in
`data/exports/`, pruned like other exports and deletable with
`DELETE /api/export/download/{name}`. Episodes whose project is missing or
has no pages are skipped (listed in `warnings`). MCP: `list_collections`,
`export_collection` (waits for the job).

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

**Per-character LoRAs**: a character in the global library (`data/characters.json`,
`GET/PATCH /api/characters/{id}`) may carry `lora: {name, weight, trigger}` —
`name` is SwarmUI's LoRA name relative to `Models/Lora` without extension
(`SecondFloor/sf_nova`), `weight` defaults to 0.8, `trigger` (null = the file
name without `_`, `sf_nova` → `sfnova`) is the trained trigger word. PATCH
validates it (`null` or a name-less entry clears it); the Characters tab sets
it from a dropdown. For every panel character with a LoRA, generation adds its
trigger word to the prompt and its LoRA to the request — full weight on a
one-character panel, 0.6 × weight when the panel lists several — merged with
the request's/global `loras` by name (the panel character's weight wins). A
LoRA the prompt already tags (`<lora:SecondFloor/sf_nova:0.8>`, as converted
comic panels carry) is not added twice. Each one is recorded in `injected` as
`{"kind":"lora","text":"<lora:name:w>","name","weight","trigger"}`. It applies
to `/api/agent/generate` (with `inject_characters`) and to
`/api/assets/swarmui/generate` (from its `project_id`/`panel_id`).
`GET /api/assets/swarmui/loras` lists the installed LoRAs as
`{"loras":[{name, trigger, architecture}]}` (trigger from the model's
`trigger_phrase` metadata, else the name convention).

**Character-sheet references (IP-Adapter)**: a library character with a sheet
(`image`) and `refWeight` (0-1; missing/null/0 = off — an explicit opt-in,
PATCH rejects anything else with 422, 0 is stored as null) guides its **solo**
panels through SwarmUI's IP-Adapter: generation sends the sheet as
`promptimages` (`|`-joined data URLs) with `useipadapter` = the preset from
`settings.swarmui.ipadapterPreset` (default `PLUS (high strength)`; FaceID is
not used), `ipadapterweight` = refWeight, `ipadapterweighttype` =
`settings.swarmui.ipadapterWeightType` (default "prompt is more important") and
`ipadapterend` = `settings.swarmui.ipadapterEnd` (default 0.7). Those defaults
come from a seed-matched A/B on arthemyComics: "standard" over every step
burnt colours and pulled the pose toward the sheet; prompt-first weighting
released at 70% keeps the scene and inking and still carries face, hair and
outfit details (0.5 is a good refWeight). Panels listing several people
never get one (a single reference blends faces). A project entry
(`settings.characters[]`) may override `refWeight`/`image`; sheets are read
only from data URLs or `/api/assets/file/<id>`; the Characters tab uploads and
generates sheets into the asset store (`POST /api/assets/file`, kind
`character`) and keeps the URL, and `POST /api/characters/migrate-images`
moves remaining data-URL sheets out of `data/characters.json`
(→ `{migrated, failed}`, idempotent). Library and per-project character
images count as references for the startup orphan-asset cleanup. The
preset, weight type and end are in the Settings tab ("IP-Adapter"; weight
type one of `standard`, `prompt is more important`, `style transfer`).
`swarm_client.generate_image`
takes `prompt_images` / `ipadapter` / `ipadapter_weight` /
`ipadapter_weight_type` / `ipadapter_end` and sends nothing IP-Adapter unless both images and a
preset are given; `promptimages` is redacted in the payload log. Applied by
`/api/agent/generate` (recorded in `injected` as
`{"kind":"reference","name","weight","preset"}`, and as `ipadapter` in the PNG
metadata) and `/api/assets/swarmui/generate`.
`GET /api/assets/swarmui/features` → `{"ipadapter": bool, "presets": [...],
"preset": "<configured>"}` (a running backend with SwarmUI's `ipadapter`
feature; presets from `/API/ListT2IParams` `useipadapter`, cached 60 s); the
Characters tab's "Guide panels with sheet" slider is disabled when it is
false. SwarmUI downloads the IP-Adapter model and CLIP-Vision encoders
(~6.6 GB) on the first such generation; after that a referenced panel costs
about 12% more time than a plain one (62 s vs 55 s at 1024², 28 steps).

**Consistency & continuity tools**: fixed seeds make style-reproducible runs;
`init_image` (+`init_creativity` 0-1) runs img2img against an asset or data
URL — feed the previous panel (low creativity ~0.4-0.6) or a character sheet
in for continuity; `mask_image` (requires `init_image`) inpaints only the
masked region (mask semantics follow SwarmUI). `settings.locations` blocks
are injected for panels naming a location (`panel.location`), same mechanism
as character blocks.

**Print resolution / local upscale**: `GET /api/agent/inference-models` and
`POST /api/agent/upscale {asset_url, model, tile}` run a local ONNX x4
upscaler (Real-ESRGAN; models download on first use into data/models/).
Optional dependency: `pip install -r backend/requirements-inference.txt` —
without it the endpoint answers 503. Preview/export scale clamps at 8
(600x900 @8 = 4800x7200). Generated PNGs embed their full recipe as tEXt
chunks (`parameters` text block + `automanga` JSON) so any export stays
reproducible outside the asset index.

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

### Content rating (SFW default, opt-in Mature) and minor protections

Every generation path — `/api/agent/generate` and `/generate-batch` (so the
MCP `generate_image`/`generate_batch` tools and `agent_cli`), the Assets tab's
`/api/assets/swarmui/generate`, the Characters tab's sheet
`/api/characters/templates/generate-image` and the LoRA dataset generator —
runs through one function, `backend/content_rating.py` `apply_rating`, right
before SwarmUI is called.

- **The rating.** `data/settings.json` → `content.defaultRating`
  (`"sfw"` by default, or `"mature"`; Settings → Content rating, or
  `POST /api/settings/ {"content": {"defaultRating": "..."}}`) applies to
  generations without a project and to projects that set none. A project's
  own `settings.contentRating` (`"sfw"` | `"mature"`) wins:
  `PUT /api/agent/projects/$PID/settings {"contentRating": "mature"}` (`""`
  unsets it; anything else is 400), or the rating selector on its Showcase
  card. A character sheet uses the rating of the project it is generated for
  (the Characters tab sends none: the default). The LoRA dataset generator is
  **always SFW**.
- **Character ages.** Library characters have `age` (whole number 0-120, or
  `null` = unknown; Characters tab "Age", `PATCH /api/characters/<id>
  {"age": 34}`; 422 outside 0-120). A project entry in `settings.characters[]`
  may carry `age` too (it wins). A character is a **minor** if its age is
  under 18, or its name/appearance/description/prompt block reads as a minor
  ("N years old" / "N-year-old" / "aged N" / "N yo" with N < 18, or teen,
  teenage, kid, child, toddler, baby, schoolgirl, schoolboy, loli, shota,
  young girl/boy, little girl/boy, middle school, high school student,
  minor, ...; a minor description wins over an adult age). It is an
  **adult** if not a minor and its age is 18+, or its text says
  "N years old" with N >= 18 or "adult". Otherwise its age is **unknown**.
- **SFW** generations get `nsfw, nude, naked, nipples, cleavage, underwear,
  lingerie` added to the negative prompt (prompt otherwise unchanged).
- **Mature** generations drop those, and always get `adult, mature adult`
  in the prompt and `child, loli, shota, childlike, teen, young, underage,
  petite child body` in the negative — but only when every character on the
  panel (`panel.characters`, resolved like the LoRA/prompt-block injection)
  is a known adult and the panel's scene mentions no minor. A panel with a
  minor or a character of unknown age (or not in the library) is **forced to
  SFW**; the response carries `"notice": "forced SFW: Kim has no age ..."`
  and the `injected` list a `{"kind": "rating", "rating": "sfw",
  "requested": "mature", "forced": true, "notice": ...}` entry. Set the
  character's age to fix an unknown one.
- **Refusals.** In mature mode a prompt that mentions a minor (the terms
  above, "16 years old", "teenage", "schoolgirl", "underage", "preteen", ...)
  is refused with **HTTP 400** and a message naming the words — never
  silently rewritten. `/generate-batch` checks every job up front (400
  `job <i>: ...`).
- Every response and asset records the outcome: `content_rating` in the
  `/generate` response, the asset metadata (`GET /api/agent/assets/<id>`,
  with the `negative_prompt` actually sent) and the PNG's parameters.
- Showcase: mature projects show a "Mature" badge and blurred covers until
  clicked (once per browser session); the collection export dialog notes
  mature episodes (`/api/collections` episodes carry `contentRating`, the
  collection `mature`).
- Negative prompts reduce what a model draws; they do not guarantee it.
  Check mature output yourself.

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

### 9b. Comics scripts (the Comics tab, `/api/comics`)

`.comic` scripts live in the Comics repo (`$COMICS_DIR`, default
`~/Projects/Comics`, `scripts/<name>.comic`); a run calls its `automanga.js`,
which paints with comic.js and rebuilds the project here. Names are
`[A-Za-z0-9][A-Za-z0-9_-]*`.

- `GET/PUT /api/comics/scripts[/{name}]` list, read, save (`{text}`; 409
  while that script is being converted).
- `POST /api/comics/scripts/{name}/plan {text?, face?}` → `comic.js --plan`
  (`--stdin` when `text` is given, so unsaved text can be checked; the script
  need not exist then). Read-only, allowed during a run, 20 s timeout. Returns
  `{ok:true, panels:[{id, page, n, line, seedLine, seed, seedPinned, gen,
  model, face, prompt, negative, fix, painted, current, prev, mtime,
  variants:[{seed, same}]}]}` or, for a script error, `{ok:false, error,
  line}` (HTTP 200 either way). `current` = painted from this prompt/seed;
  `same` = the variant was painted from the current prompt, so pinning its
  seed reuses the picture.
- `POST /api/comics/runs {script, mode, face?, panels?, force?, variants?, uncut?}`,
  one run at a time (409), detached; poll `GET /api/comics/runs/current?since=N`,
  stop with `POST /api/comics/runs/current/stop`. Modes: `paint`,
  `no-paint`, `dry-run`, `repaint` (`--panels a,b [--force]`; without
  `force` only stale panels are painted and a variant pinned with
  `PANEL seed=` is copied in: the log says `from variant seed=`), `variants`
  (`--panels a,b --variants N`, N 2-8: paints seeds into `out/<name>/variants/`
  and imports nothing). `panels` are ids like `"1.2"`.
- `POST /api/comics/scripts/{name}/rewrite {text, start, end, action,
  instruction?, model?, remove_todo?}` (`backend/api/comics_rewrite.py`, the
  editor's "AI rewrite"): the configured LLM (`OpenAIClient.for_request`,
  stored endpoint/key, `model` overrides; temperature 0.7, max 4096 tokens,
  5 min timeout) rewrites `text[start:end]` (UTF-16 offsets, as a textarea
  gives them; unsaved text is fine, nothing is saved). `action`:
  `tighten_dialogue` | `enrich_description` | `draft_uncut` (only inside a
  `PAGE uncut`/`PANEL uncut` block; keeps `todo` unless `remove_todo`) |
  `custom` (needs `instruction`, ≤ 2000 chars). The model gets the header,
  the block and 40 lines around it. Minor protection: for `draft_uncut`, any
  uncut block and any block of a `rating: mature` script, the block's panels
  are planned as uncut panels (`comic.js --plan --stdin --uncut`) BEFORE the
  model is called; a minor, an unknown age or a plan error → 400 and nothing
  is sent. Returns `{suggestion, original, plan: {ok, error, line}, model,
  durationMs}`: `plan` checks the text with the block replaced (`--uncut`
  when the script has uncut blocks) plus the same minor check on the new
  block; a failing suggestion is still returned, flagged. LLM failures → 502
  with a hint (endpoint must end in `/v1`; model crashed in LM Studio).
  Concurrent calls are allowed.
- Images: `GET /api/comics/scripts/{name}/file/page_01.png` (or `draft_01`),
  `/panel/p01-02.png` (`p01-02.prev.png` = the one it replaced),
  `/variant/p01-02_seed4301.png`.

Content rating: a script's `rating: sfw|mature` header (default sfw; a
panel's `rating: sfw` keeps one panel SFW) and `age NAME: <n>` lines follow
the same rules as here (Comics README); `automanga.js` sets the project's
`contentRating` to the script's rating and fills a library character's `age`
from the script when it has none. A mature script's `--plan` panels carry
`rating` (and `notice` when forced SFW).

Uncut editions: a script's `PAGE uncut` / `PANEL uncut` blocks (Comics README,
"Uncut editions") make a second comic, built by `comic.js --uncut` into
`out/<name>-uncut/` and imported as its own project, "<Title> (Uncut) —
<Subtitle>", marked `comicScript: "<name>:uncut"` and rated `mature`. Runs and
`/plan` take `uncut: true` (→ `--uncut`; uncut panel ids `1.u1` / `u1.2` need
it), the page/panel/variant file routes take `?uncut=1` (uncut files
`p01-u01.png`, `u01-02.png`). `--plan --uncut` panels add `edition`, `stem`,
`regular` (copied from the regular edition), `rating`, `notice`, and the plan
lists `slots` (todo slots). The script listing adds `uncut`, `uncut_slots` and
`uncut_project_id`. Collections auto-group puts uncut editions in their own
collection "<Title> (Uncut)" (stored `mature: true`), never with the regular
episodes.

Pick a variant: `variants` run → set the seed in the script (`seed: N` line if
the panel has one, else `PANEL … seed=N`) → `PUT` the script → `repaint`
without force.

### 9c. LoRA training (Characters tab "Train LoRA", `/api/training`)

Character LoRAs are trained on the Razer (ai-toolkit, the sf_* SDXL recipe)
over ssh/scp; setup and troubleshooting: `docs/TRAINING.md`. Settings live in
`data/settings.json` → `training {host, os, toolkitDir, python, baseModel,
loraFolder, sampling, resolution, cacheTextEmbeddings}` (Settings tab "LoRA
training" or `POST /api/settings/ {"training": {...}}`, validated;
`GET /api/training/settings` shows them). `resolution` (default `[512, 768]`)
is the dataset bucket list: 1024 ran out of memory on the 8 GB RTX 3070 with
full-size panels.

- Datasets: `data/training/<slug>/img_NNN.png` + `img_NNN.txt` (the trigger
  word only) + `meta.json`. `GET/POST /api/training/datasets`
  (`{slug, trigger, characterId}`; `?character_id=` filters),
  `GET /api/training/datasets/{slug}`, `POST …/upload` (multipart `files`),
  `POST …/import {projectId, panelIds?}` (project panels),
  `DELETE …/image/img_003.png`, `POST …/generate {count, characterId?}`
  (background, LoRA-free, the character's appearance over a
  pose/angle/expression/shot grid, seeds 1000 + i·7919; status in the
  dataset's `generation`), `POST …/generate/stop`.
- Jobs: one at a time, ≥ 15 images. `POST /api/training/jobs {slug, name?,
  characterId?, steps (1500), resume?}` → poll `GET /api/training/jobs/current?since=N`
  (`phase` pushing → launching → running → finishing → done | failed |
  stopped, `step`/`steps` from the tqdm bar, `lines`/`next`/`partial` log,
  `events`) → `POST /api/training/jobs/current/stop`. On success the LoRA is
  at `~/SwarmUI/Models/Lora/<loraFolder>/<name>.safetensors`, SwarmUI's list
  is refreshed and the character gets `lora {name:"Comics/<name>", weight:0.8,
  trigger}`; in a script: `lora NAME: Comics/<name> 0.8 <trigger>`. An
  existing file is never overwritten: the pull goes to `<name>_2` (`_3`, …)
  and the character's lora uses that name (see the job's `lora`). A job
  whose collection failed (`failed`, `collectable: true`) is retried with
  `POST /api/training/jobs/current/collect`.
- Limits: 25 MB per image, 200 images per dataset (413 / 400); undecodable
  images or bad base64 → 400.
- Restart-proof: the job is in `data/training_job.json` and runs detached on
  the trainer; a restarted server resumes polling it. Interrupted while
  pushing → `failed`, start again; while launching, the job is adopted from
  the pid the launcher wrote to `<log>.pid` (or `failed` if it never
  started). Each job has its own remote dir
  `~/automanga-training/<name>/<job id>/`. A name whose `output/<name>` already has
  checkpoints is refused unless `resume: true` (ai-toolkit would continue it).

## 10. Making a comic a stranger can READ (craft rules)

Everything above moves pixels; it does not guarantee a readable comic. A
mechanically clean first production run still failed real readers on four
fronts: story jumps (scene cuts with no captions), bubbles covering faces,
bubble-style overload, and appearance drift (one hero, two beard colors; two
of him in one panel). The full playbook — reader test, storyboard grammar
(establishing shots, character intros, caption plan), the character
consistency protocol (rigid prompt blocks, one-instance-per-panel, extras
guarding, img2img chaining), lettering discipline (style budget, ≤14 char
bubbles, never cover a face, vertical-text quirks) and a 7-point visual QC
checklist with fix recipes — lives in `skills/manga-maker/SKILL.md` §0-§7.
Read it before authoring panels; its rules are stated as comic-craft
requirements, not API options. The two rules that pay off most:

- **Caption every scene change** (`bubbleType:"narration"`) — 「长安·卦摊」,
  「是夜·唐宫」. The reader does not know your script.
- **Prompt for negative space** where bubbles will go (「画面上方留白」) and
  keep bubble bodies off faces; a bubble may touch the speaker's head with
  its tail, never cover the face.
