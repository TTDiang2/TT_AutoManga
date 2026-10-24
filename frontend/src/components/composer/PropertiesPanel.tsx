import { useState } from 'react';
import { useComposerStore } from '../../store/composerStore';
import { useTranslation } from '../../hooks/useTranslation';
import type { TranslationKeys } from '../../i18n';
import { DEFAULT_CORNERS } from '../../types';
import type {
  ComposerElement,
  BubbleElement,
  TextElement,
  ImageSlotElement,
  ImageElement,
  PageImageElement,
  BubbleType,
  TailPosition,
  TextDirection,
  QuadCorners,
  CornerPoint,
} from '../../types';
import { FiTrash2, FiRefreshCw } from 'react-icons/fi';

type CornerKey = 'tl' | 'tr' | 'br' | 'bl';

export function PropertiesPanel() {
  const { t } = useTranslation();
  const {
    pages,
    currentPageId,
    selectedElementId,
    updateElement,
    removeElement,
    selectElement,
    autoGap,
    setAllFrameBorders,
    snapFramesToEdge,
  } = useComposerStore();

  const currentPage = pages.find(p => p.id === currentPageId);
  const selectedElement = currentPage?.elements.find(e => e.id === selectedElementId);

  const isFrame = selectedElement?.type === 'image' || selectedElement?.type === 'image-slot' || selectedElement?.type === 'page-image';

  const frameElements = (currentPage?.elements ?? []).filter(
    e => e.type === 'image-slot' || e.type === 'image',
  );
  // Pick the border width of the first frame as the "current" value for the slider
  const currentBorderWidth =
    frameElements.length > 0
      ? (frameElements[0] as ImageElement | PageImageElement).frameBorderWidth ?? 1.5
      : 1.5;

  return (
    <div className="composer-properties">
      <div className="composer-properties-header">
        {selectedElement ? `${t.composer.properties} — ${selectedElement.type}` : t.composer.properties}
      </div>
      <div className="composer-properties-body">
        {/* --- Page-wide controls (always visible) --- */}
        <PageLevelControls
          autoGap={autoGap}
          currentBorderWidth={currentBorderWidth}
          hasFrames={frameElements.length > 0}
          onBorderChange={(w) => setAllFrameBorders(w)}
          onSnap={() => snapFramesToEdge()}
        />

        {!selectedElement && (
          <div className="composer-no-selection">{t.composer.noSelection}</div>
        )}

        {selectedElement && (<>
          <PositionSizeProps element={selectedElement} updateElement={updateElement} />

          {isFrame && (
            <CornerProps element={selectedElement} updateElement={updateElement} />
          )}

          {selectedElement.type === 'bubble' && (
            <BubbleProps element={selectedElement as BubbleElement} updateElement={updateElement} t={t} />
          )}
          {selectedElement.type === 'text' && (
            <TextProps element={selectedElement as TextElement} updateElement={updateElement} t={t} />
          )}
          {selectedElement.type === 'image' && (
            <ImageProps element={selectedElement as ImageElement} updateElement={updateElement} />
          )}
          {selectedElement.type === 'page-image' && (
            <ImageProps element={selectedElement as PageImageElement} updateElement={updateElement} />
          )}
          {selectedElement.type === 'image-slot' && (
            <div className="composer-prop-group">
              <span className="composer-prop-label">{(selectedElement as ImageSlotElement).label}</span>
              <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                Drag the central + to add an image. Drag corner handles to deform.
              </p>
            </div>
          )}
          <button
            className="composer-prop-delete"
            onClick={() => {
              removeElement(selectedElement.id);
              selectElement(null);
            }}
          >
            <FiTrash2 size={12} />
            {t.composer.deleteElement}
          </button>
        </>)}
      </div>
    </div>
  );
}

/**
 * Page-wide controls at the top of the properties sidebar — always visible.
 * Includes Auto Gap and Frame Border (both range sliders).
 */
