import { useState, useRef, useCallback, useEffect, useMemo, memo } from 'react';
import { useShallow } from 'zustand/react/shallow';
import { FiPlus } from 'react-icons/fi';
import { useComposerStore } from '../../store/composerStore';
import { useTips } from '../../hooks/useTips';
import { ImagePicker } from './ImagePicker';
import { DEFAULT_CORNERS } from '../../types';
import { tailGeometry, wedgePath } from './tailGeometry';
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

type DragState = {
  elementId: string;
  startX: number;
  startY: number;
  origX: number;
  origY: number;
  origW: number;
  origH: number;
  origCorners?: QuadCorners;
  mode: 'move' | 'resize' | 'corner' | 'image-move' | 'tail';
  handle?: string;
  corner?: CornerKey;
  origOffsetX?: number;
  origOffsetY?: number;
  origTip?: { x: number; y: number };
  rotation?: number;
};

type CutState = { fromX: number; fromY: number; toX: number; toY: number };

/** Find an element on the current page without subscribing to it. */
function findCurrentElement(elementId: string) {
  const { pages, currentPageId } = useComposerStore.getState();
  return pages.find(p => p.id === currentPageId)?.elements.find(e => e.id === elementId);
}

// memoized (no props): ComposerTab re-renders on every page edit, this
// component only when its own store selections change
export const Canvas = memo(function Canvas() {
  // narrow subscriptions: `currentPage` keeps its reference while other pages
  // change, and actions are stable, so a drag only re-renders this page
  const currentPage = useComposerStore(s => s.pages.find(p => p.id === s.currentPageId));
  const {
    currentPageId,
    selectedElementId,
    editingId,
    activeTool,
    activeBubbleType,
    zoom,
    imagePickerRequest,
  } = useComposerStore(useShallow(s => ({
    currentPageId: s.currentPageId,
    selectedElementId: s.selectedElementId,
    editingId: s.editingElementId,
    activeTool: s.activeTool,
    activeBubbleType: s.activeBubbleType,
    zoom: s.zoom,
    imagePickerRequest: s.imagePickerRequest,
  })));
  const {
    updateElement,
    selectElement,
    addElement,
    convertSlotToImage,
    setActiveTool,
    commit,
    closeImagePicker,
    splitFrame,
    createSplitPair,
    setEditingId,
  } = useComposerStore(useShallow(s => ({
    updateElement: s.updateElement,
    selectElement: s.selectElement,
    addElement: s.addElement,
    convertSlotToImage: s.convertSlotToImage,
    setActiveTool: s.setActiveTool,
    commit: s.commit,
    closeImagePicker: s.closeImagePicker,
    splitFrame: s.splitFrame,
    createSplitPair: s.createSplitPair,
    setEditingId: s.setEditingElement,
  })));

  const [dragState, setDragState] = useState<DragState | null>(null);

  // drag-a-cut-line state (split tool): the line you draw becomes the gutter
  // between two frames — inside crossed frames it splits them, on an empty
  // page it spawns a frame pair (interaction ported from the
  // novelai_local_web study, adapted to our rect+corners element model).
  // The ref drives the side effect; the state only draws the preview line.
  const [cutState, setCutState] = useState<CutState | null>(null);
  const cutRef = useRef<CutState | null>(null);

  const canvasRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // a page wider than the column at the current zoom (1650 px comic pages) opens zoomed to fit its width
  const pageWidth = currentPage?.width;
  useEffect(() => {
    const box = scrollRef.current;
    if (!box || !pageWidth) return;
    const room = box.clientWidth - 48;   // the scroll area's padding
    const { zoom: z, setZoom } = useComposerStore.getState();
    if (pageWidth * z > room) setZoom(Math.floor((room / pageWidth) * 100) / 100);
  }, [currentPageId, pageWidth]);

  const pageCoords = useCallback((e: React.MouseEvent) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    return {
      x: ((e.clientX - rect.left) / rect.width) * 100,
      y: ((e.clientY - rect.top) / rect.height) * 100,
    };
  }, []);

  const handleCutStart = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return;
    const p = pageCoords(e);
    cutRef.current = { fromX: p.x, fromY: p.y, toX: p.x, toY: p.y };
    setCutState(cutRef.current);
    e.preventDefault();
  }, [pageCoords]);

  const handleCutMove = useCallback((e: React.MouseEvent) => {
    const prev = cutRef.current;
    if (!prev) return;
    const p = pageCoords(e);
    cutRef.current = { ...prev, toX: p.x, toY: p.y };
    setCutState(cutRef.current);
  }, [pageCoords]);

  const handleCutEnd = useCallback(() => {
    const prev = cutRef.current;
    // mouseleave without a drag in progress must not end the tool
    if (!prev) return;
    cutRef.current = null;
    setCutState(null);
    const { pages, currentPageId: pageId } = useComposerStore.getState();
    const page = pages.find(p => p.id === pageId);
    if (page) {
      const dx = prev.toX - prev.fromX, dy = prev.toY - prev.fromY;
      // dominant axis of the drawn line decides the cut orientation
      const axis: 'x' | 'y' = Math.abs(dx) >= Math.abs(dy) ? 'y' : 'x';
      const span = axis === 'x'
        ? { lo: Math.min(prev.fromY, prev.toY), hi: Math.max(prev.fromY, prev.toY) }
        : { lo: Math.min(prev.fromX, prev.toX), hi: Math.max(prev.fromX, prev.toX) };
      const spanLen = span.hi - span.lo;
      // the cut sits on the dominant axis; the span selects crossed frames
      const cut = axis === 'x' ? (prev.fromX + prev.toX) / 2 : (prev.fromY + prev.toY) / 2;
      if (spanLen >= 3) {
        const crossed = page.elements.filter(el => {
          if (el.type !== 'image-slot' || el.corners || !el.visible) return false;
          const otherLo = axis === 'x' ? el.y : el.x;
          const otherHi = axis === 'x' ? el.y + el.height : el.x + el.width;
          return otherLo < span.hi && otherHi > span.lo;
        });
        if (crossed.length > 0) {
          crossed.forEach(el => splitFrame(el.id, axis, cut));
        } else {
          createSplitPair(axis, cut);
        }
      }
    }
    setActiveTool('select');
  }, [splitFrame, createSplitPair, setActiveTool]);

  const handleElementMouseDown = useCallback((e: React.MouseEvent, elementId: string) => {
    if (activeTool === 'crop' || activeTool === 'text' || activeTool === 'bubble' || activeTool === 'split') return;
    e.stopPropagation();
    // clicks inside the inline editor place the caret, they don't drag
    if (useComposerStore.getState().editingElementId === elementId) return;
    const el = findCurrentElement(elementId);
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
  }, [activeTool, selectElement]);

  const handleResizeMouseDown = useCallback((e: React.MouseEvent, elementId: string, handle: string) => {
    e.stopPropagation();
    e.preventDefault();
    const el = findCurrentElement(elementId);
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
  }, [selectElement]);

  const handleCornerMouseDown = useCallback((e: React.MouseEvent, elementId: string, corner: CornerKey) => {
    e.stopPropagation();
    e.preventDefault();
    const el = findCurrentElement(elementId);
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
      origCorners: el.corners ? { ...el.corners } : { ...DEFAULT_CORNERS },
      mode: 'corner',
      corner,
    });
  }, [selectElement]);

  // dragging a bubble's tail-tip handle moves tailTip (fractions of the box)
  const handleTailMouseDown = useCallback((e: React.MouseEvent, elementId: string) => {
    e.stopPropagation();
    e.preventDefault();
    const el = findCurrentElement(elementId);
    if (!el || el.locked || el.type !== 'bubble' || !el.tailTip) return;
    selectElement(elementId);
    setDragState({
      elementId,
      startX: e.clientX,
      startY: e.clientY,
      origX: el.x,
      origY: el.y,
      origW: el.width,
      origH: el.height,
      mode: 'tail',
      origTip: { ...el.tailTip },
      rotation: el.rotation || 0,
    });
  }, [selectElement]);

  // Click-drag on the visible image inside a frame repositions the image within
  // the frame (clip-path hides overflow). The frame bbox/corners stay put.
  // Applies to both `image` (slot-filled) and `page-image` (breakout) types.
  const handleImageMouseDown = useCallback((e: React.MouseEvent, elementId: string) => {
    if (activeTool !== 'select') return;
    e.stopPropagation();
    const el = findCurrentElement(elementId);
    if (!el || el.locked) return;
    if (el.type !== 'image' && el.type !== 'page-image') return;
    const offsetX = (el as ImageElement | PageImageElement).imageOffsetX ?? 0;
    const offsetY = (el as ImageElement | PageImageElement).imageOffsetY ?? 0;
    selectElement(elementId);
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
  }, [activeTool, selectElement]);

  // Ctrl/Cmd + wheel on an image scales it within the frame. React's onWheel
  // is passive (preventDefault is ignored and the browser zooms too), so this
  // is a native non-passive listener on the canvas element.
  const hasPage = !!currentPage;
  useEffect(() => {
    const canvasEl = canvasRef.current;
    if (!canvasEl) return;
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey && !e.metaKey) return;
      // never let Ctrl+scroll over the page zoom the whole browser
      e.preventDefault();
      if (useComposerStore.getState().activeTool !== 'select') return;
      const target = (e.target as HTMLElement | null)?.closest<HTMLElement>('[data-image-el-id]');
      const elementId = target?.dataset.imageElId;
      if (!elementId) return;
      const el = findCurrentElement(elementId);
      if (!el || el.locked) return;
      if (el.type !== 'image' && el.type !== 'page-image') return;
      e.stopPropagation();
      const img = el as ImageElement | PageImageElement;
      const next = Math.max(0.1, Math.min(4, (img.imageScale ?? 1) * (e.deltaY < 0 ? 1.05 : 1 / 1.05)));
      commit(`wheel:${elementId}`);
      updateElement(elementId, { imageScale: next } as Partial<ImageElement>);
    };
    canvasEl.addEventListener('wheel', onWheel, { passive: false });
    return () => canvasEl.removeEventListener('wheel', onWheel);
  }, [hasPage, currentPageId, commit, updateElement]);

  useEffect(() => {
    if (!dragState) return;
    // one undo step per gesture, recorded on the first real movement so a
    // plain click (select) doesn't leave an empty step behind
    let committed = false;
    const handleMouseMove = (e: MouseEvent) => {
      const canvasEl = canvasRef.current;
      if (!canvasEl) return;
      if (!committed) {
        if (e.clientX === dragState.startX && e.clientY === dragState.startY) return;
        commit();
        committed = true;
      }
      const rect = canvasEl.getBoundingClientRect();
      const deltaX = ((e.clientX - dragState.startX) / rect.width) * 100;
      const deltaY = ((e.clientY - dragState.startY) / rect.height) * 100;

      if (dragState.mode === 'move') {
        const newX = Math.max(0, Math.min(100 - dragState.origW, dragState.origX + deltaX));
        const newY = Math.max(0, Math.min(100 - dragState.origH, dragState.origY + deltaY));
        updateElement(dragState.elementId, { x: newX, y: newY });
      } else if (dragState.mode === 'resize' && dragState.handle) {
        const minSize = 3;
        const { origX, origY, origW, origH } = dragState;
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
      } else if (dragState.mode === 'tail' && dragState.origTip) {
        // the tip lives in the unrotated box: undo the element's rotation on
        // the drag (in page px, so the page's aspect doesn't skew it)
        const pw = canvasEl.offsetWidth, ph = canvasEl.offsetHeight;
        const dxPx = (deltaX / 100) * pw, dyPx = (deltaY / 100) * ph;
        const a = (-(dragState.rotation ?? 0) * Math.PI) / 180;
        const lx = dxPx * Math.cos(a) - dyPx * Math.sin(a);
        const ly = dxPx * Math.sin(a) + dyPx * Math.cos(a);
        const clamp = (v: number) => Math.max(-8, Math.min(9, v));
        updateElement(dragState.elementId, {
          tailTip: {
            x: clamp(dragState.origTip.x + lx / ((dragState.origW / 100) * pw)),
            y: clamp(dragState.origTip.y + ly / ((dragState.origH / 100) * ph)),
          },
        } as Partial<BubbleElement>);
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
  }, [dragState, updateElement, commit]);

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
  }, [activeTool, activeBubbleType, selectElement, addElement, setActiveTool, setEditingId]);

  const handleAddImageClick = useCallback((elementId: string, kind: 'slot' | 'pageImage' = 'slot') => {
    useComposerStore.getState().openImagePicker({ kind, id: elementId });
    selectElement(elementId);
  }, [selectElement]);

  const handleDoubleClick = useCallback((e: React.MouseEvent, elementId: string) => {
    e.stopPropagation();
    const el = findCurrentElement(elementId);
    if (el && (el.type === 'text' || el.type === 'bubble') && !el.locked) {
      setEditingId(elementId);
    }
  }, [setEditingId]);

  // text edits are undo steps; typing bursts in a bubble coalesce into one
  const handleBubbleTextChange = useCallback((id: string, text: string) => {
    commit(`text:${id}`);
    updateElement(id, { text } as Partial<BubbleElement>);
  }, [commit, updateElement]);

  const handleTextContentChange = useCallback((id: string, content: string) => {
    const el = findCurrentElement(id);
    if (el?.type === 'text' && el.content === content) return;
    commit();
    updateElement(id, { content } as Partial<TextElement>);
  }, [commit, updateElement]);

  const handleImageSelect = useCallback((src: string) => {
    if (!imagePickerRequest) return;
    if (imagePickerRequest.kind === 'slot') {
      convertSlotToImage(imagePickerRequest.id, src);
    } else {
      // page-image: just set src on the element directly
      commit();
      updateElement(imagePickerRequest.id, { src } as Partial<PageImageElement>);
    }
    closeImagePicker();
  }, [imagePickerRequest, convertSlotToImage, updateElement, closeImagePicker, commit]);

  const elements = currentPage?.elements;
  const sortedElements = useMemo(
    () => (elements ? [...elements].sort((a, b) => a.zIndex - b.zIndex) : []),
    [elements],
  );

  if (!currentPage) {
    return (
      <div className="composer-canvas-scroll">
        <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 'var(--space-xxl)', fontSize: 13 }}>
          Add a page to start composing.
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="composer-canvas-scroll" ref={scrollRef}>
        {/* a transform doesn't change layout size: this box is the zoomed page's real footprint, so the
            scroll area and centring follow the zoom */}
        <div className="composer-canvas-sizer" style={{ width: currentPage.width * zoom, height: currentPage.height * zoom }}>
        <div
          ref={canvasRef}
          className={`composer-canvas ${activeTool === 'text' || activeTool === 'bubble' ? 'composer-canvas-place-mode' : ''}`}
          style={{
            width: currentPage.width,
            height: currentPage.height,
            transform: `scale(${zoom})`,
            cursor: activeTool === 'text' || activeTool === 'bubble' || activeTool === 'split'
              ? 'crosshair' : 'default',
          }}
          onClick={handleCanvasClick}
          {...(activeTool === 'split' ? {
            onMouseDown: handleCutStart,
            onMouseMove: handleCutMove,
            onMouseUp: handleCutEnd,
            onMouseLeave: handleCutEnd,
          } : {})}
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
                onTailDown={handleTailMouseDown}
                pageWidth={currentPage.width}
                pageHeight={currentPage.height}
                onAddImageClick={handleAddImageClick}
                onImageMouseDown={handleImageMouseDown}
                onDoubleClick={handleDoubleClick}
                onBubbleTextChange={handleBubbleTextChange}
                onTextContentChange={handleTextContentChange}
                setEditingId={setEditingId}
              />
            );
          })}
          {cutState && (
            <div
              style={{
                position: 'absolute',
                left: `${Math.min(cutState.fromX, cutState.toX)}%`,
                top: `${Math.min(cutState.fromY, cutState.toY)}%`,
                width: `${Math.abs(cutState.toX - cutState.fromX)}%`,
                height: `${Math.abs(cutState.toY - cutState.fromY)}%`,
                borderTop: cutState.toY === cutState.fromY ? '2px dashed var(--accent-primary)' : undefined,
                borderLeft: cutState.toX === cutState.fromX ? '2px dashed var(--accent-primary)' : undefined,
                pointerEvents: 'none',
                zIndex: 9999,
              }}
            >
              {/* diagonal preview for angled drags */}
              {cutState.toY !== cutState.fromY && cutState.toX !== cutState.fromX && (
                <svg width="100%" height="100%" style={{ overflow: 'visible', position: 'absolute', inset: 0 }}>
                  <line
                    x1={cutState.fromX < cutState.toX ? '0%' : '100%'}
                    y1={cutState.fromY < cutState.toY ? '0%' : '100%'}
                    x2={cutState.fromX < cutState.toX ? '100%' : '0%'}
                    y2={cutState.fromY < cutState.toY ? '100%' : '0%'}
                    stroke="var(--accent-primary)" strokeWidth="2" strokeDasharray="6 5"
                  />
                </svg>
              )}
            </div>
          )}
        </div>
        </div>
      </div>
      {imagePickerRequest && (
        <ImagePicker onSelect={handleImageSelect} onClose={closeImagePicker} />
      )}
    </>
  );
});

