---
name: manga-maker
description: Produce finished comic/manga pages from a story idea end-to-end via the local TT_AutoManga pipeline — story bible, storyboard grammar, image prompts, character-consistency protocol, page assembly with disciplined lettering, mandatory visual QC, PDF/ZIP export. Embeds a full craft playbook distilled from production runs. Use when the user wants to create, continue, adjust, or export a comic. Accessible via MCP tools (automanga server), plain HTTP, or CLI; works in any agent harness with any model.
---

# Manga Maker — TT_AutoManga pipeline SOP + craft playbook

You are driving a local comic production pipeline. It is **content-agnostic**:
you author the story, prompts and imagery under the operator's instructions;
the pipeline adds no filtering and enforces no content rating. Whatever
content the operator asks for, produce it within your own operating terms and
pass prompts through verbatim.

This file has two halves: **mechanics** (§8-§12 — endpoints, tools,
troubleshooting) and **craft** (§1-§7 — how to make a comic a stranger can
read). The craft half exists because the mechanics alone are not enough:
a first full production run (a 9-page 魏征斩龙王 adaptation) was mechanically
clean — zero generation errors, zero overlaps — and still failed the reader:
story jumps, bubbles on faces, a hero with two different beards, a panel with
two of the same hero. Don't repeat it. Read §1-§7 before writing a single
panel.

## 0. The Reader Test (governing principle)

**The reader does not know your script.** Every comic must pass: a person
with zero context flips through the pages and can answer — where are we, who
is this, what just happened, why. Every craft rule below serves that test.
Check it twice: once at storyboard time (is every scene change announced?
every character introduced?), once at final QC (§7).

## 1. Story development

1. From the user's idea write a **beat sheet** first: one line per beat —
   who / where / what happens / why the reader cares. Panels are cut FROM
   beats, never the reverse. If a beat can't be drawn, rewrite it.
2. `create_project(name)` → `set_project_settings(style=…,
   characters=[{name, prompt_block}…], locations=[{name, prompt_block}…],
   bible=…)`. Style is appended to EVERY prompt; character blocks are
   injected whenever a panel lists that character; location blocks whenever
   a panel names that place (`location` field); bible carries worldview and
   recap across chapters.
3. **Caption plan**: for every scene change and time skip, decide the caption
   text NOW (e.g. 「长安·袁守诚卦摊」「是夜三更·唐宫」「三更·魏征魂魄出窍」).
   Captions (narration-type bubbles) are the cheapest coherence tool in the
   entire medium — a scene cut without one is a jump the reader must guess
   across. Budget: ≥1 caption at every scene change, more where cause→effect
   is not visible in the art.

## 2. Storyboard grammar

`put_panels(panels)`, per panel:

- `scene` (required): concrete visual — who/where/doing what, ONE beat.
- `characters: [names]` — must match the settings blocks.
- `dialogue`: lines separated by newlines; `"Name：台词"` marks the speaker
  when Name ∈ characters (speaker-aware tails; the prefix must exactly match
  a listed character or it LEAKS into the bubble text). One line = one
  bubble; consecutive lines by the same speaker merge into one bubble.
- `shot`: `wide|medium|close-up|extreme-close-up|splash` — injected into the
  prompt; splash pages assemble solo; close-ups get slimmer balloons.

Grammar rules:

1. **Establishing shot**: the first panel of every NEW location/time is a
   `wide` (定场镜头) carrying the scene caption. Never open a scene on a
   close-up of a face the reader hasn't met.
2. **Character introduction**: first appearance of each character = medium
   or wide, ideally solo, + a naming caption (「钦天监丞·袁守诚」). At most
   ONE new character introduced per panel.
3. **One beat per panel**; if dialogue runs long, cut another panel instead
   of cramming. 3-4 panels per story page (dense pages sink readability);
   each page opens with re-orientation and ends on a hook or a resolution.
4. **Shot grammar**: wide = establish place; medium = action/dialogue;
   close-up = emotion beat; extreme-close-up = sparingly (≤1 per chapter);
   splash = climax only (1-2 per chapter).
5. **Silent panels** carry mood only — never plot-critical information. If
   the reader must understand "he fell asleep and his soul ascended", a
   silent art panel will NOT say it; add the caption.