function PageLevelControls({
  autoGap,
  currentBorderWidth,
  hasFrames,
  onBorderChange,
  onSnap,
}: {
  autoGap: (gapPercent: number) => void;
  currentBorderWidth: number;
  hasFrames: boolean;
  onBorderChange: (width: number) => void;
  onSnap: () => void;
}) {
  const [gapPercent, setGapPercent] = useState(2);
  const [borderWidth, setBorderWidth] = useState(currentBorderWidth);
  const [syncedBorderWidth, setSyncedBorderWidth] = useState(currentBorderWidth);

  // Keep local slider in sync when page/frames change (render-time reset,
  // the pattern from react.dev/learn/you-might-not-need-an-effect)
  if (syncedBorderWidth !== currentBorderWidth) {
    setSyncedBorderWidth(currentBorderWidth);
    setBorderWidth(currentBorderWidth);
  }

  const handleBorderChange = (w: number) => {
    setBorderWidth(w);
    onBorderChange(w);
  };

  return (
    <div className="composer-page-controls-wrapper">
      {/* --- Frame Border (page-wide) --- */}
      <div className="composer-prop-group composer-page-controls">
        <div className="composer-prop-label-row">
          <span className="composer-prop-label">Frame Border</span>
          <button
            className="composer-prop-mini-btn"
            onClick={() => handleBorderChange(1.5)}
            style={{ fontSize: 11 }}
          >
            Default
          </button>
        </div>
        <div className="composer-prop-row">
          <input
            className="composer-prop-input"
            type="range"
            min={0}
            max={4}
            step={0.25}
            value={borderWidth}
            onChange={e => handleBorderChange(+e.target.value)}
            style={{ width: '70%' }}
          />
          <span style={{ fontSize: 11, color: 'var(--text-muted)', width: '30%', textAlign: 'right' }}>
            {hasFrames ? `${borderWidth}px` : '—'}
          </span>
        </div>
      </div>

      {/* --- Snap to Edge (page-wide) --- */}
      <div className="composer-prop-group composer-page-controls">
        <div className="composer-prop-label-row">
          <span className="composer-prop-label">Snap to Edge</span>
        </div>
        <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 8 }}>
          Snap frames near the page boundary so their edges become parallel to
          the page edge with a uniform 2% margin.
        </p>
        <button
          className="composer-prop-apply-btn"
          onClick={onSnap}
          style={{ width: '100%' }}
        >
          Snap to Edge
        </button>
      </div>

      {/* --- Auto Gap (page-wide) --- */}
      <div className="composer-prop-group composer-page-controls">
        <div className="composer-prop-label-row">
          <span className="composer-prop-label">Auto Gap</span>
        </div>
        <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 8 }}>
          Insert a uniform gap between touching frames. Frames stay in place; touching
          edges shrink by the gap.
        </p>
        <div className="composer-prop-row">
          <input
            className="composer-prop-input"
            type="range"
            min={0}
            max={10}
            step={0.5}
            value={gapPercent}
            onChange={e => setGapPercent(+e.target.value)}
            style={{ width: '70%' }}
          />
          <span style={{ fontSize: 11, color: 'var(--text-muted)', width: '15%', textAlign: 'right' }}>
            {gapPercent}%
          </span>
          <button
            className="composer-prop-apply-btn"
            onClick={() => autoGap(gapPercent)}
            style={{ width: '15%', padding: 0, fontSize: 11 }}
          >
            Apply
          </button>
        </div>
      </div>
    </div>
  );
}

function PositionSizeProps({
  element,
  updateElement,
}: {
  element: ComposerElement;
  updateElement: (id: string, u: Partial<ComposerElement>) => void;
}) {
  return (
    <div className="composer-prop-group">
      <span className="composer-prop-label">Position &amp; Size</span>
      <div className="composer-prop-row">
        <input
          className="composer-prop-input"
          type="number"
          value={Math.round(element.x)}
          onChange={e => updateElement(element.id, { x: +e.target.value })}
          placeholder="X"
          style={{ width: '25%' }}
        />
        <input
          className="composer-prop-input"
          type="number"
          value={Math.round(element.y)}
          onChange={e => updateElement(element.id, { y: +e.target.value })}
          placeholder="Y"
          style={{ width: '25%' }}
        />
        <input
          className="composer-prop-input"
          type="number"
          value={Math.round(element.width)}
          onChange={e => updateElement(element.id, { width: +e.target.value })}
          placeholder="W"
          style={{ width: '25%' }}
        />
        <input
          className="composer-prop-input"
          type="number"
          value={Math.round(element.height)}
          onChange={e => updateElement(element.id, { height: +e.target.value })}
          placeholder="H"
          style={{ width: '25%' }}
        />
      </div>
      <div className="composer-prop-row" style={{ marginTop: 4 }}>
        <input
          className="composer-prop-input"
          type="number"
          value={Math.round(element.rotation)}
          onChange={e => updateElement(element.id, { rotation: +e.target.value })}
          placeholder="Rotation"
          style={{ width: '50%' }}
        />
      </div>
    </div>
  );
}

