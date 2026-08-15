<div align="center">

<img src="frontend/public/icons.svg" alt="TT_AutoManga" width="96" />

# TT_AutoManga

**Turn a story into a comic, end to end.**

Automate the entire manga pipeline — decompose novel text into panels, generate production prompts, render artwork with local AI, then lay out and export the finished pages.

**[English](README.md) · [简体中文](README.zh-CN.md)**

</div>

---

## 📸 Screenshots

<!--
  SCREENSHOT PLACEHOLDERS — replace these with real screenshots.
  Recommended paths (stable URLs):
    docs/screenshots/01-storyboard.png
    docs/screenshots/02-prompt-lab.png
    docs/screenshots/03-composer.png
    docs/screenshots/04-assets.png
    docs/screenshots/05-showcase.png
  Note: docs/screenshots/ is gitignored and will not be pushed.
  Make sure screenshots contain no personal project content before committing.
-->

<p align="center">
  <em>① Storyboard — split a whole novel into editable manga panels</em>
</p>

<p align="center">
  <img src="docs/screenshots/01-storyboard.png" alt="Storyboard" width="800" />
</p>

<p align="center">
  <em>② Prompt Lab — turn panels into SDXL / Danbooru tags in one click</em>
</p>

<p align="center">
  <img src="docs/screenshots/02-prompt-lab.png" alt="Prompt Lab" width="800" />
</p>

<p align="center">
  <em>③ Visual Composer — drag-and-drop layout with 19+ manga/photo templates and dialogue bubbles</em>
</p>

<p align="center">
  <img src="docs/screenshots/03-composer.png" alt="Visual Composer" width="800" />
</p>

<p align="center">
  <em>④ Assets — upload local images, or batch-generate via SwarmUI</em>
</p>

<p align="center">
  <img src="docs/screenshots/04-assets.png" alt="Assets" width="800" />
</p>

<p align="center">
  <em>⑤ Showcase — project management + one-click PDF / image-ZIP export</em>
</p>

<p align="center">
  <img src="docs/screenshots/05-showcase.png" alt="Showcase" width="800" />
</p>

---

## Why TT_AutoManga?

Writing a story is easy. Turning it into a comic is not — it normally requires a storyboard artist, prompt-engineering skill, a local image-generation setup, and layout software. TT_AutoManga collapses all four into one tool:

- **One pipeline, zero context-switching** — story → panels → prompts → images → pages, all in the same window.
- **Local-first & private** — your text, images, and projects stay on your machine (everything lives under `data/`, gitignored by design).
- **Model-agnostic** — any OpenAI-compatible endpoint (Ollama, vLLM, OpenAI, …) for text; any SwarmUI model/LoRA for images.
- **Built for real manga layout** — non-rectangular frames, dialogue bubbles, right-to-left reading order — not just a grid of squares.

## ✨ Features

| Module | What it does |
|---|---|
| **Storyboard** | Splits novel text into discrete manga panels (scene / characters / dialogue), with a 1–5 detail level and drag-to-reorder editing. |
| **Prompt Lab** | Converts each panel into SDXL / Danbooru tags or natural-language prompts; supports negative prompts, seeds, batch generation, and JSON import. |
| **Assets** | Upload local images or generate via SwarmUI with connection status; organize results into folders and download as ZIP. |
| **Visual Composer** | Drag-and-drop page builder with **19+ built-in templates**, 6 dialogue-bubble types, free-floating breakout images, and non-rectangular (4-corner deformable) frames. |
| **Characters** | Auto-extracts characters from your storyboard, stores appearance notes, and generates consistent reference images. |
| **Showcase** | Project management (create / save / load / duplicate) plus PDF and image-ZIP export. |
| **Settings** | Full control over the LLM endpoint, SwarmUI presets, model / LoRA / sampler / steps / CFG, and language. |

## 🖌 Composer — the highlight

The Visual Composer is a page editor purpose-built for manga, not a generic image grid:

- **19+ templates** — classic manga grids (2/3/4/6/8 panel), flexible mixed layouts (1+2, 2+3, 2+3+2…), hero/emphasis layouts, and photo/album grids.
- **6 bubble types** — speech, thought, shout, whisper, narration, inner voice — with movable tails, colors, and opacity.
- **Non-rectangular frames** — drag any frame's four corners to skew it into the dynamic, cinematic shapes real manga uses.
- **Breakout "page image"** — float a free image above the grid, deform it, and use it as a splash or SFX.
- **Auto-gap / edge-snap / frame-border** — one-click tools that keep a multi-panel page perfectly aligned.
- **Undo/redo** (50 steps) and **user templates** — save any layout you craft and reuse it project after project.