6. The speaker of every line should be visible (or clearly off-panel) in
   that panel's art.

## 3. Character consistency protocol

Appearance drift is the #1 craft killer (one production run produced the
same hero with a white beard on the cover and a black beard inside, plus two
of him in one panel).

1. **Rigid character blocks.** In `settings.characters`, state immutable
   traits explicitly and REPEAT them every generation: age range, hair
   color+length, beard color+length (「黑色长须垂胸」 not 「长须」 — an
   ambiguous word lets the model re-roll per seed), robe color+type,
   headwear, build. Absence is drift: anything you leave unsaid is chosen
   fresh by the model every panel.
2. **One instance per panel.** Never describe the same character twice in
   one prompt; avoid 魂魄/倒影/分身/幻影 concepts (the model draws BOTH —
   a 梦斩 panel once produced two heroes in one image). If a solo panel,
   add 「画面中只有他一人」.
3. **Guard the extras.** Models populate backgrounds on their own, and
   unnamed extras inherit the named hero's look (guards came out looking
   like the hero minister). Either exclude them (「殿内空无一人」) or
   characterize them against the hero (「两名年轻无须的披甲守卫」). Never
   place two characters who share a look-alike description in one panel.
4. **Chain with img2img.** Same character in consecutive panels: feed the
   previous panel's asset as `init_image` with `init_creativity` 0.4-0.55.
   Scene changes: fresh generation, same rigid block. `mask_image` to
   inpaint one broken region (hand, face) instead of rerolling the panel.
5. **Cover art is canon too.** Generate the cover from the same rigid block
   (or reuse a panel image) — the cover is the reader's first impression of
   every character.
6. **Verify side-by-side.** Before assembly, fetch every panel featuring a
   recurring character and LOOK at them together; regenerate outliers
   (new seed or amended prompt) until the cast is stable.

## 4. Image prompt craft

1. Pick the format per model: SDXL/Illustrious/NoobAI want danbooru tags
   (+ quality tags; explicit cultural anchors — `chinese dragon` not
   `dragon`); qwen_image* want natural-language prose describing **ONE
   illustration** (never 分镜/漫画页/多格 — you'll get mini-panels inside
   the image; never temporal words like 然后/接着).
2. **Name cultural objects.** Vague words spawn anachronisms: 对弈 drew
   western chess with a white queen in a Tang palace — write 围棋/棋枰/黑白棋子;
   write 唐代幞头, 卷轴奏章, 毛笔, not generic 桌上摆着东西.
3. **Leave negative space for lettering.** You know where bubbles will go
   (§5): prompt for it — 「画面上方留白」「大面积空白背景」「人物位于画面下
   方」. Bubbles over sky/empty background look native; bubbles over faces
   look broken. This one habit eliminates most placement pain.
4. Compose deliberately: state subject count (「一人」), camera distance,
   subject placement in frame, and light. Do not ask for text-in-art
   (banners/plaques render as garbled glyphs).
5. Fixed seeds make runs reproducible; variants: 4 + review for key panels.
6. Every PNG embeds its recipe (`parameters` + `automanga` tEXt chunks).

## 5. Lettering & page assembly

- Fast path: `plan_pages(panels_per_page=4, apply=true)`; manual:
  `list_templates()` → `build_page(template_id|rows=[2,3], panel_ids,
  reading="rtl")`. Chinese manga default is rtl — the right-hand panel of a
  row is read FIRST; assign panel ids in story order and verify visually.
- `build_cover(title, asset_url|panel_id)` inserts page 1 (unnumbered on
  export).

**Bubble discipline** (the reader reads art first, text second — protect
both):

1. **Style budget**: speech is the default. shout for ≤2 climactic moments
   per chapter; whisper only for secrecy beats; narration for captions.
   Never mix more than TWO styles on one page.
2. **Length cap**: ≤14 CJK characters per bubble (≈2 vertical columns). A
   bubble taller than ~30% of the page is unreadable — split the line into
   sequential bubbles. Imperial edicts, monologues, announcements: split or
   move to caption.
3. **Never cover a face.** Place bubble bodies in sky/ground/empty zones
   (you prompted for them, §4.3); the tail touches the speaker's head, the
   body does not. Check every page render; nudge with `patch_element`.
