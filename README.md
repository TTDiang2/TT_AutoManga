<div align="center">

# TT_AutoManga

**AI-powered manga panel generation from novel text — automated storyboard decomposition, prompt engineering, image synthesis, and visual composition.**

<!-- LANGUAGE SWITCH -->
**[English](#-english) · [中文](#-中文)**

</div>

---

## 📸 Screenshots

<!--
  SCREENSHOT PLACEHOLDERS — replace these with actual screenshots.
  Recommended paths (so URLs are stable):
    docs/screenshots/01-storyboard.png
    docs/screenshots/02-prompt-lab.png
    docs/screenshots/03-composer.png
    docs/screenshots/04-assets.png
    docs/screenshots/05-showcase.png
-->

<p align="center">
  <em>Storyboard Engine — split text into manga panels</em>
</p>

<p align="center">
  <img src="docs/screenshots/01-storyboard.png" alt="Storyboard Engine" width="800" />
  <!-- If you don't have a screenshot yet, use this fallback while waiting:
  <img src="https://raw.githubusercontent.com/TTDiang2/TT_AutoManga/main/docs/screenshots/01-storyboard.png"
       alt="Storyboard placeholder" width="800" />
  -->
</p>

<p align="center">
  <em>Prompt Lab — convert panels into SDXL/Danbooru tags</em>
</p>

<p align="center">
  <img src="docs/screenshots/02-prompt-lab.png" alt="Prompt Lab" width="800" />
</p>

<p align="center">
  <em>Visual Composer — drag-and-drop canvas with layers and bubbles</em>
</p>

<p align="center">
  <img src="docs/screenshots/03-composer.png" alt="Visual Composer" width="800" />
</p>

<p align="center">
  <em>Asset Manager — local upload or SwarmUI generation</em>
</p>

<p align="center">
  <img src="docs/screenshots/04-assets.png" alt="Asset Manager" width="800" />
</p>

<p align="center">
  <em>Showcase &amp; Export — project gallery, PDF/ZIP export</em>
</p>

<p align="center">
  <img src="docs/screenshots/05-showcase.png" alt="Showcase" width="800" />
</p>

---

<a id="-english"></a>
## 🇬🇧 English

### ✨ Features

- **Storyboard Engine** — split novel text into discrete manga panels with scene, characters, dialogue
- **Prompt Lab** — convert panel descriptions into SDXL/Danbooru tags or natural-language prompts
- **Asset Manager** — upload local images or generate via SwarmUI with status polling
- **Visual Composer** — drag-and-drop canvas with templates, layers, and dialogue bubbles
- **Character Library** — persist character designs and reuse them across panels
- **Project Management** — save/load `.automanga` projects, export to PDF or ZIP
- **Customizable** — pluggable LLM endpoint, SwarmUI presets, per-panel overrides

### 🏗 Architecture

```
┌─────────────────────────────────────────────────┐
│  Frontend  —  React 19 + TypeScript + Vite      │
│  (Zustand state, react-icons, framer-motion)    │
└────────────────────────┬────────────────────────┘
                         │ HTTP (FastAPI)
┌────────────────────────┴────────────────────────┐
│  Backend   —  FastAPI (Python 3.10+)            │
│  ├─ /api/storyboard     — Storyboard Engine     │
│  ├─ /api/prompt         — Prompt Lab            │
│  ├─ /api/assets         — Asset Manager         │
│  ├─ /api/characters     — Character CRUD        │
│  ├─ /api/project        — Project Management    │
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

- **Python 3.10+** (uses global environment, no venv)
- **Node.js 20+** and npm
- *(Optional)* [SwarmUI](https://github.com/mcmonkeyprojects/SwarmUI) running locally on `127.0.0.1:7801`
- *(Optional)* An OpenAI-compatible LLM endpoint (Ollama, vLLM, OpenAI, etc.)

**1. Install backend dependencies**

```bash
pip install -r backend/requirements.txt
```

**2. Install frontend dependencies**

```bash
cd frontend
npm install
cd ..
```

**3. Build the frontend**

```bash
# Build once (production):
npm --prefix frontend run build

# Or run dev server with HMR:
npm --prefix frontend run dev
```

**4. Start the server**

```bash
# Backend serves built frontend at http://localhost:5180
python -m backend.main 5180
```

Or simply on Windows:

```bash
run.bat
```

### ⚙️ Configuration

After first launch, TT_AutoManga creates `data/settings.json` (gitignored). Configure:

- **API Endpoint** — your LLM URL (default `http://127.0.0.1:11434/v1` for Ollama)
- **API Key** — leave empty for local models
- **Model** — any chat-completions-compatible model
- **SwarmUI Address** — defaults to `http://127.0.0.1:7801`
- **SwarmUI Presets** — model + LoRAs + sampler config per preset

### 📦 Packaging (optional)

Package the app as a lightweight WebView executable via [Pake](https://github.com/tw93/Pake):

```bash
npm install -g pake-cli
build.bat
```

### 🛠 Tech Stack

| Layer | Tech |
|---|---|
| Frontend | React 19, TypeScript, Vite, Zustand, framer-motion, @dnd-kit |
| Backend | FastAPI, uvicorn, pydantic v2, httpx, openai |
| Export | ReportLab (PDF), Pillow (images) |
| AI | Any OpenAI-compatible LLM + SwarmUI for images |

### 📁 Project Structure

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
├── docs/
│   └── screenshots/         # README screenshots (gitignored as personal data)
├── SPEC.md                  # Full technical specification
├── run.bat                  # Start server (Windows)
├── build.bat                # Package with Pake
└── LICENSE
```

### 🤝 Contributing

PRs welcome. Please:

1. Run `npm run lint` in `frontend/` before submitting
2. Keep the existing code style (pure CSS, no Tailwind; Zustand for state)
3. Do not commit anything from `data/` — it is private user data
4. Do not commit screenshots that contain personal project output

### 📄 License

MIT — see [LICENSE](LICENSE).

### ⚠️ Note

This project is intended for **legitimate creative work**. Image-generation presets and configuration may reference NSFW-friendly models for artistic flexibility; users are responsible for compliance with applicable laws and platform terms of service in their jurisdiction.

---

<a id="-中文"></a>
<details>
<summary><h2>🇨🇳 中文</h2></summary>

### ✨ 功能特性

- **分镜引擎** — 将小说文本拆解为独立的漫画分镜,包含场景、角色与对白
- **Prompt 工坊** — 将分镜描述转换为 SDXL/Danbooru 风格标签或自然语言提示词
- **资产管理** — 上传本地图片,或调用 SwarmUI 生成并实时轮询状态
- **可视化排版** — 拖拽式画布,内置模板、图层与对话框系统
- **角色库** — 持久化角色设计,跨分镜复用
- **项目管理** — 保存/加载 `.automanga` 项目,导出 PDF 或 ZIP
- **高度可定制** — 可插拔 LLM 接入点、SwarmUI 预设、单分镜覆盖

### 🏗 系统架构

```
┌─────────────────────────────────────────────────┐
│  前端  —  React 19 + TypeScript + Vite           │
│  (Zustand 状态管理,react-icons,framer-motion)  │
└────────────────────────┬────────────────────────┘
                         │ HTTP (FastAPI)
┌────────────────────────┴────────────────────────┐
│  后端  —  FastAPI (Python 3.10+)                │
│  ├─ /api/storyboard     — 分镜引擎              │
│  ├─ /api/prompt         — Prompt 工坊           │
│  ├─ /api/assets         — 资产管理              │
│  ├─ /api/characters     — 角色 CRUD             │
│  ├─ /api/project        — 项目管理              │
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

- **Python 3.10+** (使用全局环境,不创建 venv)
- **Node.js 20+** 与 npm
- *(可选)* 本地运行的 [SwarmUI](https://github.com/mcmonkeyprojects/SwarmUI)(默认 `127.0.0.1:7801`)
- *(可选)* 任意 OpenAI 兼容的 LLM 接入点(Ollama、vLLM、OpenAI 等)

**1. 安装后端依赖**

```bash
pip install -r backend/requirements.txt
```

**2. 安装前端依赖**

```bash
cd frontend
npm install
cd ..
```

**3. 构建前端**

```bash
# 生产构建:
npm --prefix frontend run build

# 或开发模式(支持热更新):
npm --prefix frontend run dev
```

**4. 启动服务**

```bash
# 后端会将构建好的前端服务在 http://localhost:5180
python -m backend.main 5180
```

Windows 用户也可以直接:

```bash
run.bat
```

### ⚙️ 配置说明

首次启动后,TT_AutoManga 会生成 `data/settings.json` (已被 git 忽略)。可配置:

- **API 接入点** — 你的 LLM 地址(默认 `http://127.0.0.1:11434/v1`,适配 Ollama)
- **API Key** — 本地模型留空即可
- **模型** — 任意 chat-completions 兼容的模型
- **SwarmUI 地址** — 默认 `http://127.0.0.1:7801`
- **SwarmUI 预设** — 每个预设包含模型、LoRA、采样器等参数

### 📦 打包(可选)

通过 [Pake](https://github.com/tw93/Pake) 将应用打包为轻量 WebView 可执行文件:

```bash
npm install -g pake-cli
build.bat
```

### 🛠 技术栈

| 层级 | 技术 |
|---|---|
| 前端 | React 19、TypeScript、Vite、Zustand、framer-motion、@dnd-kit |
| 后端 | FastAPI、uvicorn、pydantic v2、httpx、openai |
| 导出 | ReportLab (PDF)、Pillow (图片) |
| AI | 任意 OpenAI 兼容 LLM + SwarmUI 图片生成 |

### 📁 项目结构

```
TT_AutoManga/
├── backend/
│   ├── main.py              # FastAPI 入口
│   ├── api/                 # 路由处理(分镜、prompt、资产、...)
│   ├── core/                # 配置 + OpenAI/SwarmUI 客户端
│   ├── storage/             # 文件存储逻辑
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/      # 各 Tab 组件(排版、Prompt 工坊、资产、...)
│   │   ├── store/           # Zustand 状态
│   │   ├── hooks/           # 自定义 Hooks
│   │   ├── i18n/            # 中英文翻译
│   │   └── types/           # TypeScript 类型定义
│   ├── public/              # 静态资源
│   └── package.json
├── data/                    # ⚠️ 运行时数据(已被 git 忽略)
│   ├── projects/            # 用户项目
│   ├── assets/              # 生成的图片
│   ├── exports/             # PDF/ZIP 导出
│   └── settings.json        # 用户偏好
├── docs/
│   └── screenshots/         # README 截图(作为个人数据被忽略)
├── SPEC.md                  # 完整技术规范
├── run.bat                  # 启动服务(Windows)
├── build.bat                # Pake 打包
└── LICENSE
```

### 🤝 贡献指南

欢迎提交 PR。请注意:

1. 提交前在 `frontend/` 下运行 `npm run lint`
2. 保持现有代码风格(纯 CSS、不引入 Tailwind;状态管理使用 Zustand)
3. 不要提交 `data/` 下的任何内容 — 那是用户的私有数据
4. 不要提交包含个人项目输出的截图

### 📄 开源协议

MIT — 详见 [LICENSE](LICENSE)。

### ⚠️ 免责声明

本项目用于**合法的创意工作**。图片生成预设与配置可能涉及 NSFW 友好的模型以提供艺术创作的灵活性,使用者需自行负责确保符合当地法律法规与平台服务条款。

</details>

---

<div align="center">

**[English](#-english) · [中文](#-中文)**

Made with ❤️ by [TTDiang2](https://github.com/TTDiang2)

</div>