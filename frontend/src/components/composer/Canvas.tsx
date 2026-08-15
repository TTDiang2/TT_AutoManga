import { useState, useRef, useCallback, useEffect } from 'react';
import { FiPlus } from 'react-icons/fi';
import { useComposerStore } from '../../store/composerStore';
import { ImagePicker } from './ImagePicker';
import { DEFAULT_CORNERS } from '../../types';
import type {
  ComposerElement,
  BubbleElement,
  TextElement,
  ImageElement,
  ImageSlotElement,
  PageImageElement,
  QuadCorners,
} from '../../types';

type CornerKey = 'tl' | 'tr' | 'br' | 'bl';

export function Canvas() {
  const {
    pages,
    currentPageId,
    selectedElementId,
    activeTool,
    activeBubbleType,
    zoom,
    updateElement,
    selectElement,
    addElement,
    convertSlotToImage,
    setActiveTool,
    _pushHistory,
    imagePickerRequest,
    closeImagePicker,
  } = useComposerStore();

  const currentPage = pages.find(p => p.id === currentPageId);

  const [dragState, setDragState] = useState<{
    elementId: string;
    startX: number;
    startY: number;
    origX: number;
    origY: number;
    origW: number;
    origH: number;
    origCorners?: QuadCorners;
    mode: 'move' | 'resize' | 'corner' | 'image-move';
    handle?: string;
    corner?: CornerKey;
    origOffsetX?: number;
    origOffsetY?: number;
  } | null>(null);

  const [editingId, setEditingId] = useState<string | null>(null);
  const canvasRef = useRef<HTMLDivElement>(null);

  const handleElementMouseDown = useCallback((e: React.MouseEvent, elementId: string) => {
    if (activeTool === 'crop' || activeTool === 'text' || activeTool === 'bubble') return;
    e.stopPropagation();
    const el = currentPage?.elements.find(p => p.id === elementId);
    if (!el || el.locked) return;
    selectElement(elementId);
    setDragState({
      elementId,
      startX: e.clientX,
      startY: e.clientY,
      origX: el.x,
      origY: el.y,
      origW: el.width,
      origH: el.height,
      mode: 'move',
    });
  }, [activeTool, currentPage, selectElement]);

  const handleResizeMouseDown = useCallback((e: React.MouseEvent, elementId: string, handle: string) => {
    e.stopPropagation();
    e.preventDefault();
    const el = currentPage?.elements.find(p => p.id === elementId);
    if (!el || el.locked) return;
    selectElement(elementId);
    setDragState({
      elementId,
      startX: e.clientX,
      startY: e.clientY,
      origX: el.x,
      origY: el.y,
      origW: el.width,
      origH: el.height,
      mode: 'resize',
      handle,
    });
  }, [currentPage, selectElement]);

  const handleCornerMouseDown = useCallback((e: React.MouseEvent, elementId: string, corner: CornerKey) => {
    e.stopPropagation();
    e.preventDefault();
    const el = currentPage?.elements.find(p => p.id === elementId);
    if (!el || el.locked) return;
    selectElement(elementId);
    _pushHistory();
    setDragState({
      elementId,
      startX: e.clientX,
      startY: e.clientY,
      origX: el.x,
      origY: el.y,
      origW: el.width,
      origH: el.height,
      origCorners: el.corners ? { ...el.corners } : { ...DEFAULT_CORNERS },
      mode: 'corner',
      corner,
    });
  }, [currentPage, selectElement, _pushHistory]);

  // Click-drag on the visible image inside a frame repositions the image within
  // the frame (clip-path hides overflow). The frame bbox/corners stay put.
  // Applies to both `image` (slot-filled) and `page-image` (breakout) types.
  const handleImageMouseDown = useCallback((e: React.MouseEvent, elementId: string) => {
    if (activeTool !== 'select') return;
    e.stopPropagation();
    const el = currentPage?.elements.find(p => p.id === elementId);
    if (!el || el.locked) return;
    if (el.type !== 'image' && el.type !== 'page-image') return;
    const offsetX = (el as ImageElement | PageImageElement).imageOffsetX ?? 0;
    const offsetY = (el as ImageElement | PageImageElement).imageOffsetY ?? 0;
    selectElement(elementId);
    _pushHistory();
    setDragState({
      elementId,
      startX: e.clientX,
      startY: e.clientY,
      origX: el.x,
      origY: el.y,
      origW: el.width,
      origH: el.height,
      mode: 'image-move',
      origOffsetX: offsetX,
      origOffsetY: offsetY,
    });
  }, [activeTool, currentPage, selectElement, _pushHistory]);

  // Ctrl/Alt + wheel on an image scales it within the frame. This is the
  // fastest way to "resize" the image without picking up a slider.
  // Applies to both `image` and `page-image` types.
  const handleImageWheel = useCallback((e: React.WheelEvent, elementId: string) => {
    if (activeTool !== 'select') return;
    if (!e.ctrlKey && !e.metaKey) return;
    const el = currentPage?.elements.find(p => p.id === elementId);
    if (!el || el.locked) return;
    if (el.type !== 'image' && el.type !== 'page-image') return;
    e.stopPropagation();
    e.preventDefault();
    const img = el as ImageElement | PageImageElement;
    const next = Math.max(0.1, Math.min(4, (img.imageScale ?? 1) * (e.deltaY < 0 ? 1.05 : 1 / 1.05)));
    updateElement(elementId, { imageScale: next } as Partial<ImageElement>);
  }, [activeTool, currentPage, updateElement]);

  useEffect(() => {
    if (!dragState) return;
    const handleMouseMove = (e: MouseEvent) => {
      const canvasEl = canvasRef.current;
      if (!canvasEl) return;
      const rect = canvasEl.getBoundingClientRect();
      const deltaX = ((e.clientX - dragState.startX) / rect.width) * 100;
      const deltaY = ((e.clientY - dragState.startY) / rect.height) * 100;

      if (dragState.mode === 'move') {
        const newX = Math.max(0, Math.min(100 - dragState.origW, dragState.origX + deltaX));
        const newY = Math.max(0, Math.min(100 - dragState.origH, dragState.origY + deltaY));
        updateElement(dragState.elementId, { x: newX, y: newY });
      } else if (dragState.mode === 'resize' && dragState.handle) {
        const minSize = 3;
        let { origX, origY, origW, origH } = dragState;
        let newX = origX, newY = origY, newW = origW, newH = origH;

        if (dragState.handle.includes('e')) {
          newW = Math.max(minSize, Math.min(100 - origX, origW + deltaX));
        }
        if (dragState.handle.includes('w')) {
          const maxX = origX + origW - minSize;
          newX = Math.max(0, Math.min(maxX, origX + deltaX));
          newW = origW - (newX - origX);
        }
        if (dragState.handle.includes('s')) {
          newH = Math.max(minSize, Math.min(100 - origY, origH + deltaY));
        }
        if (dragState.handle.includes('n')) {
          const maxY = origY + origH - minSize;
          newY = Math.max(0, Math.min(maxY, origY + deltaY));
          newH = origH - (newY - origY);
        }
        updateElement(dragState.elementId, { x: newX, y: newY, width: newW, height: newH });
      } else if (dragState.mode === 'corner' && dragState.corner && dragState.origCorners) {
        // Convert canvas-percent delta to bounding-box-percent delta
        const dxBbox = (deltaX / dragState.origW) * 100;
        const dyBbox = (deltaY / dragState.origH) * 100;
        const clamp = (v: number) => Math.max(-100, Math.min(200, v));
        const c = { ...dragState.origCorners };
        const k = dragState.corner;
        c[k] = { x: clamp(c[k].x + dxBbox), y: clamp(c[k].y + dyBbox) };
        updateElement(dragState.elementId, { corners: c });
      } else if (dragState.mode === 'image-move') {
        // Reposition the image inside its frame. Offset stored as % of bbox dimensions.
        const dxBbox = (deltaX / dragState.origW) * 100;
        const dyBbox = (deltaY / dragState.origH) * 100;
        const clamp = (v: number) => Math.max(-100, Math.min(100, v));
        updateElement(dragState.elementId, {
          imageOffsetX: clamp((dragState.origOffsetX ?? 0) + dxBbox),
          imageOffsetY: clamp((dragState.origOffsetY ?? 0) + dyBbox),
        } as Partial<ImageElement>);
      }
    };
    const handleMouseUp = () => setDragState(null);
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [dragState, updateElement]);

  const handleCanvasClick = useCallback((e: React.MouseEvent) => {
    if (e.target !== canvasRef.current && !(e.target as HTMLElement).classList.contains('composer-canvas')) return;
    selectElement(null);
    setEditingId(null);

    const rect = canvasRef.current!.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * 100;
    const y = ((e.clientY - rect.top) / rect.height) * 100;

    if (activeTool === 'text') {
      const id = `text_${Date.now()}`;
      addElement({
        id,
        type: 'text',
        x: Math.max(0, x - 10),
        y: Math.max(0, y - 3),
        width: 20,
        height: 8,
        rotation: 0,
        zIndex: 100,
        locked: false,
        visible: true,
        content: '',
        fontSize: 14,
        fontFamily: 'Inter',
        color: '#000000',
        direction: 'horizontal',
        fontWeight: 'normal',
        textAlign: 'left',
      });
      setEditingId(id);
      setActiveTool('select');
    } else if (activeTool === 'bubble') {
      const id = `bubble_${Date.now()}`;
      addElement({
        id,
        type: 'bubble',
        x: Math.max(0, x - 10),
        y: Math.max(0, y - 7),
        width: 20,
        height: 14,
        rotation: 0,
        zIndex: 100,
        locked: false,
        visible: true,
        bubbleType: activeBubbleType,
        text: '',
        direction: 'horizontal',
        fontSize: 12,
        backgroundColor: '#ffffff',
        borderColor: '#000000',
        tailPosition: 'bottom',
      });
      setActiveTool('select');
    }
  }, [activeTool, activeBubbleType, selectElement, addElement, setActiveTool]);

  const handleAddImageClick = useCallback((elementId: string, kind: 'slot' | 'pageImage' = 'slot') => {
    useComposerStore.getState().openImagePicker({ kind, id: elementId });
    selectElement(elementId);
  }, [selectElement]);

  const handleDoubleClick = useCallback((e: React.MouseEvent, elementId: string) => {
    e.stopPropagation();
    const el = currentPage?.elements.find(p => p.id === elementId);
    if (el && (el.type === 'text' || el.type === 'bubble')) {
      setEditingId(elementId);
    }
  }, [currentPage]);

  const handleImageSelect = useCallback((src: string) => {
    if (!imagePickerRequest) return;
    if (imagePickerRequest.kind === 'slot') {
      convertSlotToImage(imagePickerRequest.id, src);
    } else {
      // page-image: just set src on the element directly
      updateElement(imagePickerRequest.id, { src } as Partial<PageImageElement>);
    }
    closeImagePicker();
  }, [imagePickerRequest, convertSlotToImage, updateElement, closeImagePicker]);

  if (!currentPage) {
    return (
      <div className="composer-canvas-scroll">
        <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 'var(--space-xxl)', fontSize: 13 }}>
          Add a page to start composing.
        </div>
      </div>
    );
  }

  const sortedElements = [...currentPage.elements].sort((a, b) => a.zIndex - b.zIndex);

  return (
    <>
      <div className="composer-canvas-scroll">
        <div
          ref={canvasRef}
          className="composer-canvas"
          style={{
            width: currentPage.width,
            height: currentPage.height,
            transform: `scale(${zoom})`,
          }}
          onClick={handleCanvasClick}
        >
          {sortedElements.map(el => {
            if (!el.visible) return null;
            return (
              <ElementRenderer
                key={el.id}
                el={el}
                isSelected={selectedElementId === el.id}
                isEditing={editingId === el.id}
                activeTool={activeTool}
                onMouseDown={handleElementMouseDown}
                onResizeDown={handleResizeMouseDown}
                onCornerDown={handleCornerMouseDown}
                onAddImageClick={handleAddImageClick}
                onImageMouseDown={handleImageMouseDown}
                onImageWheel={handleImageWheel}
                onDoubleClick={handleDoubleClick}
                onBubbleTextChange={(id, text) => updateElement(id, { text } as Partial<BubbleElement>)}
                onTextContentChange={(id, content) => updateElement(id, { content } as Partial<TextElement>)}
                setEditingId={setEditingId}
              />
            );
          })}
        </div>
      </div>
      {imagePickerRequest && (
        <ImagePicker onSelect={handleImageSelect} onClose={closeImagePicker} />
      )}
    </>
  );
}

