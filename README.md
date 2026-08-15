# AutoManga

> AI-powered manga panel generation from novel text — automated storyboard decomposition, prompt engineering, image synthesis, and visual composition.

A full-stack web application that turns written stories into manga-style panel compositions. AutoManga chains together an LLM (any OpenAI-compatible endpoint) and SwarmUI for the heavy image-generation work, giving you a desktop-style workflow for visual storytelling.

## ✨ Features

- **Storyboard Engine** — split novel text into discrete manga panels with scene, characters, dialogue
- **Prompt Lab** — convert panel descriptions into SDXL/Danbooru tags or natural-language prompts
- **Asset Manager** — upload local images or generate via SwarmUI with status polling
- **Visual Composer** — drag-and-drop canvas with templates, layers, and dialogue bubbles
- **Project Management** — save/load `.automanga` projects, export to PDF or ZIP
- **Customizable** — pluggable LLM endpoint, SwarmUI presets, per-panel overrides

## 🏗 Architecture

```
┌─────────────────────────────────────────────────┐
│  Frontend  —  React 19 + TypeScript + Vite      │
│  (Zustand state, react-icons, framer-motion)    │
└────────────────────────┬────────────────────────┘
                         │ HTTP (FastAPI)
┌────────────────────────┴────────────────────────┐
│  Backend   —  FastAPI (Python 3.10+)            │
│  ├─ /api/storyboard     — Tab 1                 │
│  ├─ /api/prompt         — Tab 2                 │
│  ├─ /api/assets         — Tab 3                 │
│  ├─ /api/project        — Tab 5                 │
│  ├─ /api/export         — PDF / ZIP             │
│  ├─ /api/characters     — Character CRUD        │
│  └─ /api/settings       — User preferences      │
└────────┬───────────────────────┬────────────────┘
         │                       │
   ┌─────┴─────┐         ┌───────┴───────┐
   │  LLM API  │         │    SwarmUI    │
   │ (OpenAI-  │         │ (local image  │
   │ compatible│         │  generation)  │
   └───────────┘         └───────────────┘
```

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+** (uses global environment, no venv)
- **Node.js 20+** and npm
- **(Optional)** [SwarmUI](https://github.com/mcmonkeyprojects/SwarmUI) running locally on `127.0.0.1:7801`
- **(Optional)** An OpenAI-compatible LLM endpoint (Ollama, vLLM, OpenAI, etc.)

### 1. Install backend dependencies

```bash
pip install -r backend/requirements.txt
```

### 2. Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

### 3. Build the frontend

```bash
# Either build once (production mode):
npm --prefix frontend run build

# Or run dev server with HMR:
npm --prefix frontend run dev
```

### 4. Start the server

```bash
# Backend serves built frontend at http://localhost:5180
python -m backend.main 5180
```

Or simply:

```bash
run.bat
```

## ⚙️ Configuration

After first launch, AutoManga creates `data/settings.json` (gitignored). Configure:

- **API Endpoint** — your LLM URL (default `http://127.0.0.1:11434/v1` for Ollama)
- **API Key** — leave empty for local models
- **Model** — any chat-completions-compatible model
- **SwarmUI Address** — defaults to `http://127.0.0.1:7801`
- **SwarmUI Presets** — model + LoRAs + sampler config per preset

## 📦 Packaging (optional)

Package the app as a lightweight WebView executable via [Pake](https://github.com/tw93/Pake):

```bash
npm install -g pake-cli
build.bat
```

## 🛠 Tech Stack

| Layer | Tech |
|---|---|
| Frontend | React 19, TypeScript, Vite, Zustand, framer-motion, @dnd-kit |
| Backend | FastAPI, uvicorn, pydantic v2, httpx, openai |
| Export | ReportLab (PDF), Pillow (images) |
| AI | Any OpenAI-compatible LLM + SwarmUI for images |

## 📁 Project Structure

```
TT_AutoManga/
├── backend/
│   ├── main.py              # FastAPI app entry
│   ├── api/                 # Route handlers (storyboard, prompt, assets, ...)
│   ├── core/                # Config + OpenAI/SwarmUI clients
│   ├── storage/             # File storage logic
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/      # Tab components (Composer, Prompt Lab, Assets, ...)
│   │   ├── store/           # Zustand stores
│   │   ├── hooks/           # Custom hooks
│   │   ├── i18n/            # EN/ZH translations
│   │   └── types/           # TypeScript interfaces
│   ├── public/              # Static assets
│   └── package.json
├── data/                    # ⚠️ Runtime data (gitignored)
│   ├── projects/            # User projects
│   ├── assets/              # Generated images
│   ├── exports/             # PDF/ZIP exports
│   └── settings.json        # User preferences
├── SPEC.md                  # Full technical specification
├── run.bat                  # Start server (Windows)
├── build.bat                # Package with Pake
└── LICENSE
```

## 🤝 Contributing

PRs welcome. Please:

1. Run `npm run lint` in `frontend/` before submitting
2. Keep the existing code style (pure CSS, no Tailwind; Zustand for state)
3. Do not commit anything from `data/` — it's user data

## 📄 License

MIT — see [LICENSE](LICENSE).

## ⚠️ Note

This project is intended for **legitimate creative work**. Image-generation presets and configuration may reference NSFW-friendly models for artistic flexibility; users are responsible for compliance with applicable laws and platform terms of service in their jurisdiction.