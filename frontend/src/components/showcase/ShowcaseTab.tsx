import { useState, useEffect } from 'react';
import { FiGrid, FiPlus, FiTrash2, FiFolder, FiEye, FiEdit2, FiChevronLeft, FiChevronRight, FiDownload } from 'react-icons/fi';
import { useProjectStore } from '../../store/projectStore';
import { useComposerStore } from '../../store/composerStore';
import { useTranslation } from '../../hooks/useTranslation';
import { renderPageToImage } from '../composer/pageRenderer';
import type { Project } from '../../types';

export function ShowcaseTab() {
  const { setCurrentProject, setActiveTab, setComposerProjectId, loadProjectWithImages } = useProjectStore();
  const {} = useComposerStore();
  const { t } = useTranslation();
  const [projects, setProjects] = useState<Project[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [mode, setMode] = useState<'browse' | 'viewing' | 'editing'>('browse');
  const [activeProject, setActiveProject] = useState<Project | null>(null);
  const [readerPage, setReaderPage] = useState(0);
  const [readerImages, setReaderImages] = useState<string[]>([]);
  const [coverImages, setCoverImages] = useState<Record<string, string>>({});
  const [showNewModal, setShowNewModal] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');

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
    try {
      const response = await fetch(`/api/projects/load/${projectId}`);
      const data = await response.json();
      if (!data.project) return;
      const project = data.project;
      setActiveProject(project);
      setCurrentProject(project);
      setComposerProjectId(project.id);

      if (action === 'view') {
        setMode('viewing');
        setReaderPage(0);
        setReaderImages([]);
        if (project.composerPages?.length) {
          Promise.all(project.composerPages.map((page: any) => renderPageToImage(page)))
            .then(imgs => setReaderImages(imgs.filter(Boolean)));
        }
      } else {
        setActiveTab('composer');
      }
    } catch (error) {
      console.error('Failed to load project:', error);
    }
  };

  const [exportingId, setExportingId] = useState<string | null>(null);

  const handleExportProject = async (projectId: string) => {
    setExportingId(projectId);
    try {
      const res = await fetch(`/api/projects/load/${projectId}`);
      const data = await res.json();
      if (!data.project?.composerPages?.length) return;
      const pages = data.project.composerPages;
      const results = await Promise.all(pages.map((p: any) => renderPageToImage(p)));
      const canvasPages = pages.map((p: any, i: number) => ({
        name: p.name || 'page',
        dataUrl: results[i],
      })).filter((p: any) => p.dataUrl);

      const resp = await fetch('/api/export/composer-images', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pages: canvasPages }),
      });
      const exportData = await resp.json();
      if (exportData.downloadUrl) {
        const a = document.createElement('a');
        a.href = exportData.downloadUrl;
        a.download = `${data.project.name || 'comic'}.pdf`;
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
            {mode === 'browse' && `${projects.length} comic${projects.length !== 1 ? 's' : ''}`}
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
            <button className="btn btn-secondary" onClick={() => setShowNewModal(true)}>
              <FiPlus size={14} /> New Comic
            </button>
          )}
        </div>
      </div>

      {mode === 'browse' && projects.length === 0 && !isLoading ? (
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
          images={readerImages}
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

function ComicReader({ project, page, images, onPageChange, onBack, onEdit }: {
  project: Project;
  page: number;
  images: string[];
  onPageChange: (p: number) => void;
  onBack: () => void;
  onEdit: () => void;
}) {
  const total = project.composerPages?.length || 0;
  const currentImage = images[page];

  const prev = () => { if (page > 0) onPageChange(page - 1); };
  const next = () => { if (page < total - 1) onPageChange(page + 1); };

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft') prev();
      if (e.key === 'ArrowRight') next();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [page]);

  return (
    <div className="comic-reader">
      {currentImage ? (
        <div className="comic-reader-page">
          <img src={currentImage} alt={`Page ${page + 1}`} />
        </div>
      ) : (
        <div className="comic-reader-placeholder">
          Loading page {page + 1}...
        </div>
      )}
      <div className="comic-reader-nav">
        <button className="btn btn-secondary" onClick={prev} disabled={page === 0}>
          <FiChevronLeft size={16} /> Previous
        </button>
        <span>{page + 1} / {total}</span>
        <button className="btn btn-secondary" onClick={next} disabled={page === total - 1}>
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
