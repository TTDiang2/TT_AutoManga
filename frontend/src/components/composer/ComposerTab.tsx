import { useState, useEffect, useRef, useCallback, memo } from 'react';
import { useShallow } from 'zustand/react/shallow';
import {
  FiMousePointer, FiType, FiMessageCircle,
  FiRotateCcw, FiRotateCw, FiDownload,
  FiCopy, FiTrash2, FiSave, FiBook, FiX, FiPlusSquare, FiTrash,
  FiImage, FiZap, FiLayout, FiScissors,
} from 'react-icons/fi';
import { useComposerStore, TEMPLATES, hasUnsavedPages } from '../../store/composerStore';
import { useProjectStore } from '../../store/projectStore';
import { useTranslation } from '../../hooks/useTranslation';
import { Canvas } from './Canvas';
import { PropertiesPanel } from './PropertiesPanel';
import { renderPageToImage } from './pageRenderer';
import { isTextEntry } from './textEntry';
import { AUTH_RESTORED_EVENT } from '../../auth';
import './composer.css';
import type { BubbleType, ComposerPage } from '../../types';

/** Module-scope download helpers: impure (Date.now) but never render-phase. */
function timestampedName(base: string, ext: string) {
  return `${base}_${Date.now()}.${ext}`;
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/**
 * Tiny SVG preview of each bubble type, used in the toolbar picker so users
 * can compare the six styles at a glance instead of reading English names.
 * Colors match the actual canvas rendering in composer.css.
 */
function BubbleIcon({ type }: { type: BubbleType }) {
  const stroke = '#333';
  const fill = '#fff';

  if (type === 'speech') {
    return (
      <svg width="28" height="22" viewBox="0 0 28 22" aria-hidden>
        <ellipse cx="14" cy="10" rx="10" ry="7" fill={fill} stroke={stroke} strokeWidth="1.5" />
        <path d="M9 15 L7 20 L12 16 Z" fill={fill} stroke={stroke} strokeWidth="1.5" />
      </svg>
    );
  }
  if (type === 'thought') {
    return (
      <svg width="28" height="22" viewBox="0 0 28 22" aria-hidden>
        <ellipse cx="13" cy="9" rx="9" ry="6" fill={fill} stroke={stroke} strokeWidth="1.5" strokeDasharray="3 2" />
        <circle cx="8" cy="18" r="2" fill={fill} stroke={stroke} strokeWidth="1" />
        <circle cx="11.5" cy="20.5" r="1" fill={fill} stroke={stroke} strokeWidth="1" />
      </svg>
    );
  }
  if (type === 'shout') {
    return (
      <svg width="28" height="22" viewBox="0 0 28 22" aria-hidden>
        <path
          d="M14 1 L17 5 L22 3 L20 8 L26 9 L22 13 L26 17 L20 16 L22 21 L17 19 L14 23 L11 19 L6 21 L8 16 L2 17 L6 13 L2 9 L8 8 L6 3 L11 5 Z"
          fill="#FFF9C4"
          stroke={stroke}
          strokeWidth="1.5"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  if (type === 'whisper') {
    return (
      <svg width="28" height="22" viewBox="0 0 28 22" aria-hidden>
        <ellipse cx="14" cy="11" rx="10" ry="7" fill={fill} stroke="#888" strokeWidth="1" strokeDasharray="3 2" />
        <text x="14" y="14" textAnchor="middle" fontSize="8" fill="#666" fontStyle="italic">~</text>
      </svg>
    );
  }
  if (type === 'narration') {
    return (
      <svg width="28" height="22" viewBox="0 0 28 22" aria-hidden>
        <rect x="2" y="4" width="24" height="14" rx="1" fill="#F5F5F5" stroke="#333" strokeWidth="1.5" />
        <line x1="6" y1="9" x2="22" y2="9" stroke="#888" strokeWidth="1" />
        <line x1="6" y1="13" x2="18" y2="13" stroke="#888" strokeWidth="1" />
      </svg>
    );
  }
  // inner-voice
  return (
    <svg width="28" height="22" viewBox="0 0 28 22" aria-hidden>
      <ellipse cx="14" cy="10" rx="10" ry="7" fill="#E8EAF6" stroke="#5C6BC0" strokeWidth="1.5" />
      <text x="14" y="13" textAnchor="middle" fontSize="8" fill="#5C6BC0" fontStyle="italic">i</text>
    </svg>
  );
}

/**
 * One page in the sidebar list. Memoized: a page's object only changes when
 * that page is edited, so dragging on the canvas re-renders one thumbnail.
 */
const PageThumb = memo(function PageThumb({
  page,
  active,
  canDelete,
  duplicateTitle,
  deleteTitle,
  onSelect,
  onDuplicate,
  onDelete,
}: {
  page: ComposerPage;
  active: boolean;
  canDelete: boolean;
  duplicateTitle: string;
  deleteTitle: string;
  onSelect: (id: string) => void;
  onDuplicate: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  return (
    <div
      className={`composer-page-thumb ${active ? 'active' : ''}`}
      onClick={() => onSelect(page.id)}
    >
      <div className="composer-page-thumb-inner">
        {page.elements
          .filter(e => e.visible)
          .sort((a, b) => a.zIndex - b.zIndex)
          .map(el => (
            <div
              key={el.id}
              className="composer-page-thumb-slot"
              style={{
                left: `${el.x}%`,
                top: `${el.y}%`,
                width: `${el.width}%`,
                height: `${el.height}%`,
                background: el.type === 'image' ? '#ddd' : undefined,
              }}
            />
          ))}
      </div>
      <div className="composer-page-thumb-label">{page.name}</div>
      <div className="composer-page-thumb-actions">
        <button
          title={duplicateTitle}
          onClick={(e) => { e.stopPropagation(); onDuplicate(page.id); }}
        >
          <FiCopy size={9} />
        </button>
        <button
          title={deleteTitle}
          onClick={(e) => { e.stopPropagation(); if (canDelete) onDelete(page.id); }}
          disabled={!canDelete}
        >
          <FiTrash2 size={9} />
        </button>
      </div>
    </div>
  );
});

/** Autosave retries after a failure: 5 s, 15 s, then every 60 s (and at once after a sign-in). */
const RETRY_DELAYS = [5000, 15000, 60000];

const CONFLICT_MSG = "This project's pages were changed elsewhere (e.g. by a Comics import). "
  + 'Reload to see them — your unsaved changes here will be lost.';

export function ComposerTab() {
  const { t } = useTranslation();
  const language = useProjectStore(s => s.settings.language);
  const composerProjectId = useProjectStore(s => s.composerProjectId);
  const setComposerProjectId = useProjectStore(s => s.setComposerProjectId);
  const {
    pages,
    currentPageId,
    activeTool,
    activeBubbleType,
    zoom,
    userTemplates,
    currentProjectId,
    currentProjectName,
    saveConflict,
    savedPages,
  } = useComposerStore(useShallow(s => ({
    pages: s.pages,
    currentPageId: s.currentPageId,
    activeTool: s.activeTool,
    activeBubbleType: s.activeBubbleType,
    zoom: s.zoom,
    userTemplates: s.userTemplates,
    currentProjectId: s.projectId,
    currentProjectName: s.projectName,
    saveConflict: s.saveConflict,
    savedPages: s._savedPages,
  })));
  const {
    addPage,
    removePage,
    setCurrentPage,
    duplicatePage,
    applyTemplateToPage,
    setActiveTool,
    setActiveBubbleType,
    setZoom,
    undo,
    redo,
    addFrame,
    addElement,
    loadUserTemplates,
    saveAsUserTemplate,
    applyUserTemplate,
    deleteUserTemplate,
    openImagePicker,
    loadProject,
    savePages,
    setProjectMeta,
  } = useComposerStore(useShallow(s => ({
    addPage: s.addPage,
    removePage: s.removePage,
    setCurrentPage: s.setCurrentPage,
    duplicatePage: s.duplicatePage,
    applyTemplateToPage: s.applyTemplateToPage,
    setActiveTool: s.setActiveTool,
    setActiveBubbleType: s.setActiveBubbleType,
    setZoom: s.setZoom,
    undo: s.undo,
    redo: s.redo,
    addFrame: s.addFrame,
    addElement: s.addElement,
    loadUserTemplates: s.loadUserTemplates,
    saveAsUserTemplate: s.saveAsUserTemplate,
    applyUserTemplate: s.applyUserTemplate,
    deleteUserTemplate: s.deleteUserTemplate,
    openImagePicker: s.openImagePicker,
    loadProject: s.loadProject,
    savePages: s.savePages,
    setProjectMeta: s.setProjectMeta,
  })));

  useEffect(() => {
    const { pages: current, addPage: add } = useComposerStore.getState();
    if (current.length === 0 && !useProjectStore.getState().composerProjectId) {
      add('manga-4');
      // the starter page isn't an edit: nothing to undo, nothing unsaved (hasUnsavedPages)
      useComposerStore.setState({ _past: [], _future: [], _lastCommitKey: null });
    }
  }, []);

  // Load user-saved templates on mount
  useEffect(() => {
    loadUserTemplates();
  }, [loadUserTemplates]);

  // Delete / Backspace removes the selected element. Ignored while an element
  // is being edited inline, while focus is in any form control, and for
  // locked elements.
  useEffect(() => {
    const isFormControl = (node: Element | null) =>
      !!node && (node.tagName === 'INPUT' || node.tagName === 'SELECT' || isTextEntry(node));
    const handler = (e: KeyboardEvent) => {
      // Cmd/Ctrl+Z undoes, Cmd/Ctrl+Shift+Z (or Ctrl+Y) redoes; text fields keep their own undo
      if ((e.metaKey || e.ctrlKey) && (e.key.toLowerCase() === 'z' || e.key.toLowerCase() === 'y')) {
        if (isTextEntry(e.target as Element | null) || isTextEntry(document.activeElement)) return;
        e.preventDefault();
        const { undo, redo } = useComposerStore.getState();
        if (e.key.toLowerCase() === 'y' || e.shiftKey) redo(); else undo();
        return;
      }
      if (e.key !== 'Delete' && e.key !== 'Backspace') return;
      const state = useComposerStore.getState();
      const id = state.selectedElementId;
      if (!id || state.editingElementId) return;
      if (isFormControl(e.target as Element | null) || isFormControl(document.activeElement)) return;
      const el = state.pages.find(p => p.id === state.currentPageId)?.elements.find(x => x.id === id);
      if (!el || el.locked) return;
      e.preventDefault();
      state.removeElement(id);
      state.selectElement(null);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  const [showSaveModal, setShowSaveModal] = useState(false);
  const [saveProjectName, setSaveProjectName] = useState('');
  const [saveMsg, setSaveMsg] = useState('');
  const [loadError, setLoadError] = useState('');
  const [sfxPresets, setSfxPresets] = useState<Array<{ word: string; lang?: string; meaning: string; meaningZh?: string }>>([]);
  const [showSfxMenu, setShowSfxMenu] = useState(false);
  const [paginating, setPaginating] = useState(false);
  // consecutive failed saves of the current pages (0 = fine); drives the retry backoff
  const [saveFailures, setSaveFailures] = useState(0);
  const sfxRef = useRef<HTMLDivElement | null>(null);
  const msgTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // transient status message (clears itself); `sticky` keeps it until replaced
  const flash = useCallback((msg: string, sticky = false) => {
    if (msgTimerRef.current) clearTimeout(msgTimerRef.current);
    setSaveMsg(msg);
    msgTimerRef.current = sticky ? null : setTimeout(() => setSaveMsg(''), 2500);
  }, []);
  useEffect(() => () => { if (msgTimerRef.current) clearTimeout(msgTimerRef.current); }, []);

  const toggleSfxMenu = () => {
    const next = !showSfxMenu;
    setShowSfxMenu(next);
    if (next && sfxPresets.length === 0) {
      fetch('/api/agent/sfx-presets')
        .then(r => r.json())
        .then(d => setSfxPresets(d.presets || []))
        .catch(() => {
          setSfxPresets([]);
          flash(t.composer.sfxUnavailable || 'SFX presets unavailable');
        });
    }
  };

  // close the preset popover when clicking anywhere outside it
  useEffect(() => {
    if (!showSfxMenu) return;
    const onDown = (e: MouseEvent) => {
      if (sfxRef.current && !sfxRef.current.contains(e.target as Node)) {
        setShowSfxMenu(false);
      }
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [showSfxMenu]);

  const addSfx = (word: string) => {
    setShowSfxMenu(false);
    addElement({
      id: `el_${Date.now()}`, type: 'text', content: word,
      x: 30, y: 40, width: 40, height: 12, rotation: -8,
      zIndex: 999, locked: false, visible: true,
      fontSize: 48, fontFamily: '', color: '#ffffff',
      direction: 'horizontal', fontWeight: 'bold', textAlign: 'center',
      strokeWidth: 4, strokeColor: '#000000',
    });
  };

  // heuristic auto-pagination from the agent API: chunk imaged panels into
  // pages and append them, then reload the project's pages
  const autoPaginate = async () => {
    if (!currentProjectId || paginating || saveConflict) return;
    setPaginating(true);
    const projectId = currentProjectId;
    try {
      // persist local edits first: the reload below replaces the local pages
      const pre = await savePages();
      if (pre === 'conflict' || pre === 'error') {
        if (pre === 'error') flash(t.composer.saveFailed || 'Save failed');
        return;
      }
      const resp = await fetch(`/api/agent/projects/${projectId}/plan-pages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ apply: true, panels_per_page: 4 }),
      });
      if (!resp.ok) {
        console.error('plan-pages failed:', resp.status);
        flash(`${t.composer.autoPagesFailed || 'Auto pages failed'} (HTTP ${resp.status})`);
        return;
      }
      const data = await resp.json();
      if (!data.pages_added) {
        flash(t.composer.autoPagesEmpty || 'Generate panel art first');
        return;
      }
      await loadProject(projectId);
      flash((t.composer.autoPagesAdded || 'Added {n} page(s)')
        .replace('{n}', String(data.pages_added)));
    } catch (e) {
      console.error('auto-paginate failed:', e);
      flash(t.composer.autoPagesFailed || 'Auto pages failed');
    } finally {
      setPaginating(false);
    }
  };

  // "Save as": the only path that creates a project (POST /api/projects/save)
  const saveToShowcase = async () => {
    const name = saveProjectName.trim();
    if (!name) return;
    const { pages: sentPages } = useComposerStore.getState();
    const { panels: storePanels, currentProject: storeProject } = useProjectStore.getState();
    try {
      const body: Record<string, unknown> = {
        name,
        panels: storePanels,
        settings: { ...(storeProject?.settings || {}), detailLevel: 3 },
        composerPages: sentPages,
      };
      const res = await fetch('/api/projects/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = res.ok ? await res.json().catch(() => null) : null;
      if (!data?.success || !data.project?.id) {
        flash(`${t.composer.saveFailed || 'Save failed'}${res.ok ? '' : ` (HTTP ${res.status})`}`);
        return;
      }
      // the base for later page saves (read-only GET)
      let base: string | null = null;
      try {
        const lr = await fetch(`/api/projects/load/${data.project.id}`);
        if (lr.ok) {
          const ld = await lr.json();
          if (typeof ld.pagesBase === 'string') base = ld.pagesBase;
        }
      } catch { /* base stays unknown; the next save sends null */ }
      setProjectMeta({
        projectId: data.project.id,
        projectName: data.project.name ?? name,
        pagesBase: base,
        savedPages: sentPages,
      });
      flash(t.composer.savedSuccess || 'Saved!');
      setShowSaveModal(false);
      setSaveProjectName('');
    } catch {
      flash(t.composer.saveFailed || 'Save failed');
    }
  };

  const saveNow = async () => {
    flash(t.composer.saving || 'Saving…', true);
    const result = await savePages({ force: true });
    if (result === 'saved') { setSaveFailures(0); flash(t.composer.savedSuccess || 'Saved!'); }
    else if (result === 'error') { setSaveFailures(n => n + 1); flash(t.composer.saveFailed || 'Save failed'); }
    else flash('');
  };

  // autosave: only the pages, against the base they were loaded from; the
  // `pages` reference changes on every edit (immutable updates). A failed
  // save is retried with backoff (RETRY_DELAYS) until one goes through.
  useEffect(() => {
    if (!currentProjectId || saveConflict || pages.length === 0) return;
    if (pages === useComposerStore.getState()._savedPages) return;
    const delay = saveFailures === 0 ? 2000 : RETRY_DELAYS[Math.min(saveFailures, RETRY_DELAYS.length) - 1];
    const id = setTimeout(() => {
      savePages().then(result => {
        if (result === 'error') setSaveFailures(n => n + 1);
        else if (result === 'saved') setSaveFailures(0);
      });
    }, delay);
    return () => clearTimeout(id);
  }, [pages, currentProjectId, saveConflict, savePages, saveFailures]);

  // a save that failed because the session ended: retry as soon as the user signs in again
  useEffect(() => {
    const onRestored = () => {
      if (!hasUnsavedPages(useComposerStore.getState())) return;
      savePages().then(result => {
        if (result === 'error') setSaveFailures(n => n + 1);
        else if (result === 'saved') setSaveFailures(0);
      });
    };
    window.addEventListener(AUTH_RESTORED_EVENT, onRestored);
    return () => window.removeEventListener(AUTH_RESTORED_EVENT, onRestored);
  }, [savePages]);

  // another tab asked to open a project here: save (or confirm dropping) the
  // pages being edited first, since loading replaces them
  useEffect(() => {
    if (!composerProjectId) return;
    let cancelled = false;
    (async () => {
      // past the effect itself: a StrictMode re-run cancels this one before it asks anything
      await Promise.resolve();
      if (cancelled) return;
      setLoadError('');
      const s = useComposerStore.getState();
      if (hasUnsavedPages(s)) {
        const result = s.projectId ? await savePages() : 'unsaved';
        if (cancelled) return;
        if (result !== 'saved' && result !== 'skipped') {
          const why = result === 'conflict'
            ? 'Your Composer changes could not be saved: the pages were changed elsewhere.'
            : result === 'error'
              ? 'Your Composer changes could not be saved (the server did not accept them).'
              : 'The composition open in the Composer has not been saved as a project.';
          if (!window.confirm(`${why}\n\nOpen the other project anyway and discard them?`)) {
            if (result === 'error') setSaveFailures(n => n + 1);
            setComposerProjectId(null);
            return;
          }
        }
      }
      try {
        await loadProject(composerProjectId);
        if (!cancelled) setSaveFailures(0);
      } catch (err) {
        console.error('composer: project load failed:', err);
        if (!cancelled) setLoadError(`Could not load the project (${err instanceof Error ? err.message : 'network error'}).`);
      }
      if (!cancelled) setComposerProjectId(null);
    })();
    return () => { cancelled = true; };
  }, [composerProjectId, loadProject, savePages, setComposerProjectId]);

  const reloadProject = () => {
    if (!currentProjectId) return;
    setLoadError('');
    loadProject(currentProjectId).catch(err => {
      setLoadError(`Could not reload the project (${err instanceof Error ? err.message : 'network error'}).`);
    });
  };

  const currentPage = pages.find(p => p.id === currentPageId);

  const [showSaveTplModal, setShowSaveTplModal] = useState(false);
  const [tplName, setTplName] = useState('');
  const [showTemplateMenu, setShowTemplateMenu] = useState(false);

  // Close template menu on outside click
  useEffect(() => {
    if (!showTemplateMenu) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (target.closest('.composer-template-menu')) return;
      if (target.closest('.composer-manage-templates-btn')) return;
      setShowTemplateMenu(false);
    };
    window.addEventListener('mousedown', handler);
    return () => window.removeEventListener('mousedown', handler);
  }, [showTemplateMenu]);

  const handleTemplateChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    if (!currentPageId) return;
    const value = e.target.value;
    if (value.startsWith('user:')) {
      const tplId = value.slice('user:'.length);
      applyUserTemplate(currentPageId, tplId);
    } else {
      applyTemplateToPage(currentPageId, value);
    }
  };

  const handleSaveTemplate = async () => {
    const name = tplName.trim();
    if (!name) return;
    const id = await saveAsUserTemplate(name);
    if (id) {
      setShowSaveTplModal(false);
      setTplName('');
      flash(t.composer.templateSaved || 'Template saved');
    } else {
      flash(t.composer.saveFailed || 'Save failed');
    }
  };

  const handleDeleteUserTemplate = async (e: React.MouseEvent, tplId: string) => {
    e.stopPropagation();
    if (!confirm(t.composer.confirmDeleteTemplate || 'Delete this template?')) return;
    await deleteUserTemplate(tplId);
    // If the currently-active page came from this template, fall back to 'blank'
    if (currentPage?.templateId === `user:${tplId}`) {
      applyTemplateToPage(currentPageId!, 'blank');
    }
  };

  const downloadPageImage = (pageId: string) => {
    const page = pages.find(p => p.id === pageId);
    if (!page) return;
    // Server-side rendering first (parity: corners, overlays, borders);
    // fall back to the legacy local canvas renderer on any failure.
    fetch('/api/render/page', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ page, scale: 2 }),
    })
      .then(async resp => {
        if (resp.ok) {
          const blob = await resp.blob();
          downloadBlob(blob, timestampedName((page.name || 'page').replace(/\s+/g, '_'), 'png'));
          return;
        }
        throw new Error(`render failed: ${resp.status}`);
      })
      .catch(() => {
        renderPageToImage(page).then(dataUrl => {
          if (!dataUrl) return;
          const a = document.createElement('a');
          a.href = dataUrl;
          a.download = timestampedName((page.name || 'page').replace(/\s+/g, '_'), 'png');
          a.click();
        });
      });
  };

  const handleExport = (type: 'png' | 'pdf' | 'zip') => {
    if (type === 'png') {
      if (currentPageId) downloadPageImage(currentPageId);
      return;
    }
    if (type === 'pdf' || type === 'zip') {
      exportAllPages(type);
    }
  };

  const exportAllPages = async (type: 'pdf' | 'zip') => {
    // Server-side rendering keeps the export identical to what the agent
    // pipeline produces; the legacy canvas path stays as a fallback.
    try {
      const resp = await fetch('/api/render/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pages, format: type, scale: 2 }),
      });
      if (resp.ok) {
        const blob = await resp.blob();
        downloadBlob(blob, timestampedName('manga', type));
        return;
      }
      console.warn('Server export unavailable, falling back to canvas:', resp.status);
    } catch (err) {
      console.warn('Server export failed, falling back to canvas:', err);
    }
    const results = await Promise.all(pages.map(p => renderPageToImage(p)));
    const canvasPages = pages.map((p, i) => ({ name: p.name || 'page', dataUrl: results[i] }));
    sendToBackend(canvasPages, type);
  };

  const sendToBackend = async (canvasPages: { name: string; dataUrl: string }[], type: 'pdf' | 'zip') => {
    try {
      const endpoint = type === 'pdf' ? '/api/export/composer-pdf' : '/api/export/composer-images';
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pages: canvasPages }),
      });
      const data = await response.json();
      if (data.downloadUrl) {
        const a = document.createElement('a');
        a.href = data.downloadUrl;
        a.download = '';
        a.click();
      } else if (data.success) {
        alert(`${type.toUpperCase()} exported successfully!`);
      }
    } catch (err) {
      console.error('Export failed:', err);
    }
  };

  const [showExportMenu, setShowExportMenu] = useState(false);

  const bubbleTypes: BubbleType[] = ['speech', 'thought', 'shout', 'whisper', 'narration', 'inner-voice'];

  return (
    <div className="composer-tab">
      <div className="composer-page-list" data-tour="composer-pages">
        <div className="composer-page-list-header">
          <span>{t.composer.pages}</span>
        </div>
        <div className="composer-page-items">
          {pages.map((page) => (
            <PageThumb
              key={page.id}
              page={page}
              active={currentPageId === page.id}
              canDelete={pages.length > 1}
              duplicateTitle={t.composer.duplicatePage}
              deleteTitle={t.composer.deletePage}
              onSelect={setCurrentPage}
              onDuplicate={duplicatePage}
              onDelete={removePage}
            />
          ))}
        </div>
        <button className="composer-add-page-btn" onClick={() => addPage('blank')}>
          {t.composer.addPage}
        </button>
        <button
          className="composer-add-page-btn"
          onClick={autoPaginate}
          disabled={!currentProjectId || paginating || saveConflict}
          title={t.composer.autoPaginate || 'Auto Pages'}
        >
          <FiLayout size={13} style={{ marginRight: 4, verticalAlign: -2 }} />
          {t.composer.autoPaginate || 'Auto Pages'}
        </button>
      </div>

      <div className="composer-canvas-workspace">
        <div className="composer-toolbar">
          <div className="composer-toolbar-group" data-tour="composer-tools">
            <button
              className={`composer-tool-btn composer-tool-labeled ${activeTool === 'select' ? 'active' : ''}`}
              title={t.composer.select}
              onClick={() => setActiveTool('select')}
            >
              <FiMousePointer size={15} />
              <span className="composer-tool-label">{t.composer.select}</span>
            </button>
            <button
              className={`composer-tool-btn composer-tool-labeled ${activeTool === 'split' ? 'active' : ''}`}
              title={t.composer.split || 'Cut'}
              onClick={() => setActiveTool('split')}
            >
              <FiScissors size={15} />
              <span className="composer-tool-label">{t.composer.split || 'Cut'}</span>
            </button>
            <button
              className={`composer-tool-btn composer-tool-labeled ${activeTool === 'text' ? 'active' : ''}`}
              title={t.composer.text}
              onClick={() => setActiveTool('text')}
            >
              <FiType size={15} />
              <span className="composer-tool-label">{t.composer.text}</span>
            </button>
            <button
              className={`composer-tool-btn composer-tool-labeled ${activeTool === 'bubble' ? 'active' : ''}`}
              title={t.composer.bubble}
              onClick={() => setActiveTool('bubble')}
            >
              <FiMessageCircle size={15} />
              <span className="composer-tool-label">{t.composer.bubble}</span>
            </button>
          </div>

          {activeTool === 'bubble' && (
            <div className="composer-bubble-pills">
              {bubbleTypes.map(bt => (
                <button
                  key={bt}
                  className={`composer-bubble-pill ${activeBubbleType === bt ? 'active' : ''}`}
                  onClick={() => setActiveBubbleType(bt)}
                  title={bt === 'inner-voice' ? t.composer.innerVoice : bt}
                >
                  <BubbleIcon type={bt} />
                  <span className="composer-bubble-pill-label">
                    {bt === 'inner-voice' ? t.composer.innerVoice : bt}
                  </span>
                </button>
              ))}
            </div>
          )}

          <div className="composer-toolbar-group" data-tour="composer-templates">
            <select
              className="composer-template-select"
              value={currentPage?.templateId || 'blank'}
              onChange={handleTemplateChange}
            >
              <optgroup label={t.composer.builtInTemplates || 'Built-in'}>
                {TEMPLATES.map(tmpl => (
                  <option key={tmpl.id} value={tmpl.id}>
                    {language === 'zh' ? tmpl.nameZh : tmpl.name}
                  </option>
                ))}
              </optgroup>
              {userTemplates.length > 0 && (
                <optgroup label={t.composer.userTemplates || 'My Templates'}>
                  {userTemplates.map(tmpl => (
                    <option key={tmpl.id} value={`user:${tmpl.id}`}>
                      {tmpl.name}
                    </option>
                  ))}
                </optgroup>
              )}
            </select>
            <button
              className="composer-tool-btn composer-add-frame-btn"
              title={t.composer.addFrame || 'Add Frame'}
              onClick={() => addFrame()}
            >
              <FiPlusSquare size={15} />
              <span className="composer-add-frame-label">{t.composer.addFrame || 'Add Frame'}</span>
            </button>
            <button
              className="composer-tool-btn composer-add-image-btn"
              title={t.composer.addImage || 'Add Image'}
              onClick={() => openImagePicker({ kind: 'newPageImage', id: '' })}
            >
              <FiImage size={15} />
              <span className="composer-add-image-label">{t.composer.addImage || 'Add Image'}</span>
            </button>
            <div ref={sfxRef} style={{ position: 'relative', display: 'inline-flex' }}>
              <button
                className="composer-tool-btn composer-add-image-btn"
                title={t.composer.sfx || 'SFX'}
                onClick={toggleSfxMenu}
              >
                <FiZap size={15} />
                <span className="composer-add-image-label">{t.composer.sfx || 'SFX'}</span>
              </button>
              {showSfxMenu && (
                <div
                  style={{
                    position: 'absolute', top: '100%', left: 0, zIndex: 50,
                    background: 'var(--bg-secondary)', border: '1px solid var(--border-default)',
                    borderRadius: 6, padding: 6, display: 'grid',
                    gridTemplateColumns: 'repeat(3, minmax(64px, 1fr))', gap: 4,
                    maxHeight: 220, overflowY: 'auto', boxShadow: '0 4px 16px rgba(0,0,0,.25)',
                  }}
                >
                  {sfxPresets.filter(p => language === 'zh' || !p.lang || p.lang === 'en').map(p => (
                    <button
                      key={p.word}
                      className="composer-prop-btn"
                      style={{ display: 'flex', flexDirection: 'column', fontSize: 15, fontWeight: 700, padding: '6px 4px' }}
                      title={language === 'zh' ? p.meaningZh || p.meaning : p.meaning}
                      onClick={() => addSfx(p.word)}
                    >
                      <span>{p.word}</span>
                      <span style={{ fontSize: 9, fontWeight: 400, opacity: 0.7 }}>{language === 'zh' ? p.meaningZh || p.meaning : p.meaning}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <button
              className="composer-tool-btn composer-save-template-btn"
              title={t.composer.saveTemplate || 'Save current layout as template'}
              onClick={() => { setTplName(currentPage?.name || 'My Template'); setShowSaveTplModal(true); }}
            >
              <FiBook size={15} />
              <span className="composer-save-template-label">{t.composer.saveTemplate || 'Save Template'}</span>
            </button>
            <div style={{ position: 'relative' }}>
              <button
                className="composer-tool-btn composer-manage-templates-btn"
                title={t.composer.manageTemplates || 'Manage templates'}
                onClick={() => setShowTemplateMenu(v => !v)}
              >
                <span className="composer-manage-templates-icon">⋯</span>
              </button>
              {showTemplateMenu && (
                <div className="composer-template-menu" onClick={e => e.stopPropagation()}>
                  <div className="composer-template-menu-header">
                    {t.composer.userTemplates || 'My Templates'}
                  </div>
                  {userTemplates.length === 0 ? (
                    <div className="composer-template-menu-empty">
                      {t.composer.noUserTemplates || 'No saved templates'}
                    </div>
                  ) : (
                    userTemplates.map(tpl => (
                      <div key={tpl.id} className="composer-template-menu-item">
                        <span className="composer-template-menu-name">{tpl.name}</span>
                        <button
                          className="composer-template-menu-delete"
                          title={t.composer.deleteTemplate || 'Delete'}
                          onClick={(e) => handleDeleteUserTemplate(e, tpl.id)}
                        >
                          <FiTrash size={11} />
                        </button>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>
          </div>

          <div className="composer-toolbar-spacer" />

          <div className="composer-toolbar-group">
            <button className="composer-tool-btn" title={t.composer.undo} onClick={undo}>
              <FiRotateCcw size={15} />
            </button>
            <button className="composer-tool-btn" title={t.composer.redo} onClick={redo}>
              <FiRotateCw size={15} />
            </button>
          </div>

          <div className="composer-toolbar-group">
            <div className="composer-zoom-controls">
              <button onClick={() => setZoom(zoom - 0.1)} title="Zoom out">−</button>
              <span>{Math.round(zoom * 100)}%</span>
              <button onClick={() => setZoom(zoom + 0.1)} title="Zoom in">+</button>
            </div>
          </div>

          {saveFailures > 0 && !saveConflict && pages !== savedPages && (
            <span className="composer-save-failed" role="status" title={t.composer.autoSaveFailedHint}>
              {t.composer.autoSaveFailed || 'Not saved — the last save failed; retrying'}
            </span>
          )}
          {saveMsg ? (
            <span style={{ fontSize: 12, color: 'var(--accent-primary)', marginRight: 8 }}>
              {saveMsg}
            </span>
          ) : currentProjectName ? (
            <span style={{ fontSize: 12, color: 'var(--text-muted)', marginRight: 8 }}>
              {currentProjectName}
            </span>
          ) : (
            <span style={{ fontSize: 12, color: 'var(--text-muted)', marginRight: 8 }}>
              {t.composer.unsaved || 'Unsaved'}
            </span>
          )}

          <div className="composer-toolbar-group" data-tour="composer-save">
            <button
              className="composer-tool-btn"
              title="Save to Showcase"
              disabled={saveConflict}
              onClick={() => {
                if (currentProjectId) {
                  saveNow();
                } else {
                  setShowSaveModal(true);
                }
              }}
            >
              <FiSave size={15} />
            </button>
            <div style={{ position: 'relative' }}>
              <button
                className="composer-tool-btn"
                title={t.composer.export}
                onClick={() => setShowExportMenu(v => !v)}
              >
                <FiDownload size={15} />
              </button>
              {showExportMenu && (
                <div className="composer-export-menu">
                  <button onClick={() => { handleExport('png'); setShowExportMenu(false); }}>
                    Download PNG (current page)
                  </button>
                  <button onClick={() => { handleExport('pdf'); setShowExportMenu(false); }}>
                    Export as PDF
                  </button>
                  <button onClick={() => { handleExport('zip'); setShowExportMenu(false); }}>
                    Export as ZIP
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        {(saveConflict || loadError) && (
          <div className="composer-canvas-hint composer-save-conflict" role="alert">
            <span className="composer-canvas-hint-dot" />
            <span>{saveConflict ? (t.composer.pagesConflict || CONFLICT_MSG) : loadError}</span>
            {saveConflict && currentProjectId && (
              <button className="btn btn-secondary composer-save-conflict-btn" onClick={reloadProject}>
                {t.composer.reload || 'Reload'}
              </button>
            )}
            {!saveConflict && (
              <button
                className="composer-canvas-hint-cancel"
                onClick={() => setLoadError('')}
                title="Dismiss"
              >
                <FiX size={12} />
              </button>
            )}
          </div>
        )}

        {(activeTool === 'text' || activeTool === 'bubble') && (
          <div className="composer-canvas-hint" role="status">
            <span className="composer-canvas-hint-dot" />
            <span>
              {activeTool === 'text'
                ? 'Click anywhere on the canvas to place a text box. Then double-click it to edit.'
                : 'Click anywhere on the canvas to place a bubble. Then double-click it to type.'}
            </span>
            <button
              className="composer-canvas-hint-cancel"
              onClick={() => setActiveTool('select')}
              title="Cancel (Switch to Select tool)"
            >
              <FiX size={12} />
            </button>
          </div>
        )}

        <Canvas />
      </div>

      <PropertiesPanel />

      {showSaveModal && (
        <div className="composer-image-picker-overlay" onClick={() => setShowSaveModal(false)}>
          <div className="composer-image-picker" onClick={e => e.stopPropagation()} style={{ width: 360 }}>
            <div className="composer-image-picker-header">
              <h3>Save to Showcase</h3>
              <button className="composer-tool-btn" onClick={() => setShowSaveModal(false)}>
                <FiX size={16} />
              </button>
            </div>
            <div style={{ padding: 'var(--space-md)' }}>
              <label style={{ fontSize: 12, color: 'var(--text-secondary)', display: 'block', marginBottom: 6 }}>
                Project Name
              </label>
              <input
                className="input"
                autoFocus
                value={saveProjectName}
                onChange={e => setSaveProjectName(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && saveToShowcase()}
                placeholder="My Manga Chapter 1"
              />
              <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setShowSaveModal(false)}>
                  Cancel
                </button>
                <button
                  className="btn btn-primary"
                  style={{ flex: 1 }}
                  disabled={!saveProjectName.trim()}
                  onClick={saveToShowcase}
                >
                  Save
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {showSaveTplModal && (
        <div className="composer-image-picker-overlay" onClick={() => setShowSaveTplModal(false)}>
          <div className="composer-image-picker" onClick={e => e.stopPropagation()} style={{ width: 360 }}>
            <div className="composer-image-picker-header">
              <h3>{t.composer.saveTemplate || 'Save as Template'}</h3>
              <button className="composer-tool-btn" onClick={() => setShowSaveTplModal(false)}>
                <FiX size={16} />
              </button>
            </div>
            <div style={{ padding: 'var(--space-md)' }}>
              <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 8 }}>
                {t.composer.saveTemplateHint || 'Saves the current page\'s layout (no images).'}
              </p>
              <label style={{ fontSize: 12, color: 'var(--text-secondary)', display: 'block', marginBottom: 6 }}>
                {t.composer.templateName || 'Template name'}
              </label>
              <input
                className="input"
                autoFocus
                value={tplName}
                onChange={e => setTplName(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSaveTemplate()}
                placeholder="My Manga Layout"
              />
              <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setShowSaveTplModal(false)}>
                  {t.composer.cancel || 'Cancel'}
                </button>
                <button
                  className="btn btn-primary"
                  style={{ flex: 1 }}
                  disabled={!tplName.trim()}
                  onClick={handleSaveTemplate}
                >
                  {t.composer.save || 'Save'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
