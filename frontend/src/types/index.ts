export interface Panel {
  id: string;
  order: number;
  scene: string;
  characters: string[];
  dialogue: string;
  prompt: PromptData;
  image?: string;
  shot?: string;   // wide|medium|close-up|extreme-close-up|splash
}

export interface PromptData {
  turbo?: string;
  tags?: string[];
  enhanced?: string;
  negativePrompt?: string;
  seed?: number;
  removeBG?: boolean;
}

export interface Project {
  id: string;
  name: string;
  createdAt: string;
  updatedAt: string;
  panels: Panel[];
  settings: ProjectSettings;
  composerPages?: ComposerPage[];
}

export interface ProjectSettings {
  detailLevel: number;
}

export interface PromptPreset {
  id: string;
  name: string;
  content: string;
}

export interface AppSettings {
  api: {
    endpoint: string;
    api_key: string;
    model: string;
    temperature: number;
    max_tokens: number;
    thinking: boolean;
    storyboard_system_prompt: string;
    prompt_system_prompt: string;
    storyboardPresets: PromptPreset[];
    promptPresets: PromptPreset[];
  };
  swarmui: {
    address: string;
    activePresetId: string;
    presets: SwarmUIPreset[];
    currentModel: string;
    currentLoras: LoraConfig[];
    currentSteps: number;
    currentCfgScale: number;
    currentWidth: number;
    currentHeight: number;
    currentSamplerName: string;
    promptSuffix: string;
  };
  defaults: {
    detailLevel: number;
    autoSaveInterval: number;
    exportQuality: string;
  };
  language: string;
}

export interface LoraConfig {
  name: string;
  weight: number;
}

export interface SwarmUIPreset {
  id: string;
  name: string;
  model: string;
  loras: LoraConfig[];
  steps: number;
  cfgScale: number;
  width: number;
  height: number;
  samplerName: string;
  promptSuffix: string;
}

export type TabId = 'storyboard' | 'prompt' | 'assets' | 'composer' | 'showcase' | 'settings' | 'characters';

export type BubbleType = 'speech' | 'thought' | 'shout' | 'whisper' | 'narration' | 'inner-voice';

export interface DialogueBubble {
  id: string;
  text: string;
  x: number;
  y: number;
  width: number;
  height: number;
  rotation: number;
  type: BubbleType;
  opacity: number;
  backgroundColor: string;
  borderColor: string;
}

export interface BubbleTemplate {
  id: string;
  name: string;
  layout: number[];
}

