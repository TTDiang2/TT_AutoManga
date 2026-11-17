import { useState, useEffect, useRef } from 'react';
import { FiGrid, FiPlus, FiTrash2, FiFolder, FiEye, FiEdit2, FiChevronLeft, FiChevronRight, FiDownload, FiLayers } from 'react-icons/fi';
import { useProjectStore } from '../../store/projectStore';
import { useTranslation } from '../../hooks/useTranslation';
import { renderPageToImage } from '../composer/pageRenderer';
import type { Project, ComposerPage } from '../../types';
import { CollectionsView } from './CollectionsView';
import './collections.css';

export function ShowcaseTab() {
  const { setCurrentProject, setActiveTab, setComposerProjectId, loadProjectWithImages } = useProjectStore();
  const { t } = useTranslation();
  const [projects, setProjects] = useState<Project[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [mode, setMode] = useState<'browse' | 'viewing' | 'editing'>('browse');
  const [activeProject, setActiveProject] = useState<Project | null>(null);
  const [readerPage, setReaderPage] = useState(0);
  // only the latest project click may set the active project
  const loadSeqRef = useRef(0);
  const [coverImages, setCoverImages] = useState<Record<string, string>>({});
  const [showNewModal, setShowNewModal] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  // browse: every comic (as before) or the collections (series of episodes)
  const [view, setView] = useState<'comics' | 'collections'>('comics');
  const [openCollectionId, setOpenCollectionId] = useState<string | null>(null);

  const loadProjects = async () => {
    setIsLoading(true);
    try {
      const [projectsRes, coversRes] = await Promise.all([
        fetch('/api/projects/'),
        fetch('/api/projects/covers'),
      ]);
      const projectsData = await projectsRes.json();
      const coversData = await coversRes.json();
      const projectList = projectsData.projects || [];
      setProjects(projectList);
      setCoverImages(prev => ({ ...prev, ...(coversData.covers || {}) }));
    } catch (error) {
      console.error('Failed to load projects:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCreateProject = async () => {
    if (!newProjectName.trim()) return;
    const newProject: Project = {
      id: '',
      name: newProjectName,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      panels: [],
      settings: { detailLevel: 3 },
      composerPages: [],
    };
    try {
      const response = await fetch('/api/projects/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newProject),
      });

      const data = await response.json();
      if (data.project) {
        loadProjectWithImages(data.project.id);
        setShowNewModal(false);
        setNewProjectName('');
        loadProjects();
      }
    } catch (err) {
      console.error('Failed to create project:', err);
    }
  };

  useEffect(() => {
    loadProjects();
  }, []);

  useEffect(() => {
    if (mode === 'browse') {
      loadProjects();
    }
  }, [mode, JSON.stringify(projects.map(p => p.id))]);

  const handleLoadProject = async (projectId: string, action: 'view' | 'edit' = 'view') => {
    const seq = ++loadSeqRef.current;
    try {
      const response = await fetch(`/api/projects/load/${projectId}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (!data.project || seq !== loadSeqRef.current) return;
      const project = data.project;
      setActiveProject(project);
      setCurrentProject(project);

      if (action === 'view') {
        // pages render server-side on demand (see ComicReader)
        setMode('viewing');
        setReaderPage(0);
      } else {
        // load panels into the store too, or the Storyboard tab shows 0
        loadProjectWithImages(project.id);
        // only "edit" opens it in the Composer (that replaces the pages open there)
        setComposerProjectId(project.id);
        setActiveTab('composer');
      }
    } catch (error) {
      console.error('Failed to load project:', error);
    }
  };

  const [exportingId, setExportingId] = useState<string | null>(null);
  const [pageNumbers, setPageNumbers] = useState(false);

  const handleExportProject = async (projectId: string) => {
    setExportingId(projectId);
    try {
      // Server-side rendering first: same pipeline the agent export uses,
      // and it keeps deformed frames / breakout overlays in the output.
      const resp = await fetch('/api/agent/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId, format: 'pdf', scale: 2, page_numbers: pageNumbers }),
      });
      if (resp.ok) {
        const data = await resp.json();
        if (data.pdf?.url) {
          const a = document.createElement('a');
          a.href = data.pdf.url;
          a.download = '';
          a.click();
          return;
        }
      }
      console.warn('Server export unavailable, falling back to canvas:', resp.status);

      const res = await fetch(`/api/projects/load/${projectId}`);
      const data = await res.json();
      if (!data.project?.composerPages?.length) return;
      const pages = data.project.composerPages;
      const results = await Promise.all((pages as ComposerPage[]).map(p => renderPageToImage(p)));
      const canvasPages = (pages as ComposerPage[]).map((p, i: number) => ({
        name: p.name || 'page',
        dataUrl: results[i],
      })).filter(p => Boolean(p.dataUrl));

      const legacyResp = await fetch('/api/export/composer-images', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pages: canvasPages }),
      });
      const exportData = await legacyResp.json();
      if (exportData.downloadUrl) {
        const a = document.createElement('a');
        a.href = exportData.downloadUrl;
        a.download = '';
        a.click();
      }
    } catch (err) {
      console.error('Export failed:', err);
    } finally {
      setExportingId(null);
    }
  };

  const handleDeleteProject = async (projectId: string) => {
    if (!confirm('Are you sure you want to delete this project?')) return;

    try {
      await fetch(`/api/projects/delete/${projectId}`, { method: 'DELETE' });
      loadProjects();
    } catch (error) {
      console.error('Failed to delete project:', error);
    }
  };

  return (
    <div className="showcase-tab">
      <div className="showcase-header flex items-center justify-between mb-lg">
        <div>
          <h3>
            {mode === 'browse' && t.showcase.title}
            {mode === 'viewing' && activeProject?.name}
            {mode === 'editing' && (activeProject?.name + ' — Editing')}
          </h3>
          <p className="text-sm text-secondary mt-sm">
            {mode === 'browse' && view === 'comics' && `${projects.length} comic${projects.length !== 1 ? 's' : ''}`}
            {mode === 'browse' && view === 'collections' && t.showcase.collections}
            {mode === 'viewing' && `Page ${readerPage + 1} of ${activeProject?.composerPages?.length || 0}`}
            {mode === 'editing' && 'Editing in Composer'}
          </p>
        </div>
        <div className="flex gap-sm">
          {mode !== 'browse' && (
            <button
              className="btn btn-secondary"
              onClick={() => { setMode('browse'); setActiveProject(null); }}
            >
              <FiFolder size={14} /> All Comics
            </button>
          )}
          {mode === 'browse' && (
            <div className="showcase-view-toggle" role="tablist">
              <button role="tab" aria-selected={view === 'comics'} className={view === 'comics' ? 'active' : ''}
                onClick={() => setView('comics')}>
                <FiGrid size={13} /> {t.showcase.comics}
              </button>
              <button role="tab" aria-selected={view === 'collections'} className={view === 'collections' ? 'active' : ''}
                onClick={() => setView('collections')}>
                <FiLayers size={13} /> {t.showcase.collections}
              </button>
            </div>
          )}
          {mode === 'browse' && (
            <label
              className="flex items-center gap-xs text-sm"
              style={{ marginRight: 8, cursor: 'pointer', userSelect: 'none' }}
            >
              <input
                type="checkbox"
                checked={pageNumbers}
                onChange={e => setPageNumbers(e.target.checked)}
              />
              {t.showcase.pageNumbers || 'Page numbers'}
            </label>
          )}
          {mode === 'browse' && view === 'comics' && (
            <button className="btn btn-secondary" onClick={() => setShowNewModal(true)}>
              <FiPlus size={14} /> New Comic
            </button>
          )}
        </div>
      </div>

      {mode === 'browse' && view === 'collections' ? (
        <CollectionsView
          projects={projects}
          openId={openCollectionId}
          onOpen={setOpenCollectionId}
          onView={id => handleLoadProject(id, 'view')}
          onEdit={id => handleLoadProject(id, 'edit')}
          onExport={handleExportProject}
          exportingId={exportingId}
        />
      ) : mode === 'browse' && projects.length === 0 && !isLoading ? (
        <div className="empty-state">
          <FiFolder size={48} />
          <h3>{t.showcase.noProjects}</h3>
          <p>{t.showcase.noProjectsDesc}</p>
        </div>
      ) : mode === 'browse' ? (
        <div className="projects-grid">
          {projects.map(project => (
            <div key={project.id} className="project-card card">
              <div className="project-cover">
                {coverImages[project.id] ? (
                  <img src={coverImages[project.id]} alt={project.name} />
                ) : (
                  <div className="cover-placeholder">
                    <FiGrid size={24} />
                  </div>
                )}
              </div>
              <div className="project-info">
                <h4>{project.name}</h4>
                <p className="text-sm text-muted">
                  {project.composerPages?.length || 0} pages • {new Date(project.updatedAt).toLocaleDateString()}
                </p>
              </div>
              <div className="project-card-actions">
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => handleLoadProject(project.id, 'view')}
                  title="View"
                >
                  <FiEye size={14} />
                </button>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => handleLoadProject(project.id, 'edit')}
                  title="Edit"
                >
                  <FiEdit2 size={14} />
                </button>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => handleExportProject(project.id)}
                  title="Export PDF"
                  disabled={exportingId === project.id}
                >
                  <FiDownload size={14} />
                </button>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => handleDeleteProject(project.id)}
                  title="Delete"
                >
                  <FiTrash2 size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : mode === 'viewing' && activeProject ? (
        <ComicReader
          project={activeProject}
          page={readerPage}
          onPageChange={setReaderPage}
          onBack={() => setMode('browse')}
          onEdit={() => handleLoadProject(activeProject.id, 'edit')}
        />
      ) : null}

      {showNewModal && (
        <div className="modal-overlay" onClick={() => setShowNewModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <h3>{t.showcase.newProject}</h3>
            <input
              className="input mt-md"
              placeholder={t.showcase.projectName}
              value={newProjectName}
              onChange={(e) => setNewProjectName(e.target.value)}
              autoFocus
            />
            <div className="flex gap-sm mt-lg justify-end">
              <button className="btn btn-secondary" onClick={() => setShowNewModal(false)}>
                {t.showcase.cancel}
              </button>
              <button className="btn btn-primary" onClick={handleCreateProject}>
                {t.showcase.create}
              </button>
            </div>
          </div>
        </div>
      )}

      <style>{`
        .projects-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
          gap: var(--space-lg);
        }
        .project-card {
          padding: 0;
          overflow: hidden;
          cursor: pointer;
          position: relative;
        }
        .project-card.active {
          border-color: var(--accent-primary);
          box-shadow: 0 0 0 2px var(--accent-primary);
        }
        .project-cover {
          aspect-ratio: 3/4;
          background: var(--bg-tertiary);
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .project-cover img {
          width: 100%;
          height: 100%;
          object-fit: cover;
        }
        .cover-placeholder {
          color: var(--text-muted);
        }
        .project-info {
          padding: var(--space-md);
        }
        .project-info h4 {
          font-size: 14px;
          font-weight: 500;
          margin-bottom: var(--space-xs);
        }
        .delete-btn {
          position: absolute;
          top: var(--space-sm);
          right: var(--space-sm);
          opacity: 0;
          transition: opacity var(--transition-default);
        }
        .project-card:hover .delete-btn {
          opacity: 1;
        }
        .modal-content {
          width: 400px;
        }
        .export-options {
          padding: var(--space-md);
          background: var(--bg-tertiary);
          border-radius: var(--radius-md);
        }
        .project-card-actions {
          display: flex;
          gap: 4px;
          padding: var(--space-sm) var(--space-md);
        }
        .project-card-actions .btn {
          flex: 1;
          justify-content: center;
        }
        .project-card {
          cursor: default;
        }
        .comic-reader {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: var(--space-md);
        }
        .comic-reader-page {
          max-width: 600px;
          width: 100%;
          border-radius: var(--radius-md);
          overflow: hidden;
          box-shadow: 0 8px 32px rgba(0,0,0,0.2);
        }
        .comic-reader-page img {
          width: 100%;
          display: block;
        }
        .comic-reader-nav {
          display: flex;
          align-items: center;
          gap: var(--space-md);
        }
        .comic-reader-nav button {
          padding: 8px 16px;
        }
        .comic-reader-placeholder {
          aspect-ratio: 2/3;
          max-width: 400px;
          width: 100%;
          background: var(--bg-tertiary);
          border-radius: var(--radius-md);
          display: flex;
          align-items: center;
          justify-content: center;
          color: var(--text-muted);
        }
      `}</style>
    </div>
  );
}

/** Server-rendered page preview: same renderer as export (overlays, corners, borders, image offset/scale). */
function previewUrl(project: Project, page: ComposerPage) {
  const v = encodeURIComponent(project.updatedAt || '');
  return `/api/agent/projects/${encodeURIComponent(project.id)}/pages/${encodeURIComponent(page.id)}/preview.png?scale=1&v=${v}`;
}

function ReaderPage({ src, label, visible }: { src: string; label: string; visible: boolean }) {
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  return (
    <>
      <div className="comic-reader-page" style={{ display: visible && status === 'ready' ? undefined : 'none' }}>
        <img
          src={src}
          alt={label}
          onLoad={() => setStatus('ready')}
          onError={() => setStatus('error')}
        />
      </div>
      {visible && status !== 'ready' && (
        <div className="comic-reader-placeholder">
          {status === 'error' ? `Could not render ${label.toLowerCase()}` : `Loading ${label.toLowerCase()}...`}
        </div>
      )}
    </>
  );
}

function ComicReader({ project, page, onPageChange, onBack, onEdit }: {
  project: Project;
  page: number;
  onPageChange: (p: number) => void;
  onBack: () => void;
  onEdit: () => void;
}) {
  const pages: ComposerPage[] = project.composerPages || [];
  const total = pages.length;

  const prev = () => { if (page > 0) onPageChange(page - 1); };
  const next = () => { if (page < total - 1) onPageChange(page + 1); };

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft') prev();
      if (e.key === 'ArrowRight') next();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [page, total]);

  return (
    <div className="comic-reader">
      {total === 0 ? (
        <div className="comic-reader-placeholder">No pages yet</div>
      ) : (
        // the current page plus its neighbours (preloaded, hidden); keyed by
        // page id so a page's load state never bleeds into another page
        pages.map((p, i) => Math.abs(i - page) <= 1 ? (
          <ReaderPage
            key={`${project.id}:${p.id}`}
            src={previewUrl(project, p)}
            label={`Page ${i + 1}`}
            visible={i === page}
          />
        ) : null)
      )}
      <div className="comic-reader-nav">
        <button className="btn btn-secondary" onClick={prev} disabled={page === 0}>
          <FiChevronLeft size={16} /> Previous
        </button>
        <span>{total === 0 ? 0 : page + 1} / {total}</span>
        <button className="btn btn-secondary" onClick={next} disabled={page >= total - 1}>
          Next <FiChevronRight size={16} />
        </button>
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <button className="btn btn-secondary" onClick={onBack}>Back</button>
        <button className="btn btn-primary" onClick={onEdit}>Edit in Composer</button>
      </div>
    </div>
  );
}