interface ElementRendererProps {
  el: ComposerElement;
  isSelected: boolean;
  isEditing: boolean;
  activeTool: string;
  onMouseDown: (e: React.MouseEvent, id: string) => void;
  onResizeDown: (e: React.MouseEvent, id: string, handle: string) => void;
  onCornerDown: (e: React.MouseEvent, id: string, corner: CornerKey) => void;
  onAddImageClick: (id: string, kind: 'slot' | 'pageImage') => void;
  onImageMouseDown: (e: React.MouseEvent, id: string) => void;
  onImageWheel: (e: React.WheelEvent, id: string) => void;
  onDoubleClick: (e: React.MouseEvent, id: string) => void;
  onBubbleTextChange: (id: string, text: string) => void;
  onTextContentChange: (id: string, content: string) => void;
  setEditingId: (id: string | null) => void;
}

function ElementRenderer({
  el,
  isSelected,
  isEditing,
  activeTool,
  onMouseDown,
  onResizeDown,
  onCornerDown,
  onAddImageClick,
  onImageMouseDown,
  onImageWheel,
  onDoubleClick,
  onBubbleTextChange,
  onTextContentChange,
  setEditingId,
}: ElementRendererProps) {
  const isDraggable = activeTool === 'select' && !el.locked;

  // Frames (image-slot + image + page-image) share quadrilateral rendering:
  // clip-path on content, SVG polygon overlay for outline, 4 corner handles.
  // Differences live inside FrameElement — see below.
  if (el.type === 'image-slot' || el.type === 'image' || el.type === 'page-image') {
    return (
      <FrameElement
        el={el}
        isSelected={isSelected}
        isDraggable={isDraggable}
        onMouseDown={onMouseDown}
        onCornerDown={onCornerDown}
        onAddImageClick={onAddImageClick}
        onImageMouseDown={onImageMouseDown}
        onImageWheel={onImageWheel}
        onDoubleClick={onDoubleClick}
      />
    );
  }

  switch (el.type) {
    case 'text': {
      const textEl = el as TextElement;
      return (
        <div
          className={`composer-element composer-text ${textEl.direction === 'vertical' ? 'vertical' : ''} ${isSelected ? 'selected' : ''} ${isEditing ? 'editing' : ''}`}
          style={{
            left: `${el.x}%`,
            top: `${el.y}%`,
            width: `${el.width}%`,
            height: `${el.height}%`,
            transform: `rotate(${el.rotation}deg)`,
            zIndex: el.zIndex,
            fontSize: `${textEl.fontSize}px`,
            fontFamily: textEl.fontFamily,
            color: textEl.color,
            fontWeight: textEl.fontWeight,
            textAlign: textEl.textAlign,
            cursor: isDraggable ? 'grab' : 'default',
          }}
          onMouseDown={(e) => onMouseDown(e, el.id)}
          onDoubleClick={(e) => onDoubleClick(e, el.id)}
        >
          {isEditing ? (
            <div
              contentEditable
              suppressContentEditableWarning
              autoFocus
              onBlur={(e) => { onTextContentChange(el.id, e.currentTarget.textContent || ''); setEditingId(null); }}
              style={{ outline: 'none', width: '100%', height: '100%', display: 'flex', alignItems: 'center' }}
            >
              {textEl.content}
            </div>
          ) : (
            textEl.content || <span style={{ color: 'var(--text-muted)' }}>{textEl.content || 'Text'}</span>
          )}
          {isSelected && !el.locked && !isEditing && <ResizeHandles id={el.id} onResizeDown={onResizeDown} />}
        </div>
      );
    }

    case 'bubble': {
      const bubble = el as BubbleElement;
      return (
        <div
          className={`composer-element composer-bubble ${bubble.bubbleType} ${bubble.direction === 'vertical' ? 'vertical' : ''} ${isSelected ? 'selected' : ''} ${el.locked ? 'locked' : ''}`}
          style={{
            left: `${el.x}%`,
            top: `${el.y}%`,
            width: `${el.width}%`,
            height: `${el.height}%`,
            transform: `rotate(${el.rotation}deg)`,
            zIndex: el.zIndex,
            fontSize: `${bubble.fontSize}px`,
            cursor: isDraggable ? 'grab' : 'default',
          }}
          onMouseDown={(e) => onMouseDown(e, el.id)}
          onDoubleClick={(e) => onDoubleClick(e, el.id)}
        >
          <div className="composer-bubble-inner">
            {isEditing ? (
              <input
                className="composer-bubble-input"
                autoFocus
                value={bubble.text}
                onChange={e => onBubbleTextChange(el.id, e.target.value)}
                onBlur={() => setEditingId(null)}
                onKeyDown={e => { if (e.key === 'Enter') setEditingId(null); }}
                onClick={e => e.stopPropagation()}
              />
            ) : (
              <>
                <span>{bubble.text || '...'}</span>
                <div className={`composer-bubble-tail ${bubble.tailPosition}`} />
              </>
            )}
          </div>
          {isSelected && !el.locked && !isEditing && <ResizeHandles id={el.id} onResizeDown={onResizeDown} />}
        </div>
      );
    }

    default:
      return null;
  }
}

