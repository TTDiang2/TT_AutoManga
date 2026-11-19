import { useState, useCallback, memo } from 'react';
import { useShallow } from 'zustand/react/shallow';
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

// memoized (no props): ComposerTab re-renders on every page edit, this
// component only when its own store selections change
export const PropertiesPanel = memo(function PropertiesPanel() {
  const { t } = useTranslation();
  const {
    updateElement,
    removeElement,
    selectElement,
    autoGap,
    setAllFrameBorders,
    snapFramesToEdge,
    commit,
  } = useComposerStore(useShallow(s => ({
    updateElement: s.updateElement,
    removeElement: s.removeElement,
    selectElement: s.selectElement,
    autoGap: s.autoGap,
    setAllFrameBorders: s.setAllFrameBorders,
    snapFramesToEdge: s.snapFramesToEdge,
    commit: s.commit,
  })));
  // narrow selectors: the panel re-renders only when the selected element
  // (or the page-wide border summary) changes, not on every canvas edit
  const selectedElement = useComposerStore(s =>
    s.pages.find(p => p.id === s.currentPageId)?.elements.find(e => e.id === s.selectedElementId));
  const { hasFrames, currentBorderWidth } = useComposerStore(useShallow(s => {
    const page = s.pages.find(p => p.id === s.currentPageId);
    const first = page?.elements.find(e => e.type === 'image-slot' || e.type === 'image');
    // the first frame's border width is the "current" value for the slider
    return {
      hasFrames: !!first,
      currentBorderWidth: (first as ImageElement | undefined)?.frameBorderWidth ?? 1.5,
    };
  }));

  // every property edit is an undo step; continuous edits of the same field
  // (slider drags, typing in a number box) coalesce into one step
  const editElement = useCallback((id: string, updates: Partial<ComposerElement>) => {
    commit(`prop:${id}:${Object.keys(updates).sort().join(',')}`);
    updateElement(id, updates);
  }, [commit, updateElement]);

  const isFrame = selectedElement?.type === 'image' || selectedElement?.type === 'image-slot' || selectedElement?.type === 'page-image';

  return (
    <div className="composer-properties" data-tour="composer-properties">
      <div className="composer-properties-header">
        {selectedElement ? `${t.composer.properties} — ${selectedElement.type}` : t.composer.properties}
      </div>
      <div className="composer-properties-body">
        {/* --- Page-wide controls (always visible) --- */}
        <PageLevelControls
          autoGap={autoGap}
          currentBorderWidth={currentBorderWidth}
          hasFrames={hasFrames}
          onBorderChange={(w) => setAllFrameBorders(w)}
          onSnap={() => snapFramesToEdge()}
        />

        {!selectedElement && (
          <div className="composer-no-selection">{t.composer.noSelection}</div>
        )}

        {selectedElement && (<>
          <PositionSizeProps element={selectedElement} updateElement={editElement} />

          {isFrame && (
            <CornerProps element={selectedElement} updateElement={editElement} />
          )}

          {selectedElement.type === 'bubble' && (
            <BubbleProps element={selectedElement as BubbleElement} updateElement={editElement} t={t} />
          )}
          {selectedElement.type === 'text' && (
            <TextProps element={selectedElement as TextElement} updateElement={editElement} t={t} />
          )}
          {selectedElement.type === 'image' && (
            <ImageProps element={selectedElement as ImageElement} updateElement={editElement} />
          )}
          {selectedElement.type === 'page-image' && (
            <ImageProps element={selectedElement as PageImageElement} updateElement={editElement} />
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
});

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
            aria-label="Frame border width"
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
            aria-label="Auto gap (%)"
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
          aria-label="X (%)"
          style={{ width: '25%' }}
        />
        <input
          className="composer-prop-input"
          type="number"
          value={Math.round(element.y)}
          onChange={e => updateElement(element.id, { y: +e.target.value })}
          placeholder="Y"
          aria-label="Y (%)"
          style={{ width: '25%' }}
        />
        <input
          className="composer-prop-input"
          type="number"
          value={Math.round(element.width)}
          onChange={e => updateElement(element.id, { width: +e.target.value })}
          placeholder="W"
          aria-label="Width (%)"
          style={{ width: '25%' }}
        />
        <input
          className="composer-prop-input"
          type="number"
          value={Math.round(element.height)}
          onChange={e => updateElement(element.id, { height: +e.target.value })}
          placeholder="H"
          aria-label="Height (%)"
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
          aria-label="Rotation (degrees)"
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
            <span className="composer-corner-key" title={labels[key]}>{labels[key]}</span>
            <input
              className="composer-prop-input"
              type="number"
              value={Math.round(corners[key].x)}
              onChange={e => setCorner(key, 'x', +e.target.value)}
              placeholder="X"
              aria-label={`${labels[key]} corner X (%)`}
            />
            <input
              className="composer-prop-input"
              type="number"
              value={Math.round(corners[key].y)}
              onChange={e => setCorner(key, 'y', +e.target.value)}
              placeholder="Y"
              aria-label={`${labels[key]} corner Y (%)`}
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
  const openImagePicker = useComposerStore(s => s.openImagePicker);
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
          aria-label="Image offset X (%)"
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
          aria-label="Image offset Y (%)"
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
          aria-label="Image scale"
        />
        <input
          className="composer-prop-input"
          type="number"
          step={0.1}
          min={0.1}
          max={4}
          value={Number(scale.toFixed(2))}
          aria-label="Image scale (number)"
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
        <label className="composer-prop-label" style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 6 }}>
          <input
            type="checkbox"
            checked={!!element.tailTip}
            disabled={element.bubbleType === 'narration'}
            onChange={e => updateElement(element.id, {
              tailTip: e.target.checked ? { x: 0.3, y: 1.6 } : undefined,
            } as Partial<BubbleElement>)}
          />
          Point tail (drag the orange handle)
        </label>
        {element.tailTip && (
          <div className="composer-prop-row" style={{ marginTop: 4 }}>
            <input
              className="composer-prop-input"
              type="number"
              step={5}
              value={Math.round(element.tailTip.x * 100)}
              onChange={e => updateElement(element.id, {
                tailTip: { ...element.tailTip!, x: (+e.target.value || 0) / 100 },
              } as Partial<BubbleElement>)}
              placeholder="Tail X"
              aria-label="Tail X (% of bubble width)"
              title="Tail tip X (% of the bubble's width)"
              style={{ width: '50%' }}
            />
            <input
              className="composer-prop-input"
              type="number"
              step={5}
              value={Math.round(element.tailTip.y * 100)}
              onChange={e => updateElement(element.id, {
                tailTip: { ...element.tailTip!, y: (+e.target.value || 0) / 100 },
              } as Partial<BubbleElement>)}
              placeholder="Tail Y"
              aria-label="Tail Y (% of bubble height)"
              title="Tail tip Y (% of the bubble's height)"
              style={{ width: '50%' }}
            />
          </div>
        )}
      </div>
      <div className="composer-prop-group">
        <span className="composer-prop-label">Text align</span>
        <div className="composer-prop-btn-group">
          {(['left', 'center', 'right'] as const).map(a => (
            <button
              key={a}
              className={`composer-prop-btn ${(element.textAlign ?? 'center') === a ? 'active' : ''}`}
              onClick={() => updateElement(element.id, {
                textAlign: a === 'center' ? undefined : a,
              } as Partial<BubbleElement>)}
            >
              {a}
            </button>
          ))}
        </div>
        <label className="composer-prop-label" style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 6 }}>
          <input
            type="checkbox"
            checked={element.markup === 'stars'}
            onChange={e => updateElement(element.id, {
              markup: e.target.checked ? 'stars' : undefined,
            } as Partial<BubbleElement>)}
          />
          *word* = emphasis
        </label>
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
          aria-label={t.composer.fontSize}
        />
      </div>
      <div className="composer-prop-group">
        <span className="composer-prop-label">{t.composer.bgColor}</span>
        <input
          type="color"
          className="composer-prop-color"
          value={element.backgroundColor}
          onChange={e => updateElement(element.id, { backgroundColor: e.target.value })}
          aria-label={t.composer.bgColor}
        />
      </div>
      <div className="composer-prop-group">
        <span className="composer-prop-label">{t.composer.borderColor}</span>
        <input
          type="color"
          className="composer-prop-color"
          value={element.borderColor}
          onChange={e => updateElement(element.id, { borderColor: e.target.value })}
          aria-label={t.composer.borderColor}
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
          aria-label={t.composer.fontSize}
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
          aria-label={t.composer.strokeWidth || 'Outline'}
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
          aria-label={t.composer.fontColor}
        />
      </div>
    </>
  );
}