interface ElementRendererProps {
  el: ComposerElement;
  isSelected: boolean;
  isEditing: boolean;
  activeTool: string;
  onMouseDown: (e: React.MouseEvent, id: string) => void;
  onResizeDown: (e: React.MouseEvent, id: string, handle: string) => void;
  onCornerDown: (e: React.MouseEvent, id: string, corner: CornerKey) => void;
  onTailDown: (e: React.MouseEvent, id: string) => void;
  pageWidth: number;
  pageHeight: number;
  onAddImageClick: (id: string, kind: 'slot' | 'pageImage') => void;
  onImageMouseDown: (e: React.MouseEvent, id: string) => void;
  onDoubleClick: (e: React.MouseEvent, id: string) => void;
  onBubbleTextChange: (id: string, text: string) => void;
  onTextContentChange: (id: string, content: string) => void;
  setEditingId: (id: string | null) => void;
}

/**
 * Inline editor for a text element. `autoFocus` does nothing on a
 * contentEditable div, so focus it (caret at the end) once it mounts —
 * otherwise Backspace on a fresh text box reaches the global delete handler.
 */
function TextContentEditor({
  content,
  onCommit,
}: {
  content: string;
  onCommit: (content: string) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    node.focus();
    const sel = window.getSelection();
    if (sel) {
      const range = document.createRange();
      range.selectNodeContents(node);
      range.collapse(false);
      sel.removeAllRanges();
      sel.addRange(range);
    }
  }, []);
  return (
    <div
      ref={ref}
      contentEditable
      suppressContentEditableWarning
      onBlur={(e) => onCommit(e.currentTarget.textContent || '')}
      style={{ outline: 'none', width: '100%', height: '100%', display: 'flex', alignItems: 'center' }}
    >
      {content}
    </div>
  );
}

