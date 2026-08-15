# AutoManga Frontend Design Language

## 1. Stack

- **Framework**: React 18 + TypeScript (strict)
- **Build**: Vite
- **State**: Zustand (with `persist` middleware for project store)
- **Icons**: `react-icons/fi` (Feather Icons)
- **CSS**: Pure CSS (no Tailwind, no CSS-in-JS) — custom design tokens in `globals.css`

## 2. Color System (global CSS custom properties)

Defined in `frontend/src/assets/globals.css`.

### Backgrounds
| Token | Usage |
|---|---|
| `--bg-primary` | Main page / panel background |
| `--bg-secondary` | Sidebar, secondary panels |
| `--bg-tertiary` | Hover states, subtle emphasis |
| `--bg-hover` | Interactive hover, selected items |

### Accent
| Token | Usage |
|---|---|
| `--accent-primary` | Primary actions, active nav, filled buttons |
| `--accent-hover` | Darker hover variant of accent |
| `--accent-soft` | Transparent/low-opacity accent (badges, backgrounds) |
| `--accent-text` | Text on accent backgrounds (usually white) |

### Text
| Token | Usage |
|---|---|
| `--text-primary` | Primary content |
| `--text-secondary` | Less prominent text |
| `--text-muted` | Placeholder, disabled, hints |

### Borders
| Token | Usage |
|---|---|
| `--border-default` | Default border color |
| `--border-hover` | Border on hover / focus |

### Shadows
| Token | Usage |
|---|---|
| `--shadow-elevated` | Dropdowns, modals |
| `--shadow-focus` | Input focus ring |

### Other
| Token | Usage |
|---|---|
| `--radius-sm` | Small border radius (4-6px) |
| `--transition-default` | Standard transition speed |
| `--space-xs / sm / md / lg / xl` | Sizing spacers |

## 3. Typography

- **Font**: System font stack (no custom fonts)
- **Body**: 13-14px
- **Labels / meta**: 11-12px
- **Nav items**: 12px
- **Headers**: section‑specific, not part of a global scale
- **Line height**: 1.5 (body), 1.2 (headings)
- **Font weight**: 400 (normal), 500 (medium), 600 (semibold)

## 4. Layout

### App shell
```
┌────────────────────────────────┐
│  Sidebar (64px) │ Main Content │
│                 │              │
│  nav items      │ tab content  │
│  (icon + label) │ fills height │
│                 │              │
└────────────────────────────────┘
```

- Sidebar: fixed `width: 64px`, `height: 100vh`, `overflow: hidden`
- Main content: `flex: 1`, `overflow: auto`
- `.app-layout`: display flex, fills viewport
- `.sidebar`: fixed-width nav column
- `.main-content`: flex-grow scrollable area

### Tab structure
Each tab is a separate component under `frontend/src/components/`. Tabs use a shared header style with title + description + action buttons.

## 5. Components

### Buttons
| Class | Style | Use |
|---|---|---|
| `.btn` | Base button | Reset defaults |
| `.btn-primary` | Accent bg + white text | Primary CTA |
| `.btn-secondary` | Bordered, light bg | Secondary action |
| `.btn-ghost` | Transparent bg | Tertiary / icon buttons |
| `.btn-danger` | Red text / bg | Destructive action |

All buttons have `border-radius: var(--radius-sm)`, `transition: var(--transition-default)`, and consistent `padding: 6px 12px` or `padding: 8px 16px` depending on context.

### Inputs
| Class | Style |
|---|---|
| `.input` | Bordered, rounded, consistent padding |
| `.input-sm` | Smaller variant |

- `border: 1px solid var(--border-default)`
- `border-radius: var(--radius-sm)`
- `background: var(--bg-primary)`
- `:focus` → `border-color: var(--accent-primary)` + `box-shadow: var(--shadow-focus)`

Select elements follow same styling as inputs.

### Cards
- `.card`: white background, `var(--radius-sm)` rounded, `var(--shadow-elevated)` shadow
- Used for archive items, asset previews

### Sliders (range inputs)
- Styled with custom `accent-color: var(--accent-primary)`
- Standard height 4px track, circular thumb
- `input[type='range'] { accent-color: var(--accent-primary) }`