/**
 * 4-corner editor for image / image-slot elements. Each corner has X/Y percent
 * inputs relative to the element's bounding box (0-100).
 */
function CornerProps({
  element,
  updateElement,
}: {
  element: ComposerElement;
  updateElement: (id: string, u: Partial<ComposerElement>) => void;
}) {
  const corners: QuadCorners = element.corners ?? DEFAULT_CORNERS;
  const labels: Record<CornerKey, string> = {
    tl: 'Top-Left',
    tr: 'Top-Right',
    br: 'Bottom-Right',
    bl: 'Bottom-Left',
  };
  const order: CornerKey[] = ['tl', 'tr', 'br', 'bl'];

  const setCorner = (key: CornerKey, axis: 'x' | 'y', value: number) => {
    const clamped = Math.max(-100, Math.min(200, value));
    const next: QuadCorners = {
      ...corners,
      [key]: { ...corners[key], [axis]: clamped } as CornerPoint,
    };
    updateElement(element.id, { corners: next });
  };

  return (
    <div className="composer-prop-group">
      <div className="composer-prop-label-row">
        <span className="composer-prop-label">Corners</span>
        <button
          className="composer-prop-mini-btn"
          onClick={() => updateElement(element.id, { corners: { ...DEFAULT_CORNERS } })}
          title="Reset to rectangle"
        >
          Reset
        </button>
      </div>
      <div className="composer-corner-grid">
        {order.map(key => (
          <div key={key} className="composer-corner-row">
            <span className="composer-corner-key">{labels[key]}</span>
            <input
              className="composer-prop-input"
              type="number"
              value={Math.round(corners[key].x)}
              onChange={e => setCorner(key, 'x', +e.target.value)}
              placeholder="X"
            />
            <input
              className="composer-prop-input"
              type="number"
              value={Math.round(corners[key].y)}
              onChange={e => setCorner(key, 'y', +e.target.value)}
              placeholder="Y"
            />
          </div>
        ))}
      </div>
    </div>
  );
}

