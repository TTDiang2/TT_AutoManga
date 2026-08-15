# AI Comic Tool - Technical Specification

## 1. Project Overview

**Project Name:** AutoManga  
**Type:** Full-stack Web Application (WebView Desktop App)  
**Core Functionality:** Automated manga panel generation from novel text through AI-powered storyboard decomposition, prompt generation, image synthesis, and visual composition.  
**Target Users:** Manga artists, webcomic creators, novel enthusiasts wanting to visualize stories.

---

## 2. UI/UX Specification

### 2.1 Layout Structure

**Overall Layout:**
- Single-page application with tab-based navigation
- Fixed left sidebar (64px width) for tab icons
- Main content area with contextual header
- No traditional header/footer - maximized canvas space

**Responsive Behavior:**
- Desktop-first design (1920x1080 primary target)
- Minimum supported: 1280x720
- Fluid scaling between breakpoints

### 2.2 Visual Design

**Color Palette:**
| Role | Color | Hex |
|------|-------|-----|
| Background Primary | Pure White | #FFFFFF |
| Background Secondary | Off-White | #FAFAFA |
| Background Tertiary | Light Gray | #F5F5F5 |
| Border Default | Whisper Gray | #E8E8E8 |
| Border Hover | Soft Gray | #D4D4D4 |
| Text Primary | Charcoal | #1A1A1A |
| Text Secondary | Medium Gray | #6B6B6B |
| Text Muted | Light Gray | #9B9B9B |
| Accent Primary | Ink Black | #000000 |
| Accent Hover | Dark Gray | #333333 |
| Success | Sage Green | #4CAF50 |
| Warning | Amber | #FF9800 |
| Error | Coral Red | #F44336 |
| Info | Sky Blue | #2196F3 |

**Typography:**
| Element | Font Family | Size | Weight | Line Height |
|---------|-------------|------|--------|-------------|
| App Title | Inter | 18px | 600 | 1.2 |
| Tab Label | Inter | 12px | 500 | 1.0 |
| Section Header | Inter | 16px | 600 | 1.3 |
| Body Text | Inter | 14px | 400 | 1.5 |
| Small/Caption | Inter | 12px | 400 | 1.4 |
| Monospace (code) | JetBrains Mono | 13px | 400 | 1.5 |

**Spacing System:**
- Base unit: 4px
- XS: 4px | S: 8px | M: 16px | L: 24px | XL: 32px | XXL: 48px

**Visual Effects:**
- Box shadows: `0 1px 3px rgba(0,0,0,0.04)` (subtle), `0 4px 12px rgba(0,0,0,0.08)` (elevated)
- Border radius: 4px (small), 8px (medium), 12px (large), 16px (cards)
- Transitions: 200ms ease-out (default), 300ms ease-in-out (complex)
- No gradients - pure flat design

### 2.3 Components

**Navigation Sidebar:**
- Vertical icon strip with tooltips
- Active state: filled icon + left border accent
- Hover: subtle background tint

**Tab Content Container:**
- Max-width: 1400px, centered
- Padding: 32px
- Scrollable content area

**Buttons:**
- Primary: Black background, white text, 36px height
- Secondary: White background, black border, black text
- Ghost: Transparent, text only
- States: hover (darken 10%), active (darken 15%), disabled (50% opacity)

**Input Fields:**
- Height: 40px
- Border: 1px solid #E8E8E8
- Focus: border-color #000000, subtle shadow
- Placeholder: #9B9B9B

**Cards:**
- White background
- 1px border #E8E8E8
- 16px border-radius
- Hover: elevated shadow

**Modal/Dialogs:**
- Centered overlay with backdrop blur (4px)
- White card with 24px padding
- Smooth scale-in animation

---

## 3. Functionality Specification

### 3.1 Tab 1: Storyboard Engine

**Input Section:**
- Large textarea for novel text (min-height: 200px)
- Character count display
- Clear button

**Precision Control:**
- Slider: 1-5 scale (1=abstract summary, 5=detailed scenes)
- Preset buttons: "Brief", "Balanced", "Detailed"
- Affects `detail_level` parameter in API prompt

**Generation:**
- "Generate Storyboard" button (primary)
- Loading state with progress indicator
- Error state with retry option

**Output Display:**
- Vertical list of storyboard cards
- Each card shows:
  - Panel number (auto-indexed)
  - Scene description (editable textarea)
  - Characters in scene (tag list)
  - Dialogue excerpts (if any)
  - Delete button

**Interactions:**
- Drag-and-drop reordering (react-beautiful-dnd or @dnd-kit)
- Inline text editing - click to edit, blur to save
- Add/remove panels manually

**API Integration:**
- POST /api/storyboard/generate
- Request: { text, detail_level, api_config }
- Response: { panels: [{ id, scene, characters, dialogue }] }

### 3.2 Tab 2: Prompt Lab

**Panel Selector:**
- Dropdown or thumbnail grid to select target panel
- "Apply to All" button