const ElementRenderer = memo(function ElementRenderer({
  el,
  isSelected,
  isEditing,
  activeTool,
  onMouseDown,
  onResizeDown,
  onCornerDown,
  onTailDown,
  pageWidth,
  pageHeight,
  onAddImageClick,
  onImageMouseDown,
  onDoubleClick,
  onBubbleTextChange,
  onTextContentChange,
  setEditingId,
}: ElementRendererProps) {
  const tips = useTips().composer;
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
            <TextContentEditor
              content={textEl.content}
              onCommit={(content) => { onTextContentChange(el.id, content); setEditingId(null); }}
            />
          ) : (
            textEl.content || <span style={{ color: 'var(--text-muted)' }}>{textEl.content || 'Text'}</span>
          )}
          {isSelected && !el.locked && !isEditing && <ResizeHandles id={el.id} onResizeDown={onResizeDown} />}
        </div>
      );
    }

    case 'bubble': {
      const bubble = el as BubbleElement;
      const tip = bubble.tailTip;
      // pointed tail: element-box px (the page is unzoomed inside the scaled canvas)
      const bw = (el.width / 100) * pageWidth, bh = (el.height / 100) * pageHeight;
      // .composer-bubble's 6px padding is where the CSS body starts
      const tail = tip ? tailGeometry(bubble.bubbleType, bw, bh, [tip.x * bw, tip.y * bh], 6) : null;
      const sw = bubble.bubbleType === 'shout' ? 3 : bubble.bubbleType === 'whisper' ? 1 : 2;
      const fill = bubble.backgroundColor || (bubble.bubbleType === 'shout' ? '#FFF9C4' : '#ffffff');
      const stroke = bubble.borderColor || '#000000';
      const tailSvg = (layer: 'under' | 'over') => tail && (
        <svg className={`composer-bubble-tailtip ${layer}`} width={bw} height={bh}>
          {tail.kind === 'circles'
            ? layer === 'over' && tail.circles.map(([cx, cy, r], i) => (
              <circle key={i} cx={cx} cy={cy} r={r} fill={fill} stroke={stroke} strokeWidth={sw} />))
            : layer === 'under'
              // under the body: the edges at double width — the fill on top leaves the outer half
              ? <path d={wedgePath(tail, true)} fill={fill} stroke={stroke} strokeWidth={sw * 2} strokeLinejoin="round" />
              // over the body: fill only, covering the body's outline at the root (seamless)
              : <path d={wedgePath(tail, true)} fill={fill} />}
        </svg>
      );
      const align = bubble.textAlign && bubble.textAlign !== 'center' ? bubble.textAlign : undefined;
      let label: React.ReactNode = bubble.text || '...';
      if (bubble.markup === 'stars' && bubble.text) {
        const parts = bubble.text.split(/(\*[^*\n]+\*)/g);
        // split() with a capture group puts the *x* matches at odd indexes
        label = parts.map((p, i) => (i % 2 ? <em key={i}>{p.slice(1, -1)}</em> : p));
      }
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
          {tailSvg('under')}
          <div
            className="composer-bubble-inner"
            style={align ? {
              textAlign: align,
              justifyContent: align === 'left' ? 'flex-start' : 'flex-end',
            } : undefined}
          >
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
                <span style={bubble.markup || align ? { whiteSpace: 'pre-line' } : undefined}>{label}</span>
                {!tip && <div className={`composer-bubble-tail ${bubble.tailPosition}`} />}
              </>
            )}
          </div>
          {tailSvg('over')}
          {isSelected && !el.locked && !isEditing && <ResizeHandles id={el.id} onResizeDown={onResizeDown} />}
          {isSelected && !el.locked && !isEditing && tip && (
            <div
              className="composer-tail-handle"
              style={{ left: tip.x * bw, top: tip.y * bh }}
              data-tip={tips.tailHandle}
              onMouseDown={(e) => onTailDown(e, el.id)}
            />
          )}
        </div>
      );
    }

    default:
      return null;
  }
});

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
  onDoubleClick,
}: FrameElementProps) {
  const tip = useTips().composer;
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
            data-image-el-id={el.id}
            onMouseDown={(e) => onImageMouseDown(e, el.id)}
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
          data-tip={tip.addSlotImage}
          aria-label={tip.addSlotImage}
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