function ImageProps({
  element,
  updateElement,
}: {
  element: ImageElement | PageImageElement;
  updateElement: (id: string, u: Partial<ComposerElement>) => void;
}) {
  const { openImagePicker } = useComposerStore();
  const offX = element.imageOffsetX ?? 0;
  const offY = element.imageOffsetY ?? 0;
  const isOffset = offX !== 0 || offY !== 0;
  const scale = element.imageScale ?? 1;
  const isScaled = scale !== 1;
  const pickerKind = element.type === 'page-image' ? 'pageImage' : 'slot';
  return (
    <>
    <div className="composer-prop-group">
      <div className="composer-prop-label-row">
        <span className="composer-prop-label">Image</span>
      </div>
      <div className="composer-prop-row" style={{ marginBottom: 8 }}>
        <button
          className="composer-prop-btn"
          style={{ gap: 4, fontSize: 12, padding: '4px 12px', width: '100%' }}
          onClick={() => openImagePicker({ kind: pickerKind, id: element.id })}
        >
          <FiRefreshCw size={12} /> Replace Image
        </button>
      </div>
    </div>
    <div className="composer-prop-group">
      <div className="composer-prop-label-row">
        <span className="composer-prop-label">Image Offset</span>
        {isOffset && (
          <button
            className="composer-prop-mini-btn"
            onClick={() =>
              updateElement(element.id, {
                imageOffsetX: 0,
                imageOffsetY: 0,
              } as Partial<ImageElement>)
            }
          >
            Reset
          </button>
        )}
      </div>
      <div className="composer-prop-row">
        <input
          className="composer-prop-input"
          type="number"
          step={1}
          min={-100}
          max={100}
          value={Math.round(offX)}
          onChange={e =>
            updateElement(element.id, {
              imageOffsetX: Math.max(-100, Math.min(100, +e.target.value || 0)),
            } as Partial<ImageElement>)
          }
          placeholder="Offset X (%)"
          style={{ width: '50%' }}
          title="Horizontal image offset (% of frame width)"
        />
        <input
          className="composer-prop-input"
          type="number"
          step={1}
          min={-100}
          max={100}
          value={Math.round(offY)}
          onChange={e =>
            updateElement(element.id, {
              imageOffsetY: Math.max(-100, Math.min(100, +e.target.value || 0)),
            } as Partial<ImageElement>)
          }
          placeholder="Offset Y (%)"
          style={{ width: '50%' }}
          title="Vertical image offset (% of frame height)"
        />
      </div>

      <div className="composer-prop-label-row" style={{ marginTop: 10 }}>
        <span className="composer-prop-label">Image Scale</span>
        {isScaled && (
          <button
            className="composer-prop-mini-btn"
            onClick={() =>
              updateElement(element.id, {
                imageScale: 1,
              } as Partial<ImageElement>)
            }
          >
            Reset
          </button>
        )}
      </div>
      <div className="composer-prop-row">
        <input
          className="composer-prop-input"
          type="range"
          min={0.1}
          max={4}
          step={0.05}
          value={scale}
          onChange={e =>
            updateElement(element.id, {
              imageScale: Math.max(0.1, Math.min(4, +e.target.value || 1)),
            } as Partial<ImageElement>)
          }
          title="Scale image within the frame"
        />
        <input
          className="composer-prop-input"
          type="number"
          step={0.1}
          min={0.1}
          max={4}
          value={Number(scale.toFixed(2))}
          onChange={e =>
            updateElement(element.id, {
              imageScale: Math.max(0.1, Math.min(4, +e.target.value || 1)),
            } as Partial<ImageElement>)
          }
          style={{ width: '60px' }}
        />
      </div>

      <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 6 }}>
        Drag the image body inside the frame to reposition. Reshape the frame with its corner handles.
        Use the scale slider to zoom the image within the frame.
      </p>
    </div>
    </>
  );
}

function BubbleProps({
  element,
  updateElement,
  t,
}: {
  element: BubbleElement;
  updateElement: (id: string, u: Partial<ComposerElement>) => void;
  t: TranslationKeys;
}) {
  const bubbleTypes: BubbleType[] = ['speech', 'thought', 'shout', 'whisper', 'narration', 'inner-voice'];
  const tailPositions: TailPosition[] = ['top', 'bottom', 'left', 'right'];
  const directions: TextDirection[] = ['horizontal', 'vertical'];

  return (
    <>
      {element.speaker && (
        <div className="composer-prop-group">
          <span className="composer-prop-label">{t.composer.speaker || 'Speaker'}</span>
          <span className="composer-prop-label" style={{ fontWeight: 600 }}>
            {element.speaker}
          </span>
        </div>
      )}
      <div className="composer-prop-group">
        <span className="composer-prop-label">{t.composer.bubble}</span>
        <div className="composer-prop-btn-group">
          {bubbleTypes.map(bt => (
            <button
              key={bt}
              className={`composer-prop-btn ${element.bubbleType === bt ? 'active' : ''}`}
              onClick={() => updateElement(element.id, { bubbleType: bt })}
            >
              {bt === 'inner-voice' ? t.composer.innerVoice : bt}
            </button>
          ))}
        </div>
      </div>
      <div className="composer-prop-group">
        <span className="composer-prop-label">{t.composer.tailPosition}</span>
        <div className="composer-prop-btn-group">
          {tailPositions.map(tp => (
            <button
              key={tp}
              className={`composer-prop-btn ${element.tailPosition === tp ? 'active' : ''}`}
              onClick={() => updateElement(element.id, { tailPosition: tp })}
            >
              {tp}
            </button>
          ))}
        </div>
      </div>
      <div className="composer-prop-group">
        <span className="composer-prop-label">{t.composer.direction}</span>
        <div className="composer-prop-btn-group">
          {directions.map(d => (
            <button
              key={d}
              className={`composer-prop-btn ${element.direction === d ? 'active' : ''}`}
              onClick={() => updateElement(element.id, { direction: d })}
            >
              {d === 'horizontal' ? t.composer.horizontal : t.composer.vertical}
            </button>
          ))}
        </div>
      </div>
      <div className="composer-prop-group">
        <span className="composer-prop-label">{t.composer.fontSize}</span>
        <input
          className="composer-prop-input"
          type="number"
          min={8}
          max={72}
          value={element.fontSize}
          onChange={e => updateElement(element.id, { fontSize: +e.target.value })}
        />
      </div>
      <div className="composer-prop-group">
        <span className="composer-prop-label">{t.composer.bgColor}</span>
        <input
          type="color"
          className="composer-prop-color"
          value={element.backgroundColor}
          onChange={e => updateElement(element.id, { backgroundColor: e.target.value })}
        />
      </div>
      <div className="composer-prop-group">
        <span className="composer-prop-label">{t.composer.borderColor}</span>
        <input
          type="color"
          className="composer-prop-color"
          value={element.borderColor}
          onChange={e => updateElement(element.id, { borderColor: e.target.value })}
        />
      </div>
    </>
  );
}