## 🏗 Architecture

```
┌─────────────────────────────────────────────────┐
│  Frontend  —  React 19 + TypeScript + Vite      │
│  (Zustand, framer-motion, @dnd-kit, react-icons)│
└────────────────────────┬────────────────────────┘
                         │ HTTP (FastAPI)
┌────────────────────────┴────────────────────────┐
│  Backend   —  FastAPI (Python 3.10+)            │
│  ├─ /api/storyboard     — panel decomposition   │
│  ├─ /api/prompt         — prompt enhancement    │
│  ├─ /api/assets         — upload + generation   │
│  ├─ /api/characters     — character CRUD        │
│  ├─ /api/composer       — user templates        │
│  ├─ /api/archive        — image folders         │
│  └─ /api/export         — PDF / ZIP             │
└────────┬───────────────────────┬────────────────┘
         │                       │
   ┌─────┴─────┐         ┌───────┴───────┐
   │  LLM API  │         │    SwarmUI    │
   │ (OpenAI-  │         │ (local image  │
   │ compatible│         │  generation)  │
   └───────────┘         └───────────────┘
```

## 🚀 Quick Start

**Prerequisites**

- **Python 3.10+** (global environment, no venv)
- **Node.js 20+** and npm
- *(Optional)* [SwarmUI](https://github.com/mcmonkeyprojects/SwarmUI) running on `127.0.0.1:7801`
- *(Optional)* An OpenAI-compatible LLM endpoint (Ollama, vLLM, OpenAI, …)

```bash
# 1. Install backend dependencies
pip install -r backend/requirements.txt

# 2. Install frontend dependencies
cd frontend && npm install && cd ..

# 3. Build the frontend (production) — or `npm --prefix frontend run dev` for HMR
npm --prefix frontend run build

# 4. Start the server (serves the built frontend at http://localhost:5180)
python -m backend.main 5180
```

On Windows, just run `run.bat`.

## ⚙️ Configuration

On first launch TT_AutoManga creates `data/settings.json` (gitignored). Configure:

- **API Endpoint** — your LLM URL (default `http://127.0.0.1:11434/v1` for Ollama)
- **API Key** — leave empty for local models
- **Model** — any chat-completions-compatible model
- **SwarmUI** — server address, plus presets combining model, LoRAs, steps, CFG, sampler, and a global prompt suffix

## 📦 Packaging (optional)

Bundle the app as a lightweight WebView executable via [Pake](https://github.com/tw93/Pake):

```bash
npm install -g pake-cli
build.bat
```

## 🛠 Tech Stack

| Layer | Tech |
|---|---|
| Frontend | React 19, TypeScript, Vite, Zustand, framer-motion, @dnd-kit, react-icons |
| Backend | FastAPI, uvicorn, pydantic v2, httpx, openai |
| Export | ReportLab (PDF), Pillow (images) |
| AI | Any OpenAI-compatible LLM + SwarmUI for images |

## 📁 Project Structure

```
TT_AutoManga/
├── backend/
│   ├── main.py              # FastAPI entry
│   ├── api/                 # route handlers
│   ├── core/                # config + OpenAI/SwarmUI clients
│   ├── storage/             # file storage
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/      # the seven tabs
│   │   ├── store/           # Zustand stores
│   │   ├── i18n/            # EN/ZH translations
│   │   └── types/           # TypeScript interfaces
│   └── package.json
├── data/                    # ⚠️ runtime data (gitignored)
├── docs/
│   └── screenshots/         # README screenshots (gitignored)
├── SPEC.md                  # full technical spec
├── run.bat / build.bat      # start / package scripts
└── LICENSE
```

## 🤝 Contributing

PRs welcome. Please:

1. Run `npm run lint` in `frontend/` before submitting
2. Keep the existing style (pure CSS, no Tailwind; Zustand for state)
3. Never commit anything under `data/` — it is private user data

## 📄 License

MIT — see [LICENSE](LICENSE).

## ⚠️ Note

This project is intended for **legitimate creative work**. Image-generation presets may reference NSFW-friendly models for artistic flexibility; users are responsible for compliance with local laws and platform terms of service.

---

<div align="center">

**[English](README.md) · [简体中文](README.zh-CN.md)**

Made with ❤️ by [TTDiang2](https://github.com/TTDiang2)

</div>