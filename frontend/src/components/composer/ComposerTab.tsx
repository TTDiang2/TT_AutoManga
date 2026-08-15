import { useState, useEffect } from 'react';
import {
  FiMousePointer, FiType, FiMessageCircle,
  FiRotateCcw, FiRotateCw, FiDownload,
  FiCopy, FiTrash2, FiSave, FiBook, FiX, FiPlusSquare, FiTrash,
  FiImage,
} from 'react-icons/fi';
import { useComposerStore, TEMPLATES } from '../../store/composerStore';
import { useProjectStore } from '../../store/projectStore';
import { useTranslation } from '../../hooks/useTranslation';
import { Canvas } from './Canvas';
import { PropertiesPanel } from './PropertiesPanel';
import { renderPageToImage } from './pageRenderer';
import './composer.css';
import type { BubbleType } from '../../types';

export function ComposerTab() {
  const { t } = useTranslation();
  const language = useProjectStore(s => s.settings.language);
  const { composerProjectId, setComposerProjectId } = useProjectStore();
  const {
    pages,
    currentPageId,
    activeTool,
    activeBubbleType,
    zoom,
    selectedElementId,
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
    setPages: setComposerPages,
    addFrame,
    removeElement,
    selectElement,
    userTemplates,
    loadUserTemplates,
    saveAsUserTemplate,
    applyUserTemplate,
    deleteUserTemplate,
    openImagePicker,
  } = useComposerStore();

  useEffect(() => {
    if (pages.length === 0) {
      addPage('manga-4');
    }
  }, []);

  // Load user-saved templates on mount
  useEffect(() => {
    loadUserTemplates();
  }, [loadUserTemplates]);

  // Delete / Backspace removes the selected element. Ignored while typing in an
  // input/textarea/contentEditable to avoid hijacking text editing.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key !== 'Delete' && e.key !== 'Backspace') return;
      if (!selectedElementId) return;
      const target = e.target as HTMLElement | null;
      if (target) {
        const tag = target.tagName;
        if (tag === 'INPUT' || tag === 'TEXTAREA' || target.isContentEditable) return;
      }
      e.preventDefault();
      removeElement(selectedElementId);
      selectElement(null);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [selectedElementId, removeElement, selectElement]);

  const [showSaveModal, setShowSaveModal] = useState(false);
  const [saveProjectName, setSaveProjectName] = useState('');
  const [saveMsg, setSaveMsg] = useState('');
  const [currentProjectId, setCurrentProjectId] = useState<string | null>(null);
  const [currentProjectName, setCurrentProjectName] = useState<string | null>(null);

  const saveToShowcase = async () => {
    const name = saveProjectName.trim();
    if (!name) return;
    try {
      const body: any = {
        name,
        panels: [],
        settings: { detailLevel: 3 },
        composerPages: pages,
      };
      if (currentProjectId) body.id = currentProjectId;
      const res = await fetch('/api/projects/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (data.success) {
        setCurrentProjectId(data.project.id);
        setCurrentProjectName(data.project.name);
        setSaveMsg(t.composer.savedSuccess || 'Saved!');
        setShowSaveModal(false);
        setSaveProjectName('');
        setTimeout(() => setSaveMsg(''), 2500);
      }
    } catch {
      setSaveMsg(t.composer.saveFailed || 'Save failed');
    }
  };

  const autoSave = async () => {
    if (!currentProjectId) return;
    try {
      await fetch('/api/projects/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: currentProjectId,
          name: currentProjectName,
          panels: [],
          settings: { detailLevel: 3 },
          composerPages: pages,
        }),
      });
    } catch { /* silent auto-save */ }
  };

  useEffect(() => {
    const id = setTimeout(() => {
      if (currentProjectId && pages.length > 0) {
        autoSave();
      }
    }, 2000);
    return () => clearTimeout(id);
    }, [JSON.stringify(pages)]);

  useEffect(() => {
    if (!composerProjectId) return;
    fetch(`/api/projects/load/${composerProjectId}`)
      .then(r => r.json())
      .then(data => {
        if (!data.project) return;
        setCurrentProjectId(data.project.id);
        setCurrentProjectName(data.project.name);
        if (data.project.composerPages?.length) {
          setComposerPages(data.project.composerPages);
        }
        setComposerProjectId(null);
      });
  }, [composerProjectId]);

  const saveDraft = () => {
    localStorage.setItem('composer-draft', JSON.stringify(pages));
    setSaveMsg(t.composer.draftSaved || 'Draft saved!');
    setTimeout(() => setSaveMsg(''), 2500);
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
      setSaveMsg(t.composer.templateSaved || 'Template saved');
      setTimeout(() => setSaveMsg(''), 2500);
    } else {
      setSaveMsg(t.composer.saveFailed || 'Save failed');
      setTimeout(() => setSaveMsg(''), 2500);
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
    renderPageToImage(page).then(dataUrl => {
      if (!dataUrl) return;
      const a = document.createElement('a');
      a.href = dataUrl;
      a.download = `${(page.name || 'page').replace(/\s+/g, '_')}_${Date.now()}.png`;
      a.click();
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
      <div className="composer-page-list">
        <div className="composer-page-list-header">
          <span>{t.composer.pages}</span>
        </div>
        <div className="composer-page-items">
          {pages.map((page) => (
            <div
              key={page.id}
              className={`composer-page-thumb ${currentPageId === page.id ? 'active' : ''}`}
              onClick={() => setCurrentPage(page.id)}
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
                  title={t.composer.duplicatePage}
                  onClick={(e) => { e.stopPropagation(); duplicatePage(page.id); }}
                >
                  <FiCopy size={9} />
                </button>
                <button
                  title={t.composer.deletePage}
                  onClick={(e) => { e.stopPropagation(); if (pages.length > 1) removePage(page.id); }}
                  disabled={pages.length <= 1}
                >
                  <FiTrash2 size={9} />
                </button>
              </div>
            </div>
          ))}
        </div>
        <button className="composer-add-page-btn" onClick={() => addPage('blank')}>
          {t.composer.addPage}
        </button>
      </div>

      <div className="composer-canvas-workspace">
        <div className="composer-toolbar">
          <div className="composer-toolbar-group">
            <button
              className={`composer-tool-btn ${activeTool === 'select' ? 'active' : ''}`}
              title={t.composer.select}
              onClick={() => setActiveTool('select')}
            >
              <FiMousePointer size={15} />
            </button>
            <button
              className={`composer-tool-btn ${activeTool === 'text' ? 'active' : ''}`}
              title={t.composer.text}
              onClick={() => setActiveTool('text')}
            >
              <FiType size={15} />
            </button>
            <button
              className={`composer-tool-btn ${activeTool === 'bubble' ? 'active' : ''}`}
              title={t.composer.bubble}
              onClick={() => setActiveTool('bubble')}
            >
              <FiMessageCircle size={15} />
            </button>
          </div>

          {activeTool === 'bubble' && (
            <div className="composer-bubble-pills">
              {bubbleTypes.map(bt => (
                <button
                  key={bt}
                  className={`composer-bubble-pill ${activeBubbleType === bt ? 'active' : ''}`}
                  onClick={() => setActiveBubbleType(bt)}
                >
                  {bt === 'inner-voice' ? t.composer.innerVoice : bt}
                </button>
              ))}
            </div>
          )}

          <div className="composer-toolbar-group">
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

          <div className="composer-toolbar-group">
            <button
              className="composer-tool-btn"
              title="Save to Showcase"
              onClick={() => {
                if (currentProjectId) {
                  autoSave();
                  setSaveMsg(t.composer.savedSuccess || 'Saved!');
                  setTimeout(() => setSaveMsg(''), 2500);
                } else {
                  setShowSaveModal(true);
                }
              }}
            >
              <FiSave size={15} />
            </button>
            <button
              className="composer-tool-btn"
              title="Save Draft (local)"
              onClick={saveDraft}
            >
              <FiBook size={15} />
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