**Mode Toggle:**
- Tab switcher: "Z-image Turbo" | "SDXL/Tags"

**Z-image Turbo Mode:**
- Input: natural language prompt textarea
- "Generate" button calls AI enhancement
- Output: Enhanced prompt with scene weighting
- Copy button

**SDXL/Tags Mode:**
- Input: comma-separated tags
- Auto-parsing of (weight) brackets
- Preview: formatted tag list with weight indicators
- Manual tag editor

**Prompt History:**
- Last 5 generated prompts per panel
- Click to restore

**Batch Operations:**
- "Refresh All Prompts" button
- Individual panel refresh

**API Integration:**
- POST /api/prompt/enhance
- Request: { scene_description, mode, api_config }
- Response: { enhanced_prompt }

### 3.3 Tab 3: Asset Management

**Panel Grid:**
- 2-3 column grid of panel slots
- Each slot shows:
  - Panel number
  - Current image (or placeholder)
  - Status indicator (empty/pending/ready)
  - Action buttons

**Local Upload:**
- Click slot to open file picker
- Supported: JPG, PNG, WebP
- Image auto-crops to fit panel aspect ratio

**SwarmUI Integration:**
- "Generate with SwarmUI" button per panel
- SwarmUI endpoint configuration (default: 127.0.0.1:7801)
- Workflow:
  1. Click generate → API call to SwarmUI
  2. Polling interval: 2 seconds
  3. Progress indicator during generation
  4. Auto-fill when complete
  5. Error handling with retry

**Image Preview:**
- Click to view full-size in modal
- Zoom controls

**API Integration:**
- GET /api/swarmui/status/{task_id}
- POST /api/swarmui/generate
- Request: { prompt, panel_id, swarmui_config }
- Response: { task_id, status, image_url }

### 3.4 Tab 4: Visual Composer

**Canvas Area:**
- Full-width canvas element
- Pan and zoom controls
- Grid snap option

**Template Library:**
- Sidebar with panel layout templates:
  - 1-panel (full)
  - 2-panel (vertical/horizontal)
  - 3-panel (vertical/horizontal/mixed)
  - 4-panel (grid)
  - 6-panel (2x3)
  - Manga-style (right-to-left)
- Drag template to canvas

**Layer System:**
- Layer panel on right side
- Layers: Background, Characters, Dialogue Bubbles, Effects
- Drag to reorder
- Visibility toggle
- Lock toggle
- Opacity slider

**Dialogue Bubble System:**
- Bubble templates: speech, thought, shout, whisper
- Auto-fill from Tab 1 dialogue data
- Drag to position
- Resize handles
- Text editor within bubble

**Tools:**
- Selection tool
- Move tool
- Text tool
- Bubble tool

**Export:**
- Export as PNG (composed)
- Export individual panels

### 3.5 Tab 5: Showcase & Export

**Project Gallery:**
- Grid of project cards
- Each shows: cover thumbnail, title, date, panel count
- Click to load project

**Project Management:**
- Create new project
- Save project (.automanga format - JSON)
- Load project
- Delete project
- Duplicate project

**Export Options:**
- PDF export (multi-page)
  - Page size: A4, Letter, Original
  - Quality: Standard, High
  - Include cover page option
- Image export (ZIP of PNGs)
- Individual panel export

**API Integration:**
- POST /api/project/save
- POST /api/export/pdf
- POST /api/export/images

### 3.6 Settings Center

**API Configuration:**
- OpenAI Compatible Endpoint (text input)
- API Key (password input with show/hide)
- Model selection (dropdown)
- Temperature slider (0-2)
- Max tokens input

**SwarmUI Configuration:**
- Server address (default: 127.0.0.1:7801)
- Connection test button

**Application Settings:**
- Default detail level
- Auto-save interval
- Export quality defaults

**Data Management:**
- Projects directory location
- Clear cache button
- Reset to defaults

---

## 4. Technical Architecture

### 4.1 Backend (FastAPI)

**Directory Structure:**
```
backend/
├── main.py              # FastAPI app entry
├── api/
│   ├── storyboard.py    # Tab 1 endpoints
│   ├── prompt.py       # Tab 2 endpoints
│   ├── assets.py       # Tab 3 endpoints
│   ├── project.py      # Tab 5 endpoints
│   └── export.py       # Tab 5 export endpoints
├── core/
│   ├── config.py        # Settings management
│   ├── openai_client.py # AI API wrapper
│   └── swarmui_client.py # SwarmUI wrapper
├── storage/
│   └── manager.py       # File storage logic
└── utils/
    └── pdf_generator.py # PDF synthesis
```