/**
 * Frame-style element rendering: shared by `image-slot`, `image`, and
 * `page-image`. Renders a quadrilateral defined by 4 corner points, with:
 *   - clipped content (image pixels, slot placeholder, or empty page-image)
 *   - SVG polygon overlay for the visible outline
 *   - central + button for "needs an image" states (empty slot OR empty page-image)
 *   - 4 corner handles when selected, supporting non-rectangular frames
 *   - image-move drag + Ctrl/Alt wheel scale when an image is present
 */
interface FrameElementProps {
  el: ImageSlotElement | ImageElement | PageImageElement;
  isSelected: boolean;
  isDraggable: boolean;
  onMouseDown: (e: React.MouseEvent, id: string) => void;
  onCornerDown: (e: React.MouseEvent, id: string, corner: CornerKey) => void;
  onAddImageClick: (id: string, kind: 'slot' | 'pageImage') => void;
  onImageMouseDown: (e: React.MouseEvent, id: string) => void;
  onImageWheel: (e: React.WheelEvent, id: string) => void;
  onDoubleClick: (e: React.MouseEvent, id: string) => void;
}

function FrameElement({
  el,
  isSelected,
  isDraggable,
  onMouseDown,
  onCornerDown,
  onAddImageClick,
  onImageMouseDown,
  onImageWheel,
  onDoubleClick,
}: FrameElementProps) {
  const corners = el.corners ?? DEFAULT_CORNERS;
  const polygonPts = `${corners.tl.x}% ${corners.tl.y}%, ${corners.tr.x}% ${corners.tr.y}%, ${corners.br.x}% ${corners.br.y}%, ${corners.bl.x}% ${corners.bl.y}%`;
  const svgPts = `${corners.tl.x},${corners.tl.y} ${corners.tr.x},${corners.tr.y} ${corners.br.x},${corners.br.y} ${corners.bl.x},${corners.bl.y}`;
  // Centroid of the polygon — used to anchor the central + button visually inside the shape
  const cx = (corners.tl.x + corners.tr.x + corners.br.x + corners.bl.x) / 4;
  const cy = (corners.tl.y + corners.tr.y + corners.br.y + corners.bl.y) / 4;

  const isSlot = el.type === 'image-slot';
  const isPageImage = el.type === 'page-image';
  const hasImage = isSlot ? false : !!(el as ImageElement | PageImageElement).src;
  // The + button is shown when the frame has no image yet — applies to slots
  // (always) and to page-image elements that haven't been filled in.
  const showAddButton = isSlot || (isPageImage && !hasImage);
  // Slot label only renders for image-slot elements (image/page-image have no label).
  const showSlotLabel = isSlot;

  const className = `composer-element ${isSlot ? 'composer-image-slot' : isPageImage ? 'composer-page-image' : 'composer-image'} ${isSelected ? 'selected' : ''} ${el.locked ? 'locked' : ''}`;

  // Manga-panel frames (image-slot + image) get a visible black border that
  // follows the quadrilateral shape. Page-image (floating breakout) has no border.
  const isPanel = isSlot || el.type === 'image';
  // Selected → blue selection outline; unselected panel → black; page-image → none
  const borderW = el.frameBorderWidth ?? (isPanel ? 1.5 : 0);
  const strokeColor = isSelected
    ? '#3B82F6'
    : isPanel ? '#111' : 'transparent';
  const strokeWidth = isSelected ? 2 : borderW;
  const strokeDasharray = 'none';

  return (
    <div
      className={className}
      style={{
        left: `${el.x}%`,
        top: `${el.y}%`,
        width: `${el.width}%`,
        height: `${el.height}%`,
        transform: `rotate(${el.rotation}deg)`,
        zIndex: el.zIndex,
        cursor: isDraggable ? 'grab' : 'default',
      }}
      onMouseDown={(e) => onMouseDown(e, el.id)}
      onDoubleClick={(e) => onDoubleClick(e, el.id)}
    >
      {/* Clipped content (image pixels, slot placeholder, or empty page-image) */}
      <div
        className="composer-frame-content"
        style={{ clipPath: `polygon(${polygonPts})`, WebkitClipPath: `polygon(${polygonPts})` }}
      >
        {hasImage && (
          <img
            src={(el as ImageElement | PageImageElement).src}
            alt=""
            draggable={false}
            onMouseDown={(e) => onImageMouseDown(e, el.id)}
            onWheel={(e) => onImageWheel(e, el.id)}
            style={{
              transform: `translate(${(el as ImageElement | PageImageElement).imageOffsetX ?? 0}%, ${(el as ImageElement | PageImageElement).imageOffsetY ?? 0}%) scale(${(el as ImageElement | PageImageElement).imageScale ?? 1})`,
              transformOrigin: 'center center',
              cursor: isDraggable ? 'move' : 'default',
            }}
          />
        )}
        {showSlotLabel && (
          <div className="composer-slot-fill">
            <span className="composer-slot-label">{(el as ImageSlotElement).label}</span>
          </div>
        )}
        {/* Empty page-image: subtle placeholder, but the + button is the primary affordance */}
        {isPageImage && !hasImage && (
          <div className="composer-page-image-empty" />
        )}
      </div>

      {/* SVG overlay for the polygon outline */}
      <svg
        className="composer-frame-outline"
        width="100%"
        height="100%"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
      >
        <polygon
          points={svgPts}
          fill="none"
          stroke={strokeColor}
          strokeWidth={strokeWidth}
          strokeDasharray={strokeDasharray}
          vectorEffect="non-scaling-stroke"
        />
      </svg>

      {/* Central + button — for empty frames (slots always, page-image before image is set) */}
      {showAddButton && (
        <button
          type="button"
          className="composer-slot-add-btn"
          style={{ left: `${cx}%`, top: `${cy}%` }}
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation();
            onAddImageClick(el.id, isSlot ? 'slot' : 'pageImage');
          }}
          title="Add image"
        >
          <FiPlus size={18} />
        </button>
      )}

      {/* 4 corner handles when selected */}
      {isSelected && !el.locked && (
        <CornerHandles corners={corners} onCornerDown={(e, corner) => onCornerDown(e, el.id, corner)} />
      )}
    </div>
  );
}

function CornerHandles({
  corners,
  onCornerDown,
}: {
  corners: QuadCorners;
  onCornerDown: (e: React.MouseEvent, corner: CornerKey) => void;
}) {
  const positions: [CornerKey, { x: number; y: number }][] = [
    ['tl', corners.tl],
    ['tr', corners.tr],
    ['br', corners.br],
    ['bl', corners.bl],
  ];
  return (
    <>
      {positions.map(([key, pos]) => (
        <div
          key={key}
          className={`composer-corner-handle ${key}`}
          style={{ left: `${pos.x}%`, top: `${pos.y}%` }}
          onMouseDown={(e) => onCornerDown(e, key)}
        />
      ))}
    </>
  );
}

function ResizeHandles({
  id,
  onResizeDown,
}: {
  id: string;
  onResizeDown: (e: React.MouseEvent, id: string, handle: string) => void;
}) {
  const handles = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];
  return (
    <>
      {handles.map(h => (
        <div
          key={h}
          className={`composer-resize-handle ${h}`}
          onMouseDown={(e) => onResizeDown(e, id, h)}
        />
      ))}
    </>
  );
}