function TextProps({
  element,
  updateElement,
  t,
}: {
  element: TextElement;
  updateElement: (id: string, u: Partial<ComposerElement>) => void;
  t: TranslationKeys;
}) {
  const directions: TextDirection[] = ['horizontal', 'vertical'];
  const aligns: Array<'left' | 'center' | 'right'> = ['left', 'center', 'right'];

  return (
    <>
      <div className="composer-prop-group">
        <span className="composer-prop-label">{t.composer.fontSize}</span>
        <input
          className="composer-prop-input"
          type="number"
          min={8}
          max={120}
          value={element.fontSize}
          onChange={e => updateElement(element.id, { fontSize: +e.target.value })}
        />
      </div>
      <div className="composer-prop-group">
        <span className="composer-prop-label">{t.composer.strokeWidth || 'Outline'}</span>
        <input
          className="composer-prop-input"
          type="number"
          min={0}
          max={20}
          value={element.strokeWidth ?? 0}
          onChange={e => updateElement(element.id, {
            strokeWidth: Math.max(0, Math.min(20, +e.target.value || 0)),
          })}
        />
      </div>
      <div className="composer-prop-group">
        <span className="composer-prop-label">{t.composer.fontWeight}</span>
        <div className="composer-prop-btn-group">
          {['normal', 'bold'].map(w => (
            <button
              key={w}
              className={`composer-prop-btn ${element.fontWeight === w ? 'active' : ''}`}
              onClick={() => updateElement(element.id, { fontWeight: w })}
            >
              {w}
            </button>
          ))}
        </div>
      </div>
      <div className="composer-prop-group">
        <span className="composer-prop-label">{t.composer.textAlign}</span>
        <div className="composer-prop-btn-group">
          {aligns.map(a => (
            <button
              key={a}
              className={`composer-prop-btn ${element.textAlign === a ? 'active' : ''}`}
              onClick={() => updateElement(element.id, { textAlign: a })}
            >
              {a === 'left' ? t.composer.alignLeft : a === 'center' ? t.composer.alignCenter : t.composer.alignRight}
            </button>
          ))}
        </div>
      </div>
      <div className="composer-prop-group">
        <span className="composer-prop-label">{t.composer.direction}</span>
        <div className="composer-prop-btn-group">
          {directions.map(d => (
            <button
              key={d}
              className={`composer-prop-btn ${element.direction === d ? 'active' : ''}`}
              onClick={() => updateElement(element.id, { direction: d })}
            >
              {d === 'horizontal' ? t.composer.horizontal : t.composer.vertical}
            </button>
          ))}
        </div>
      </div>
      <div className="composer-prop-group">
        <span className="composer-prop-label">{t.composer.fontColor}</span>
        <input
          type="color"
          className="composer-prop-color"
          value={element.color}
          onChange={e => updateElement(element.id, { color: e.target.value })}
        />
      </div>
    </>
  );
}