**API Endpoints:**
| Method | Path | Tab | Description |
|--------|------|-----|-------------|
| POST | /api/storyboard/generate | 1 | Generate storyboard from text |
| POST | /api/prompt/enhance | 2 | Enhance prompt |
| POST | /api/assets/upload | 3 | Upload local image |
| POST | /api/swarmui/generate | 3 | Generate image |
| GET | /api/swarmui/status/{task_id} | 3 | Check generation status |
| GET | /api/projects | 5 | List projects |
| POST | /api/projects/save | 5 | Save project |
| GET | /api/projects/load/{id} | 5 | Load project |
| POST | /api/export/pdf | 5 | Export PDF |
| POST | /api/export/images | 5 | Export images |
| GET | /api/settings | 6 | Get settings |
| POST | /api/settings | 6 | Update settings |

### 4.2 Frontend (React + TypeScript)

**Directory Structure:**
```
frontend/
├── src/
│   ├── components/
│   │   ├── layout/
│   │   │   ├── Sidebar.tsx
│   │   │   └── TabContainer.tsx
│   │   ├── common/
│   │   │   ├── Button.tsx
│   │   │   ├── Input.tsx
│   │   │   ├── Modal.tsx
│   │   │   └── Card.tsx
│   │   ├── storyboard/
│   │   │   ├── StoryboardTab.tsx
│   │   │   ├── PanelCard.tsx
│   │   │   └── PrecisionControl.tsx
│   │   ├── prompt/
│   │   │   ├── PromptLabTab.tsx
│   │   │   ├── ModeToggle.tsx
│   │   │   └── TagEditor.tsx
│   │   ├── assets/
│   │   │   ├── AssetTab.tsx
│   │   │   ├── PanelSlot.tsx
│   │   │   └── SwarmUIPanel.tsx
│   │   ├── composer/
│   │   │   ├── ComposerTab.tsx
│   │   │   ├── Canvas.tsx
│   │   │   ├── LayerPanel.tsx
│   │   │   └── BubbleTool.tsx
│   │   ├── showcase/
│   │   │   ├── ShowcaseTab.tsx
│   │   │   ├── ProjectCard.tsx
│   │   │   └── ExportModal.tsx
│   │   └── settings/
│   │       ├── SettingsTab.tsx
│   │       └── ApiConfigForm.tsx
│   ├── hooks/
│   │   ├── useApi.ts
│   │   ├── useProject.ts
│   │   └── useSwarmUI.ts
│   ├── store/
│   │   └── projectStore.ts
│   ├── types/
│   │   └── index.ts
│   ├── styles/
│   │   └── globals.css
│   ├── App.tsx
│   └── main.tsx
├── index.html
├── package.json
└── vite.config.ts
```

### 4.3 Data Models

**Project:**
```typescript
interface Project {
  id: string;
  name: string;
  createdAt: string;
  updatedAt: string;
  panels: Panel[];
  settings: ProjectSettings;
}

interface Panel {
  id: string;
  order: number;
  scene: string;
  characters: string[];
  dialogue: string;
  prompt: PromptData;
  image?: string; // base64 or file path
  layers: Layer[];
}

interface PromptData {
  turbo?: string;
  tags?: string[];
  enhanced?: string;
}

interface Layer {
  id: string;
  type: 'background' | 'character' | 'bubble' | 'effect';
  content: string;
  position: { x: number; y: number };
  size: { width: number; height: number };
  opacity: number;
  locked: boolean;
  visible: boolean;
}
```

**Settings:**
```typescript
interface AppSettings {
  api: {
    endpoint: string;
    apiKey: string;
    model: string;
    temperature: number;
    maxTokens: number;
  };
  swarmui: {
    address: string;
  };
  defaults: {
    detailLevel: number;
    autoSaveInterval: number;
    exportQuality: 'standard' | 'high';
  };
}
```

---

## 5. Acceptance Criteria

### 5.1 Core Functionality
- [ ] Application launches without errors
- [ ] All 5 tabs are accessible and functional
- [ ] Settings are persisted across sessions
- [ ] Projects can be saved and loaded

### 5.2 Tab-Specific
- [ ] Tab 1: Can input text, adjust precision, generate storyboard, reorder panels
- [ ] Tab 2: Can switch modes, enhance prompts, batch refresh
- [ ] Tab 3: Can upload images, generate via SwarmUI with status polling
- [ ] Tab 4: Canvas loads, templates work, layers manageable, bubbles functional
- [ ] Tab 5: Projects display in gallery, PDF export produces valid file

### 5.3 Visual Checkpoints
- [ ] Minimalist white theme applied consistently
- [ ] Smooth transitions between tabs (300ms)
- [ ] Hover states on all interactive elements
- [ ] Loading states during API calls
- [ ] Error states display clearly

### 5.4 Build & Package
- [ ] Frontend builds without errors
- [ ] Backend starts without errors
- [ ] Pake script generates executable
- [ ] Packaged app runs standalone

---

## 6. Constraints

- **No Gradio** - Custom React UI only
- **No Electron** - Pake WebView packaging
- **No Rust/Go** - Pure Python backend
- **Global Python** - Use existing environment, no venv
- **Local-first** - All data stored locally