export interface PanelDefinition {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface CanvasDefinition {
  width: number;
  height: number;
}

export interface LayoutDefinition {
  id: string;
  name: string;
  canvas: CanvasDefinition;
  panels: PanelDefinition[];
  is_preset?: boolean;
}

export interface Character {
  id: string;
  name: string;
  description: string;
  appearance?: string;
  image?: string;
  sourcePanelIds: string[];
  createdAt: string;
  updatedAt: string;
}

export interface CharacterTemplate {
  id: string;
  name: string;
  description: string;
  appearance?: string;
  image?: string;
  isBuiltIn: boolean;
  createdAt: string;
}

// --- Composer Types ---

export type ComposerElementType = 'image-slot' | 'image' | 'page-image' | 'text' | 'bubble';

export type TextDirection = 'horizontal' | 'vertical';

/**
 * Four corners of a non-rectangular frame, each given as a percentage (0-100)
 * offset relative to the element's own bounding box (x = rightward, y = downward).
 * Default rectangle: tl=(0,0) tr=(100,0) br=(100,100) bl=(0,100).
 * Rendered as an SVG polygon + clip-path; corner handle drag mutates these values.
 */
export interface CornerPoint {
  x: number;
  y: number;
}

export interface QuadCorners {
  tl: CornerPoint;
  tr: CornerPoint;
  br: CornerPoint;
  bl: CornerPoint;
}

export const DEFAULT_CORNERS: QuadCorners = {
  tl: { x: 0, y: 0 },
  tr: { x: 100, y: 0 },
  br: { x: 100, y: 100 },
  bl: { x: 0, y: 100 },
};

export type TailPosition = 'top' | 'bottom' | 'left' | 'right';

export interface ComposerPage {
  id: string;
  name: string;
  templateId: string;
  width: number;
  height: number;
  elements: ComposerElement[];
  order: number;
}

export type ComposerElement = ImageSlotElement | ImageElement | PageImageElement | TextElement | BubbleElement;

export interface ComposerElementBase {
  id: string;
  type: ComposerElementType;
  x: number;
  y: number;
  width: number;
  height: number;
  rotation: number;
  zIndex: number;
  locked: boolean;
  visible: boolean;
  /**
   * Optional quadrilateral corners. Omit (or set to DEFAULT_CORNERS) for a plain
   * rectangle. Currently honored by image-slot and image elements; text/bubble
   * ignore it and remain rectangular.
   */
  corners?: QuadCorners;
  /**
   * Frame border thickness in SVG pixels. Applies to image-slot and image
   * elements (manga-style black panel outline). Defaults to 1.5 when absent.
   */
  frameBorderWidth?: number;
}

export interface ImageSlotElement extends ComposerElementBase {
  type: 'image-slot';
  label: string;
}

export interface ImageElement extends ComposerElementBase {
  type: 'image';
  src: string;
  cropArea?: { x: number; y: number; width: number; height: number };
  originalSrc?: string;
  /**
   * Image translation inside its frame, as a percentage of the element's
   * bounding-box dimensions. (0, 0) = default position filling the bbox.
   * Positive X shifts the image to the right, positive Y shifts it down.
   * The frame's clip-path (polygon) stays fixed; the visible window simply
   * reveals different parts of the translated image.
   */
  imageOffsetX?: number;
  imageOffsetY?: number;
  /**
   * Image scale inside its frame. 1.0 = fill bbox exactly (subject to
   * offset). 2.0 = image twice as large (more zoom). 0.5 = half size.
   * Scale center is the bbox center.
   */
  imageScale?: number;
}

/**
 * A free-floating page image that is NOT bound to a slot — it is added directly
 * to the canvas via the "Add Image" toolbar button and floats above the page
 * like a sticker. It shares the same 4-corner quadrilateral rendering and
 * image offset/scale as {@link ImageElement}, but is never seeded from a
 * template (templates never carry page-image geometry; saving a template
 * downgrades page-image to image-slot).
 */
export interface PageImageElement extends ComposerElementBase {
  type: 'page-image';
  src: string;
  /**
   * Image translation inside its frame, as a percentage of the element's
   * bounding-box dimensions. (0, 0) = default position filling the bbox.
   * Positive X shifts the image to the right, positive Y shifts it down.
   * The frame's clip-path (polygon) stays fixed; the visible window simply
   * reveals different parts of the translated image.
   */
  imageOffsetX?: number;
  imageOffsetY?: number;
  /**
   * Image scale inside its frame. 1.0 = fill bbox exactly (subject to
   * offset). 2.0 = image twice as large (more zoom). 0.5 = half size.
   * Scale center is the bbox center.
   */
  imageScale?: number;
}

export interface TextElement extends ComposerElementBase {
  type: 'text';
  content: string;
  fontSize: number;
  fontFamily: string;
  color: string;
  direction: TextDirection;
  fontWeight: string;
  textAlign: 'left' | 'center' | 'right';
  strokeWidth?: number;   // px at 1x page scale; >0 draws an outline (SFX look)
  strokeColor?: string;
}

export interface BubbleElement extends ComposerElementBase {
  type: 'bubble';
  bubbleType: BubbleType;
  text: string;
  speaker?: string;   // set by assembly when dialogue is "Name：台词"
  direction: TextDirection;
  fontSize: number;
  backgroundColor: string;
  borderColor: string;
  tailPosition: TailPosition;
}

export interface ComposerTemplate {
  id: string;
  name: string;
  nameZh: string;
  width: number;
  height: number;
  elements: (Omit<ComposerElementBase, 'id' | 'zIndex' | 'locked' | 'visible'> & { label?: string })[];
}

/**
 * A user-saved composer template. Identical shape to ComposerTemplate on the
 * geometry side, plus optional timestamps so the backend can sort them.
 * Persisted via `/api/composer/templates` (see backend/api/composer_templates.py).
 *
 * NOTE: image payload (`src`) is intentionally never stored here — saving
 * a template captures geometry only. Elements that were images on the source
 * page are downgraded to empty slots when applied.
 */
export interface SavedTemplateElement extends Omit<ComposerElementBase, 'id' | 'zIndex' | 'locked' | 'visible'> {
  type: ComposerElementType;
  label?: string;
}

export interface SavedTemplate {
  id: string;
  name: string;
  width: number;
  height: number;
  elements: SavedTemplateElement[];
  created_at?: string;
  updated_at?: string;
}
