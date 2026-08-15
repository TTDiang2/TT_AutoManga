<div align="center">

<img src="frontend/public/icons.svg" alt="TT_AutoManga" width="96" />

# TT_AutoManga

**从一段文字,到一本漫画。**

将小说文本自动拆解为分镜 → 生成专业提示词 → 调用本地 AI 出图 → 排版成稿并导出 PDF。一条龙完成从「故事」到「成书」的完整创作流程。

<!-- LANGUAGE SWITCH -->
**[English](#-english) · [中文](#-中文)**

</div>

---

## 📸 界面预览

<!--
  SCREENSHOT PLACEHOLDERS — 请替换为真实截图。
  推荐路径（保证 URL 稳定）：
    docs/screenshots/01-storyboard.png
    docs/screenshots/02-prompt-lab.png
    docs/screenshots/03-composer.png
    docs/screenshots/04-assets.png
    docs/screenshots/05-showcase.png
  注意：docs/screenshots/ 已在 .gitignore 中，不会随代码推送，
  提交前请确认截图不含个人项目内容。
-->

<p align="center">
  <em>① 分镜拆解 —— 把一整段小说拆成一个个可编辑的漫画分镜</em>
</p>

<p align="center">
  <img src="docs/screenshots/01-storyboard.png" alt="分镜拆解" width="800" />
</p>

<p align="center">
  <em>② 提示词实验室 —— 一键把分镜转成 SDXL / Danbooru 标签</em>
</p>

<p align="center">
  <img src="docs/screenshots/02-prompt-lab.png" alt="提示词实验室" width="800" />
</p>

<p align="center">
  <em>③ 视觉编辑器 —— 拖拽式排版,内置 19+ 漫画/写真模板与对话气泡</em>
</p>

<p align="center">
  <img src="docs/screenshots/03-composer.png" alt="视觉编辑器" width="800" />
</p>

<p align="center">
  <em>④ 素材管理 —— 上传本地图片,或调用 SwarmUI 批量出图</em>
</p>

<p align="center">
  <img src="docs/screenshots/04-assets.png" alt="素材管理" width="800" />
</p>

<p align="center">
  <em>⑤ 作品陈列 —— 项目管理 + 一键导出 PDF / 图片压缩包</em>
</p>

<p align="center">
  <img src="docs/screenshots/05-showcase.png" alt="作品陈列" width="800" />
</p>

---

<a id="-english"></a>
## 🇬🇧 English

> Turn a story into a comic, end to end.

**TT_AutoManga** is a full-stack, AI-driven workflow that automates the entire manga production pipeline: it decomposes novel text into panels, turns each panel into a production-grade image prompt, generates artwork through your local [SwarmUI](https://github.com/mcmonkeyprojects/SwarmUI), and assembles everything into a finished page you can export as PDF or images.

### Why TT_AutoManga?

Writing a story is easy. Turning it into a comic is not — it normally requires a storyboard artist, prompt-engineering skill, a local image-generation setup, and layout software. TT_AutoManga collapses all four into one tool:

- **One pipeline, zero context-switching** — story → panels → prompts → images → pages, all in the same window.
- **Local-first & private** — your text, images, and projects stay on your machine (everything lives under `data/`, gitignored by design).
- **Model-agnostic** — any OpenAI-compatible endpoint (Ollama, vLLM, OpenAI, …) for text; any SwarmUI model/LoRA for images.
- **Built for real manga layout** — non-rectangular frames, dialogue bubbles, right-to-left reading order — not just a grid of squares.

### ✨ Features

| Module | What it does |
|---|---|
| **Storyboard** | Splits novel text into discrete manga panels (scene / characters / dialogue), with a 1–5 detail level and drag-to-reorder editing. |
| **Prompt Lab** | Converts each panel into SDXL / Danbooru tags or natural-language prompts; supports negative prompts, seeds, batch generation, and JSON import. |
| **Assets** | Upload local images or generate via SwarmUI with connection status; organize results into folders and download as ZIP. |
| **Visual Composer** | Drag-and-drop page builder with **19+ built-in templates**, 6 dialogue-bubble types, free-floating breakout images, and non-rectangular (4-corner deformable) frames. |
| **Characters** | Auto-extracts characters from your storyboard, stores appearance notes, and generates consistent reference images. |
| **Showcase** | Project management (create / save / load / duplicate) plus PDF and image-ZIP export. |
| **Settings** | Full control over the LLM endpoint, SwarmUI presets, model / LoRA / sampler / steps / CFG, and language. |

### 🖌 Composer — the highlight

The Visual Composer is a page editor purpose-built for manga, not a generic image grid:

- **19+ templates** — classic manga grids (2/3/4/6/8 panel), flexible mixed layouts (1+2, 2+3, 2+3+2…), hero/emphasis layouts, and photo/album grids.
- **6 bubble types** — speech, thought, shout, whisper, narration, inner voice — with movable tails, colors, and opacity.
- **Non-rectangular frames** — drag any frame's four corners to skew it into the dynamic, cinematic shapes real manga uses.
- **Breakout "page image"** — float a free image above the grid, deform it, and use it as a splash or SFX.
- **Auto-gap / edge-snap / frame-border** — one-click tools that keep a multi-panel page perfectly aligned.
- **Undo/redo** (50 steps) and **user templates** — save any layout you craft and reuse it project after project.

### 🏗 Architecture

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

### 🚀 Quick Start

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

### ⚙️ Configuration

On first launch TT_AutoManga creates `data/settings.json` (gitignored). Configure:

- **API Endpoint** — your LLM URL (default `http://127.0.0.1:11434/v1` for Ollama)
- **API Key** — leave empty for local models
- **Model** — any chat-completions-compatible model
- **SwarmUI** — server address, plus presets combining model, LoRAs, steps, CFG, sampler, and a global prompt suffix

### 📦 Packaging (optional)

Bundle the app as a lightweight WebView executable via [Pake](https://github.com/tw93/Pake):

```bash
npm install -g pake-cli
build.bat
```

### 🛠 Tech Stack

| Layer | Tech |
|---|---|
| Frontend | React 19, TypeScript, Vite, Zustand, framer-motion, @dnd-kit, react-icons |
| Backend | FastAPI, uvicorn, pydantic v2, httpx, openai |
| Export | ReportLab (PDF), Pillow (images) |
| AI | Any OpenAI-compatible LLM + SwarmUI for images |

### 📁 Project Structure

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

### 🤝 Contributing

PRs welcome. Please:

1. Run `npm run lint` in `frontend/` before submitting
2. Keep the existing style (pure CSS, no Tailwind; Zustand for state)
3. Never commit anything under `data/` — it is private user data

### 📄 License

MIT — see [LICENSE](LICENSE).

### ⚠️ Note

This project is intended for **legitimate creative work**. Image-generation presets may reference NSFW-friendly models for artistic flexibility; users are responsible for compliance with local laws and platform terms of service.

---

<a id="-中文"></a>
<details>
<summary><h2>🇨🇳 中文</h2></summary>

> 把故事变成漫画,一步到位。

**TT_AutoManga** 是一个 AI 驱动的全流程漫画创作工具:把小说文字自动拆成分镜 → 为每个分镜生成专业级提示词 → 通过本地 [SwarmUI](https://github.com/mcmonkeyprojects/SwarmUI) 出图 → 排版成稿并导出 PDF 或图片。从「一段故事」到「一本漫画」,一个窗口里全部完成。

### 为什么需要它?

写故事不难,把故事画成漫画却很难 —— 通常需要分镜师的功力、提示词工程的经验、一套本地出图环境,再加一套排版软件。TT_AutoManga 把这四件事合而为一:

- **一条流水线,零切换成本** — 故事 → 分镜 → 提示词 → 图片 → 页面,全程在同一个界面里完成。
- **本地优先,隐私无忧** — 你的文字、图片、项目全部留在本地(`data/` 目录,设计上就已 git 忽略)。
- **模型无关** — 文字侧可接任意 OpenAI 兼容端点(Ollama、vLLM、OpenAI…),图片侧可挂任意 SwarmUI 模型 / LoRA。
- **为真正的漫画排版而生** — 非矩形分镜框、对话气泡、从右到左的阅读顺序,而不是一排排死板的方格。

### ✨ 功能一览

| 模块 | 能力 |
|---|---|
| **分镜拆解** | 把小说文本拆成独立漫画分镜(场景 / 角色 / 对白),支持 1–5 档详细度,可拖拽排序。 |
| **提示词实验室** | 把每个分镜转成 SDXL / Danbooru 标签或自然语言提示词;支持反向提示词、种子、批量生成、JSON 导入。 |
| **素材管理** | 上传本地图片,或调用 SwarmUI 出图(带连接检测);归档到文件夹、一键下载 ZIP。 |
| **视觉编辑器** | 拖拽式排版,**19+ 内置模板**、6 种对话气泡、自由漂浮「破图」、非矩形(四角可变形)分镜框。 |
| **角色设计** | 自动从分镜提取角色,记录外貌设定,生成一致的角色参考图。 |
| **作品陈列** | 项目管理(新建 / 保存 / 加载 / 复制)+ PDF / 图片 ZIP 导出。 |
| **设置** | 完整掌控 LLM 端点、SwarmUI 预设、模型 / LoRA / 采样器 / 步数 / CFG,以及界面语言。 |

### 🖌 视觉编辑器 —— 核心亮点

这是为漫画专门打造的页面编辑器,而不是普通的图片网格:

- **19+ 种模板** — 经典漫画格(2/3/4/6/8 格)、灵活混合布局(1+2、2+3、2+3+2…)、强调 / 大特写布局、写真 / 相册网格。
- **6 种气泡** — 对白、思考、喊叫、耳语、旁白、内心独白,尾巴可拖动,颜色、透明度均可调。
- **非矩形分镜框** — 拖动任意分镜的四个角,把方格斜切成真正漫画里那种充满张力的动感构图。
- **「破图」自由图** — 让一张图脱离网格浮在页面上,自由缩放、变形,用作跨页特写或特效字。
- **自动间距 / 边缘吸附 / 统一描边** — 一键让多分镜页面严丝合缝地对齐。
- **撤销 / 重做**(50 步)与**自定义模板** — 精心排好的版式可以存成模板,下次直接复用。

### 🏗 系统架构

```
┌─────────────────────────────────────────────────┐
│  前端  —  React 19 + TypeScript + Vite           │
│  (Zustand, framer-motion, @dnd-kit, react-icons) │
└────────────────────────┬────────────────────────┘
                         │ HTTP (FastAPI)
┌────────────────────────┴────────────────────────┐
│  后端  —  FastAPI (Python 3.10+)                │
│  ├─ /api/storyboard     — 分镜拆解              │
│  ├─ /api/prompt         — 提示词增强            │
│  ├─ /api/assets         — 上传 + 出图           │
│  ├─ /api/characters     — 角色 CRUD             │
│  ├─ /api/composer       — 用户模板              │
│  ├─ /api/archive        — 图片文件夹            │
│  └─ /api/export         — PDF / ZIP 导出        │
└────────┬───────────────────────┬────────────────┘
         │                       │
   ┌─────┴─────┐         ┌───────┴───────┐
   │  LLM API  │         │    SwarmUI    │
   │ (OpenAI-  │         │ (本地图片     │
   │ compatible│         │  生成服务)    │
   └───────────┘         └───────────────┘
```

### 🚀 快速开始

**前置依赖**

- **Python 3.10+**(使用全局环境,不创建 venv)
- **Node.js 20+** 与 npm
- *(可选)* 本地运行的 [SwarmUI](https://github.com/mcmonkeyprojects/SwarmUI)(默认 `127.0.0.1:7801`)
- *(可选)* 任意 OpenAI 兼容的 LLM 接入点(Ollama、vLLM、OpenAI 等)

```bash
# 1. 安装后端依赖
pip install -r backend/requirements.txt

# 2. 安装前端依赖
cd frontend && npm install && cd ..

# 3. 构建前端(生产模式)—— 开发热更新用 `npm --prefix frontend run dev`
npm --prefix frontend run build

# 4. 启动服务(把构建好的前端托管在 http://localhost:5180)
python -m backend.main 5180
```

Windows 用户直接运行 `run.bat` 即可。

### ⚙️ 配置说明

首次启动后,TT_AutoManga 会生成 `data/settings.json`(已被 git 忽略)。可配置:

- **API 端点** — 你的 LLM 地址(默认 `http://127.0.0.1:11434/v1`,适配 Ollama)
- **API 密钥** — 本地模型留空即可
- **模型** — 任意 chat-completions 兼容模型
- **SwarmUI** — 服务器地址,以及组合了模型、LoRA、步数、CFG、采样器和全局提示词后缀的预设

### 📦 打包(可选)

通过 [Pake](https://github.com/tw93/Pake) 把应用打包成轻量 WebView 可执行文件:

```bash
npm install -g pake-cli
build.bat
```

### 🛠 技术栈

| 层级 | 技术 |
|---|---|
| 前端 | React 19、TypeScript、Vite、Zustand、framer-motion、@dnd-kit、react-icons |
| 后端 | FastAPI、uvicorn、pydantic v2、httpx、openai |
| 导出 | ReportLab (PDF)、Pillow (图片) |
| AI | 任意 OpenAI 兼容 LLM + SwarmUI 出图 |

### 📁 项目结构

```
TT_AutoManga/
├── backend/
│   ├── main.py              # FastAPI 入口
│   ├── api/                 # 路由处理
│   ├── core/                # 配置 + OpenAI/SwarmUI 客户端
│   ├── storage/             # 文件存储
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/      # 七个功能页签
│   │   ├── store/           # Zustand 状态
│   │   ├── i18n/            # 中英文翻译
│   │   └── types/           # TypeScript 类型
│   └── package.json
├── data/                    # ⚠️ 运行时数据(已 git 忽略)
├── docs/
│   └── screenshots/         # README 截图(已 git 忽略)
├── SPEC.md                  # 完整技术规范
├── run.bat / build.bat      # 启动 / 打包脚本
└── LICENSE
```

### 🤝 贡献指南

欢迎提交 PR。请注意:

1. 提交前在 `frontend/` 下运行 `npm run lint`
2. 保持现有代码风格(纯 CSS、不引入 Tailwind;状态管理使用 Zustand)
3. 不要提交 `data/` 下的任何内容 —— 那是用户的私有数据

### 📄 开源协议

MIT — 详见 [LICENSE](LICENSE)。

### ⚠️ 免责声明

本项目用于**合法的创意工作**。图片生成预设可能涉及 NSFW 友好的模型以提供艺术创作的灵活性,使用者需自行负责确保符合当地法律法规与平台服务条款。

</details>

---

<div align="center">

**[English](#-english) · [中文](#-中文)**

Made with ❤️ by [TTDiang2](https://github.com/TTDiang2)

</div>