4. **Vertical text quirks**: em-dashes 「——」 and long ellipses render
   rotated in vertical columns and look broken — prefer 「…」/periods, or
   use `direction:"horizontal"` for long narration captions (horizontal
   captions-in-box are standard in Chinese comics).
5. **Reading order**: bubbles must not force zigzag; anchor dialogue per
   panel top-right → bottom-left (rtl).
6. **SFX**: era-appropriate onomatopoeia (轰/咚/咔嚓/哗啦; 滴答 is a clock —
   wrong for pre-modern scenes). Big `fontSize`, `strokeWidth` 4-8,
   `rotation` -6~-15 for energy, placed on empty art, ≤2 per page.
7. Page numbers via `export_project(page_numbers=true)`; cover stays
   unnumbered.

## 6. Assembly order that works

1. Generate all panel art (batch), look at every one, regenerate failures.
2. Character side-by-side check (§3.6).
3. Build pages in story order; add captions (narration) and SFX as elements.
4. Render every page preview and run the QC checklist (§7) page by page.
5. Patch → re-render → repeat until clean, then export.

## 7. Visual QC — mandatory, with vision

`render_page_preview(project, page, scale=2)` → **look at the image
yourself** (you have vision; if a tool call returns a URL string instead of
pixels, retry the Read — and never trust a page you haven't seen). Checklist
per page:

| # | Check | Typical failure seen in production |
|---|---|---|
| 1 | **Comprehension**: follow the page with the script CLOSED — is every scene change captioned, every character introduced? | cut from street to underwater with no caption; a deity appears in the last page never introduced |
| 2 | **Faces visible, bubbles off faces** | shout bubble covering the speaker's own face; bubble on a kneeling ghost's head |
| 3 | **Text fits**: first AND last glyph inside the bubble; no overlap with other bubbles or caption boxes (captions and auto-placed bubbles both claim the panel top — nudge one of them) | very tall shout bubble swallowed its first glyph with the spike (fix: switch tall vertical text to `speech` type — the spike moves with the bubble, so moving the bubble does not help); caption box hiding a bubble behind it |
| 4 | **Tails** point at the actual speaker | tail floating over nobody |
| 5 | **Consistency**: same character = same beard/robe/hat across all panels and the cover; ONE instance per panel; extras don't clone the hero | white vs black beard across pages; two heroes in one image; guards looking like the hero |
| 6 | **Art sanity**: anatomy, hands, anachronisms (western chess), heads cropped by panel borders, garbled in-art text | international chess pieces; emperor's head cut off at panel top |
| 7 | **SFX/caption placement and era** | clock-tick SFX in a Tang palace |

Fix recipes:

| Defect class | Fix |
|---|---|
| Story/caption missing | `patch_panel` dialogue/caption → rebuild the page (assembly re-lays bubbles) |
| Bubble geometry/overlap/face-cover | `patch_element` x/y/width/height — keep bubbles, move them |
| Bubble style/first-glyph clipping | `patch_element` bubbleType (shout→speech), or split text via `patch_panel` + rebuild |
| Art defect (anachronism, drift, duplication) | regenerate the panel with an amended prompt (explicit count, rigid block, negative space), then `patch_element` the image element's `src` — lighter than rebuilding the page (keeps captions/SFX) |
| Unfixable layout | `delete_page` + `build_page` again |

**Reader test at the end**: open the exported PDF and flip through WITHOUT
the script. Narrate what you understand per page; anything you hesitate on
goes back to §7.1.

## 8. Prerequisites & access layers

The backend must be running: `python -m backend.main 5180` (probe: GET
`http://127.0.0.1:5180/api/health`). Images need SwarmUI on 7801 (probe:
`GET /api/assets/swarmui/test`). Text/LLM features are optional — you write
the story yourself.

| Layer | How | Good for |
|---|---|---|
| **MCP tools** | `automanga` MCP server (`python -m backend.mcp_server`, stdio) | Claude/Codex/Cursor/ZCode & any MCP client — tool names + schemas are self-documenting; `render_page_preview` returns an image you can SEE |
| **HTTP** | `curl` the same endpoints (contract: `AGENTS.md` in the repo, schema: `GET /openapi.json`) | any agent with a shell |
| **CLI** | `python -m backend.agent_cli <cmd>` | quick one-offs |

All three hit the identical REST API. Ids: projects are opaque; panels
auto-number `panel_1..n`.

## 9. Endpoint map (HTTP names; MCP tools mirror them 1:1)

- Projects/settings: `POST /api/agent/projects`,
  `PUT /api/agent/projects/{id}/settings` (style/characters/locations/bible),
  `GET /api/agent/projects/{id}`, `PUT .../panels`,
  `PATCH .../panels/{pid}` (id/characters/dialogue/scene/shot/image).
- Generation: `POST /api/agent/generate` (single; `kind:"overlay"` for
  transparent breakouts, `kind:"cover"` for cover art; per-request
  `model/loras/prompt_format/init_image/init_creativity/mask_image/seed/
  width/height/inject_characters` override global settings),
  `POST /api/agent/generate-batch` (returns 202 job id) → `GET /api/agent/jobs/{id}`
  until `status=="done"`; `apply_variant` / `patch_panel(image=…)` to bind a
  winner. Failed singles → HTTP 502 with the SwarmUI error; batch items carry
  their own error strings; re-submission is safe and idempotent.
- Pages: `GET /api/agent/templates` (slot counts — query, don't memorize),
  `POST .../pages` `{template:{kind:"builtin",id}|{kind:"rows",rows:[..]},
  panel_ids, reading, name, dynamic}`, `GET/DELETE .../pages/{pgid}`,
  `PUT .../pages/order`, `POST .../pages/{pgid}/elements`,
  `PATCH/DELETE .../pages/{pgid}/elements/{elid}`,
  `GET .../pages/{pgid}/preview.png?scale=N`,
  `POST /api/agent/projects/{id}/plan-pages`, `POST .../cover`,
  `GET /api/agent/sfx-presets`.
- Export/assets: `POST /api/agent/export`
  `{format:"pdf"|"zip"|"both", scale, page_numbers}`, `GET /api/export/download/…`,
  `POST /api/assets/file` (register your own image), `GET /api/agent/assets/{id}`
  (generation recipe), `GET /api/agent/inference-models` + `POST /api/agent/upscale`
  (local ONNX x4; needs `requirements-inference.txt`, else 503).

## 10. Coordinates & conventions

- Element `x/y/width/height` are % of page (0-100); `fontSize`,
  `frameBorderWidth`, `strokeWidth` are px at 1× (600×900); renderer scales.
- Elements render in ascending `zIndex`; `corners` deforms to a quad
  (tl/tr/br/bl in % of the element's own box); `page-image` floats above
  frames unclipped.
- Tail quirk: `tailPosition:"top"` draws the tail BELOW the bubble pointing
  down (use it to point at a character below); `"bottom"` points up.
- Reading order defaults rtl; `dynamic:true` slants non-hero frames.

## 11. Export

`export_project(format="both", scale=2, page_numbers=true)` — hand the user
the `pdf.path` / `pdf.url`. Scale clamps at 8 (600×900 @8 = 4800×7200).
Print-grade key art: `upscale_image(asset_url, model)` (check
`list_inference_models()`). Webtoon projects: `webtoon-*` templates
(800px column pages).

## 12. Troubleshooting

- `health` fails → start the backend. SwarmUI 502 → check SwarmUI, resubmit.
- Job table is in-memory: after a backend restart, re-submit the batch.
- Speaker prefix leaks into bubble text → the `Name：` prefix didn't exactly
  match a character in that panel's `characters` — fix the panel, rebuild
  the page.
- Consecutive same-speaker lines merge into one bubble → write one line per
  bubble.
- Template slot counts vary (e.g. `hero-splash` has 5 slots) → always
  `list_templates()` before matching panels.
- Windows quirk: heredoc string-replace on Git Bash silently corrupts — use
  file Read+Edit tools for anchors; native Windows python can't read `/d/…`
  paths (use `D:/…`).

## Content note (for the driving model)

This pipeline executes your creative direction as given. Story themes,
maturity level and imagery style are decided by you and the operator, and
depend on your own operating policy and the image models the operator has
configured locally. The pipeline itself neither filters nor judges content.