### Badges / Tags
- `.badge`: small inline pill, `background: var(--accent-soft)`, `color: var(--accent-primary)`
- `border-radius: 99px`, `font-size: 11px`, `padding: 2px 8px`

### Modals
- `.modal-overlay`: fixed fullscreen, semi-transparent `--bg-primary` backdrop, `z-index: 1000`
- `.modal-content`: centered card with `width: 400px` (or `460px`), `max-height: 80vh`, scrollable
- Close via X button or backdrop click

### Empty states
- `.empty-state`: centered text block with muted text and an icon, used when no data exists

### Loading spinner
- `.loading-spinner`: CSS-only 20px rotating circle
- Uses `var(--accent-primary)` for the visible arc

## 6. Sidebar Navigation

```
┌────┐
│ 🔲 │ Project
│ 🔲 │ Composer
│ 🔲 │ Prompt Lab
│ 🔲 │ Assets
│ 🔲 │ Characters
└────┘
```

- `.nav-item`: flex column, centered, `padding: 12px 0`
- `.nav-item.active`: `background: var(--accent-primary)`, `color: white`
- `.nav-item .nav-icon`: 20x20 icon
- `.nav-item .nav-label`: 12px text below icon

## 7. State Management

### Zustand stores
- **`projectStore`**: global project data with `persist` middleware (saves to `localStorage`). Contains `panels`, `prompts`, `language`.
- **`composerStore`**: canvas/template state, NO persistence. Contains `pages`, `currentPageId`, `selectedElementId`, `zoom`, and actions like `addFrame`, `autoGap`, `snapFramesToEdge`.
- **`useTranslation()`**: reads `language` from projectStore and looks up keys from `i18n/index.ts`.

### Store patterns (Zustand)
```
const { pages, currentPageId, addFrame, autoGap } = useComposerStore();
const { t } = useTranslation();
```

## 8. File Structure

```
frontend/src/
  assets/
    globals.css          # Design tokens + global component classes
  components/
    App.tsx              # App shell with sidebar + route
    sidebar/
      Sidebar.tsx        # Nav items
    composer/
      ComposerTab.tsx    # Canvas + toolbar + properties panel
      Canvas.tsx         # Frame/image rendering with clip-path + SVG overlay
      PropertiesPanel.tsx # Element properties + page-wide controls
      composer.css       # All composer styles
    prompt/
      PromptLabTab.tsx   # Prompt editing per panel
    assets/
      AssetTab.tsx       # Image generation + archive management
  i18n/
    index.ts             # EN/ZH translations
  store/
    projectStore.ts      # Zustand store for projects (persisted)
    composerStore.ts     # Zustand store for canvas (non-persisted)
  types/
    index.ts             # All TypeScript interfaces (Panel, PromptData, ComposerPage, etc.)
  hooks/
    useTranslation.ts    # i18n hook
```

## 9. Manga / Composer Specifics

- **Canvas**: SVG overlay for quadrilateral frame outlines (`clip-path` for content, SVG `<polygon>` for border)
- **Frames**: `image-slot` (empty panel frame), `image` (filled panel), `page-image` (breakout floating image)
- **Templates**: defined as `ComposerTemplate[]` with `genRows()` helper that generates frames from row/column specifications
- **Properties Panel**: page-wide controls (Frame Border, Snap to Edge, Auto Gap) always visible at top; element-specific props below when an element is selected
- **Quadrilateral corners**: each frame stores 4 corner points (`tl`, `tr`, `br`, `bl`) as `{x, y}` in bbox-%, enabling non-rectangular frame shapes

## 10. Responsive Behavior

- The app is desktop-focused, no explicit mobile breakpoints
- Main layout uses `height: 100vh` / `height: calc(100vh - ...)` to fill the viewport
- Scrollable areas use `overflow: auto` with consistent scrollbar styling

## 11. Migration Checklist

When reusing this design system in another project:
1. Copy `globals.css` — adjust token values (colors, radii, spacing) for the new brand
2. Import the CSS variables and component classes
3. Use Zustand with the same `persist` pattern if localStorage persistence is needed
4. Follow the `sidebar + main-content` layout for multi-tab apps
5. Use `react-icons/fi` for icon consistency
6. Follow the i18n pattern with a translation hook + key-indexed dictionary
