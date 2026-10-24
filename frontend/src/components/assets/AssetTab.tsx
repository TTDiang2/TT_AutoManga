import { useState, useEffect, useMemo } from 'react';
import { FiUpload, FiRefreshCw, FiImage, FiCheck, FiX, FiAlertCircle, FiZap, FiTag, FiArchive, FiDownload, FiEdit2, FiLayers } from 'react-icons/fi';
import { useProjectStore } from '../../store/projectStore';
import { useTranslation } from '../../hooks/useTranslation';
import type { TranslationKeys } from '../../i18n';
import type { Panel } from '../../types';

type ImageStatus = 'empty' | 'pending' | 'ready' | 'error';

// shapes returned by GET /api/archive/images and /api/archive/folders
interface ArchiveImageMeta {
  id: string;
  name: string;
  path: string;
  folder_id: string | null;
  created_at: string;
  thumbnail_path?: string | null;
}

interface ArchiveFolderMeta {
  id: string;
  name: string;
  parent_id: string | null;
  created_at: string;
  sort_order: number;
  group?: string | null;
}

/**
 * Detects the natural aspect ratio of an image (data URL or remote URL) and
 * returns a CSS `aspect-ratio` value (e.g. `"768 / 1216"`). While the image
 * has not been loaded yet (or when no src is provided), `fallback` is used so
 * the placeholder box keeps a sensible default shape.
 */
function useImageAspectRatio(src: string | undefined, fallback: string = '2 / 3'): string {
  const [ratio, setRatio] = useState<string>(fallback);

  useEffect(() => {
    if (!src) return; // No image to measure - render path below returns fallback.
    const img = new Image();
    img.onload = () => {
      if (img.naturalWidth > 0 && img.naturalHeight > 0) {
        setRatio(`${img.naturalWidth} / ${img.naturalHeight}`);
      }
    };
    img.src = src;
  }, [src]);

  // Derive the no-src case during render instead of setState-in-effect.
  return src ? ratio : fallback;
}

interface PanelSlotProps {
  panelId: string;
  index: number;
  image?: string;
  status: ImageStatus;
  isGenerating: boolean;
  error?: string;
  /** CSS aspect-ratio used for the placeholder when no image is loaded yet. */
  defaultAspectRatio: string;
  onUpload: (panelId: string, file: File) => void;
  onGenerate: (panelId: string) => void;
  onArchive?: (panelId: string) => void;
  t: TranslationKeys;
}

function PanelSlot({ panelId, index, image, status, isGenerating, error, defaultAspectRatio, onUpload, onGenerate, onArchive, t }: PanelSlotProps) {
  const [isUploading, setIsUploading] = useState(false);
  // Snap to the image's real ratio once it loads; fall back to the configured
  // default (matches the current SwarmUI width/height) for empty slots.
  const aspectRatio = useImageAspectRatio(image, defaultAspectRatio);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setIsUploading(true);
      try {
        onUpload(panelId, file);
      } catch {
        // onUpload reports its own errors via the panel status line
      } finally {
        setIsUploading(false);
      }
    }
  };



  return (
    <div className="panel-slot card">
      <div className="slot-header">
        <span className="badge">Panel {index + 1}</span>
        <span className={`status-badge ${isGenerating ? 'pending' : status}`}>
          {isGenerating && <><span className="spinner-dot" /> {t.assets.generating}</>}
          {!isGenerating && status === 'empty' && t.assets.empty}
          {!isGenerating && status === 'ready' && <><FiCheck size={12} /> {t.assets.ready}</>}
          {!isGenerating && status === 'error' && <><FiX size={12} /> {t.assets.error}</>}
        </span>
      </div>

      <div className="slot-preview" style={{ aspectRatio }}>
        {image ? (
          <img src={image} alt={`Panel ${index + 1}`} />
        ) : (
          <div className="slot-placeholder">
            <FiImage size={32} />
            <span>{t.assets.empty}</span>
          </div>
        )}
      </div>

      {error && (
        <div className="slot-error">
          <FiAlertCircle size={14} /> {error}
        </div>
      )}

      <div className="slot-actions">
        <label className="btn btn-secondary">
          <FiUpload size={14} />
          {t.assets.upload}
          <input
            type="file"
            accept="image/*"
            onChange={handleFileChange}
            disabled={isUploading}
            hidden
          />
        </label>
        <button
          className="btn btn-primary"
          onClick={() => onGenerate(panelId)}
          disabled={isGenerating}
        >
          {isGenerating ? <span className="loading-spinner" /> : <FiRefreshCw size={14} />}
          {t.assets.generate}
        </button>
        {image && onArchive && (
          <button
            className="btn btn-secondary"
            onClick={() => onArchive(panelId)}
            title="Archive image"
          >
            <FiArchive size={14} />
          </button>
        )}
      </div>
    </div>
  );
}

interface ArchiveItemProps {
  img: ArchiveImageMeta;
  isSelected: boolean;
  isMoveMenuOpen: boolean;
  folders: ArchiveFolderMeta[];
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onToggleMoveMenu: (id: string) => void;
  onMove: (imageId: string, folderId: string | null) => void;
  t: TranslationKeys;
}

/**
 * One archive thumbnail. Extracted into its own component so each image can
 * measure its natural aspect ratio via useImageAspectRatio without re-renders
 * cascading across the whole list.
 */
function ArchiveItem({ img, isSelected, isMoveMenuOpen, folders, onSelect, onDelete, onToggleMoveMenu, onMove, t }: ArchiveItemProps) {
  const src = `/api/archive/images/${img.id}/serve`;
  const aspectRatio = useImageAspectRatio(src, '2 / 3');
  return (
    <div
      className={`archive-item card ${isSelected ? 'selected' : ''}`}
      onClick={() => onSelect(img.id)}
    >
      <div className="archive-item-preview" style={{ aspectRatio }}>
        <img src={src} alt={img.name} />
      </div>
      <div className="archive-item-info">
        <span className="archive-item-name">{img.name}</span>
      </div>
      <button
        className="btn btn-ghost archive-item-delete"
        onClick={(e) => { e.stopPropagation(); onDelete(img.id); }}
      >
        Delete
      </button>
      <div className="archive-item-move-wrapper">
        <button
          className="btn btn-ghost archive-item-move-btn"
          onClick={(e) => { e.stopPropagation(); onToggleMoveMenu(img.id); }}
        >
          {t.assets.moveToFolder}
        </button>
        {isMoveMenuOpen && (
          <div className="archive-move-menu" onClick={e => e.stopPropagation()}>
            <button
              className="archive-move-option"
              style={{ color: img.folder_id === null ? 'var(--accent-primary)' : 'inherit', fontWeight: img.folder_id === null ? 600 : 400 }}
              onClick={() => onMove(img.id, null)}
            >
              {t.assets.moveToAllImages}
            </button>
            {folders.map(folder => (
              <button
                key={folder.id}
                className="archive-move-option"
                style={{ color: img.folder_id === folder.id ? 'var(--accent-primary)' : 'inherit', fontWeight: img.folder_id === folder.id ? 600 : 400 }}
                onClick={() => onMove(img.id, folder.id)}
              >
                {folder.name}
              </button>
            ))}
            {folders.length === 0 && (
              <div className="archive-move-empty">No folders yet</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export function AssetTab() {
  const { panels, updatePanelImage, settings, currentProject, promptMode, setPromptMode, generatingPanels, startGenerating, stopGenerating } = useProjectStore();
  const { t } = useTranslation();
  const [panelStatuses, setPanelStatuses] = useState<Record<string, ImageStatus>>({});
  const [panelErrors, setPanelErrors] = useState<Record<string, string>>({});
  const [swarmUIConnected, setSwarmUIConnected] = useState<boolean | null>(null);
  const [viewMode, setViewMode] = useState<'generated' | 'archive'>('generated');
  const [archiveImages, setArchiveImages] = useState<ArchiveImageMeta[]>([]);
  const [archiveFolders, setArchiveFolders] = useState<ArchiveFolderMeta[]>([]);
  const [folderSortBy, setFolderSortBy] = useState<'order' | 'name' | 'created'>('order');
  const [currentFolder, setCurrentFolder] = useState<string | null>(null);
  const [activeGroup, setActiveGroup] = useState<string | null>(null);
  const [selectedArchiveImage, setSelectedArchiveImage] = useState<string | null>(null);
  const [movingImageId, setMovingImageId] = useState<string | null>(null);

  // Default placeholder ratio follows the configured SwarmUI output dimensions,
  // so an empty slot matches whatever the next "Generate" will produce.
  const defaultAspectRatio = useMemo(() => {
    const w = settings.swarmui.currentWidth;
    const h = settings.swarmui.currentHeight;
    return w && h ? `${w} / ${h}` : '2 / 3';
  }, [settings.swarmui.currentWidth, settings.swarmui.currentHeight]);

  useEffect(() => {
    checkSwarmUIConnection();
    if (viewMode === 'archive') {
      loadArchive();
    }
  }, [viewMode, currentFolder]);

  useEffect(() => {
    if (!selectedArchiveImage) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSelectedArchiveImage(null);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [selectedArchiveImage]);

  const loadArchive = async () => {
    try {
      const [imagesRes, foldersRes] = await Promise.all([
        fetch(`/api/archive/images${currentFolder ? `?folder_id=${currentFolder}` : ''}`),
        fetch(`/api/archive/folders?sort_by=${folderSortBy === 'order' ? '' : folderSortBy}`)
      ]);
      const images = await imagesRes.json();
      const folders = await foldersRes.json();
      setArchiveImages(Array.isArray(images) ? images : []);
      setArchiveFolders(Array.isArray(folders) ? folders : []);
    } catch (err) {
      console.error('Failed to load archive:', err);
      setArchiveImages([]);
      setArchiveFolders([]);
    }
  };

  const archiveImage = async (panelId: string) => {
    const panel = panels.find(p => p.id === panelId);
    if (!panel?.image) return;
    try {
      const response = await fetch('/api/archive/images', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_data: panel.image,
          name: `Panel ${panels.indexOf(panel) + 1}`,
          folder_id: currentFolder
        })
      });
      const data = await response.json();
      if (data.success) {
        loadArchive();
      }
    } catch (err) {
      console.error('Failed to archive image:', err);
    }
  };

  const deleteArchiveImage = async (imageId: string) => {
    if (!confirm('Delete this image from archive?')) return;
    try {
      await fetch(`/api/archive/images/${imageId}`, { method: 'DELETE' });
      loadArchive();
    } catch (err) {
      console.error('Failed to delete archive image:', err);
    }
  };

  const moveImage = async (imageId: string, folderId: string | null) => {
    try {
      await fetch(`/api/archive/images/${imageId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder_id: folderId }),
      });
      setMovingImageId(null);
      loadArchive();
    } catch (err) {
      console.error('Failed to move image:', err);
    }
  };

  const createFolder = async () => {
    const name = prompt('Folder name:');
    if (!name) return;
    try {
      await fetch('/api/archive/folders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: `folder_${Date.now()}`,
          name,
          parent_id: currentFolder,
          created_at: new Date().toISOString(),
          sort_order: 0,
        })
      });
      loadArchive();
    } catch (err) {
      console.error('Failed to create folder:', err);
    }
  };

  const deleteFolder = async (folderId: string) => {
    if (!confirm('Delete this folder and all images in it?')) return;
    try {
      await fetch(`/api/archive/folders/${folderId}`, { method: 'DELETE' });
      if (currentFolder === folderId) setCurrentFolder(null);
      loadArchive();
    } catch (err) {
      console.error('Failed to delete folder:', err);
    }
  };

  const downloadFolder = async (folderId: string) => {
    const a = document.createElement('a');
    a.href = `/api/archive/folders/${folderId}/download`;
    a.download = '';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const selectArchiveImage = (imageId: string) => {
    setSelectedArchiveImage(imageId === selectedArchiveImage ? null : imageId);
  };

  const checkSwarmUIConnection = async () => {
    try {
      const response = await fetch('/api/assets/swarmui/test');
      const data = await response.json();
      setSwarmUIConnected(data.connected);
    } catch {
      setSwarmUIConnected(false);
    }
  };

  const getPromptForPanel = (panel: Panel): string => {
    if (promptMode === 'tags' && panel.prompt.tags && panel.prompt.tags.length > 0) {
      return panel.prompt.tags.join(', ');
    }
    return panel.prompt.turbo || panel.scene;
  };

  const handleUpload = async (panelId: string, file: File) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const result = e.target?.result as string;
      updatePanelImage(panelId, result);
      setPanelStatuses(prev => ({ ...prev, [panelId]: 'ready' }));
      setPanelErrors(prev => ({ ...prev, [panelId]: '' }));
    };
    reader.onerror = () => {
      setPanelStatuses(prev => ({ ...prev, [panelId]: 'error' }));
      setPanelErrors(prev => ({ ...prev, [panelId]: t.assets.uploadFailed }));
    };
    reader.readAsDataURL(file);
  };

  const handleGenerate = async (panelId: string) => {
    const panel = panels.find(p => p.id === panelId);
    if (!panel) return;
    if (generatingPanels.includes(panelId)) return;

    startGenerating(panelId);
    setPanelErrors(prev => ({ ...prev, [panelId]: '' }));

    try {
      const prompt = getPromptForPanel(panel);
      const negPrompt = panel.prompt.negativePrompt || 'low quality, blurry, distorted';
      const seed = panel.prompt.seed;
      console.log('[Generate] negative_prompt:', negPrompt, '| seed:', seed, '| panel.prompt:', panel.prompt);
      
      const removeBG = panel.prompt.removeBG || false;
      const response = await fetch('/api/assets/swarmui/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt,
          negative_prompt: negPrompt,
          seed,
          panel_id: panelId,
          project_id: currentProject?.id || 'default',
          swarmui_address: settings.swarmui.address,
          remove_background: removeBG,
        }),
      });

      const data = await response.json();

      if (data.success && data.image) {
        updatePanelImage(panelId, data.image);
        setPanelStatuses(prev => ({ ...prev, [panelId]: 'ready' }));
      } else {
        setPanelStatuses(prev => ({ ...prev, [panelId]: 'error' }));
        setPanelErrors(prev => ({ ...prev, [panelId]: data.error || 'Generation failed' }));
      }
    } catch (error) {
      console.error('Generation failed:', error);
      setPanelStatuses(prev => ({ ...prev, [panelId]: 'error' }));
      setPanelErrors(prev => ({ ...prev, [panelId]: String(error) }));
    } finally {
      stopGenerating(panelId);
    }
  };

  const handleGenerateAll = async () => {
    const ungenerated = panels.filter(p => !p.image && !generatingPanels.includes(p.id));
    for (const panel of ungenerated) {
      await handleGenerate(panel.id);
    }
  };

  return (
    <div className="asset-tab">
      <div className="asset-header flex items-center justify-between mb-lg">
        <div className="flex items-center gap-md">
          <div className="mode-toggle">
            <button
              className={`mode-btn ${promptMode === 'turbo' ? 'active' : ''}`}
              onClick={() => setPromptMode('turbo')}
            >
              <FiZap size={16} /> {t.prompt.turbo}
            </button>
            <button
              className={`mode-btn ${promptMode === 'tags' ? 'active' : ''}`}
              onClick={() => setPromptMode('tags')}
            >
              <FiTag size={16} /> {t.prompt.sdxl}
            </button>
          </div>
          <div className="view-toggle" style={{ marginLeft: '16px', display: 'flex', gap: '4px', padding: '4px', background: 'var(--bg-tertiary)', borderRadius: '8px' }}>
            <button
              className={`view-btn ${viewMode === 'generated' ? 'active' : ''}`}
              onClick={() => setViewMode('generated')}
              style={{ padding: '6px 12px', borderRadius: '6px', border: 'none', background: viewMode === 'generated' ? 'var(--accent-primary)' : 'transparent', color: viewMode === 'generated' ? 'white' : 'var(--text-secondary)', cursor: 'pointer', fontSize: '13px' }}
            >
              Generated
            </button>
            <button
              className={`view-btn ${viewMode === 'archive' ? 'active' : ''}`}
              onClick={() => setViewMode('archive')}
              style={{ padding: '6px 12px', borderRadius: '6px', border: 'none', background: viewMode === 'archive' ? 'var(--accent-primary)' : 'transparent', color: viewMode === 'archive' ? 'white' : 'var(--text-secondary)', cursor: 'pointer', fontSize: '13px' }}
            >
              Archive
            </button>
          </div>
        </div>
        <div className="flex items-center gap-md">
          {viewMode === 'generated' && panels.some(p => !p.image) && (
            <button
              className="btn btn-primary"
              onClick={handleGenerateAll}
              disabled={generatingPanels.length > 0}
              style={{ whiteSpace: 'nowrap' }}
            >
              {generatingPanels.length > 0 ? <span className="loading-spinner" /> : <FiRefreshCw size={14} />}
              {t.assets.generateAll || 'Generate All'}
            </button>
          )}
          <span className={`connection-status ${swarmUIConnected ? 'connected' : 'disconnected'}`}>
            <span className="status-dot" />
            SwarmUI: {swarmUIConnected === null ? t.assets.checking : swarmUIConnected ? t.assets.connected : t.assets.disconnected}
          </span>
        </div>
      </div>

      {viewMode === 'archive' ? (
        <div className="archive-view" style={{ display: 'flex', gap: '16px', height: 'calc(100vh - 200px)' }}>
          <div className="archive-sidebar" style={{ width: '320px', flexShrink: 0, display: 'flex', flexDirection: 'column', gap: '0' }}>
            <div className="folder-header flex justify-between items-center mb-sm">
              <span style={{ fontSize: '12px', color: 'var(--text-secondary)', textTransform: 'uppercase' }}>Groups</span>
              <div style={{ display: 'flex', gap: '4px' }}>
                <select
                  value={folderSortBy}
                  onChange={(e) => { const v = e.target.value as 'order' | 'name' | 'created'; setFolderSortBy(v); loadArchive(); }}
                  style={{ fontSize: '10px', padding: '2px 4px', borderRadius: '4px', background: 'var(--bg-tertiary)', color: 'var(--text-primary)', border: '1px solid var(--border-default)' }}
                >
                  <option value="order">Default</option>
                  <option value="name">Name</option>
                  <option value="created">Date</option>
                </select>
                <button className="btn btn-ghost" style={{ padding: '2px 6px', fontSize: '11px' }} onClick={createFolder}>+ New</button>
              </div>
            </div>
            <div style={{ flex: 1, overflow: 'auto' }}>
              <div
                className={`group-item ${activeGroup === null ? 'active' : ''}`}
                style={{ padding: '6px 10px', borderRadius: '6px', cursor: 'pointer', background: activeGroup === null ? 'var(--accent-primary)' : 'transparent', color: activeGroup === null ? 'white' : 'inherit', fontSize: '12px', fontWeight: 600 }}
                onClick={() => { setActiveGroup(null); setCurrentFolder(null); }}
              >
                All Folders
              </div>
              {(() => {
                const groups: Record<string, typeof archiveFolders> = {};
                archiveFolders.forEach(f => {
                  const g = f.group || '__ungrouped__';
                  if (!groups[g]) groups[g] = [];
                  groups[g].push(f);
                });
                return Object.entries(groups).sort(([a], [b]) => {
                  if (a === '__ungrouped__') return 1;
                  if (b === '__ungrouped__') return -1;
                  if (folderSortBy === 'name') return a.localeCompare(b);
                  if (folderSortBy === 'created') return 0;
                  return 0;
                }).map(([groupName, folders]) => (
                  <div key={groupName} style={{ marginBottom: '4px' }}>
                    <div
                      className={`group-item ${activeGroup === groupName ? 'active' : ''}`}
                      style={{ padding: '6px 10px', borderRadius: '6px', cursor: 'pointer', background: activeGroup === groupName ? '#5b8def' : 'var(--bg-tertiary)', color: activeGroup === groupName ? 'white' : 'var(--text-secondary)', fontSize: '11px', fontWeight: 500, marginBottom: '2px' }}
                      onClick={() => { setActiveGroup(groupName); setCurrentFolder(null); }}
                    >
                      {groupName === '__ungrouped__' ? 'Ungrouped' : groupName} ({folders.length})
                    </div>
                    {activeGroup === groupName && folders.map(folder => (
                      <div
                        key={folder.id}
                        style={{
                          padding: '0',
                          borderRadius: '6px',
                          cursor: 'pointer',
                          background: currentFolder === folder.id ? 'var(--accent-primary)' : 'transparent',
                          color: currentFolder === folder.id ? 'white' : 'inherit',
                          minWidth: 0,
                          marginLeft: '12px',
                          marginBottom: '2px',
                        }}
                        onClick={() => setCurrentFolder(folder.id)}
                      >
                        <div className="flex justify-between items-center" style={{ padding: '6px 10px', width: '100%' }}>
                          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1, fontSize: '12px' }}>{folder.name}</span>
                          <div style={{ display: 'flex', gap: '1px', alignItems: 'center', flexShrink: 0, marginLeft: '8px' }} onClick={e => e.stopPropagation()}>
                            <button style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', opacity: 0.6, padding: '3px', borderRadius: '3px', display: 'flex', alignItems: 'center' }} onClick={() => { const newName = prompt('Rename folder:', folder.name); if (newName) { fetch(`/api/archive/folders/${folder.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: newName }) }).then(() => loadArchive()); } }} title="Rename"><FiEdit2 size={11} /></button>
                            <button style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', opacity: 0.6, padding: '3px', borderRadius: '3px', display: 'flex', alignItems: 'center' }} onClick={() => { const g = prompt('Group name:', folder.group || ''); fetch(`/api/archive/folders/${folder.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ group: g || null }) }).then(() => loadArchive()); }} title="Group"><FiLayers size={11} /></button>
                            <button style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', opacity: 0.6, padding: '3px', borderRadius: '3px', display: 'flex', alignItems: 'center' }} onClick={() => downloadFolder(folder.id)} title={t.assets.downloadFolder || 'Download'}><FiDownload size={11} /></button>
                            <button style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', opacity: 0.6, padding: '3px', borderRadius: '3px', display: 'flex', alignItems: 'center' }} onClick={() => deleteFolder(folder.id)} title="Delete">×</button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ));
              })()}
            </div>
          </div>
          <div className="archive-content" style={{ flex: 1, overflow: 'auto' }}>
            {archiveImages.length === 0 ? (
              <div className="empty-state">
                <FiImage size={48} />
                <h3>No archived images</h3>
                <p>Generated images can be archived for later use</p>
              </div>
            ) : (
              <div className="archive-grid">
                {archiveImages.map(img => (
                  <ArchiveItem
                    key={img.id}
                    img={img}
                    isSelected={selectedArchiveImage === img.id}
                    isMoveMenuOpen={movingImageId === img.id}
                    folders={archiveFolders}
                    onSelect={selectArchiveImage}
                    onDelete={deleteArchiveImage}
                    onToggleMoveMenu={(id) => setMovingImageId(movingImageId === id ? null : id)}
                    onMove={moveImage}
                    t={t}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      ) : (
        <>
          {panels.length === 0 ? (
            <div className="empty-state">
              <FiImage size={48} />
              <h3>{t.assets.noPanels}</h3>
              <p>{t.assets.noPanelsDesc}</p>
            </div>
          ) : (
            <div className="assets-grid">
        {panels.map((panel, index) => (
          <PanelSlot
            key={panel.id}
            panelId={panel.id}
            index={index}
            image={panel.image}
            status={panelStatuses[panel.id] || (panel.image ? 'ready' : 'empty')}
            isGenerating={generatingPanels.includes(panel.id)}
            defaultAspectRatio={defaultAspectRatio}

            error={panelErrors[panel.id]}
            onUpload={handleUpload}
            onGenerate={handleGenerate}
            onArchive={archiveImage}
            t={t}
          />
        ))}
            </div>
          )}
        </>
      )}

      <style>{`
        .connection-status {
          display: flex;
          align-items: center;
          gap: var(--space-sm);
          font-size: 13px;
          color: var(--text-secondary);
        }
        .status-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: var(--error);
        }
        .connection-status.connected .status-dot {
          background: var(--success);
        }
        .assets-grid {
          display: flex;
          flex-wrap: wrap;
          gap: var(--space-lg);
          align-items: flex-start;
        }
        .panel-slot {
          padding: var(--space-md);
          /* Card shrinks to its preview's ratio-driven width so all previews
             share one height while widths vary per image. */
          width: fit-content;
          min-width: 200px;
        }
        .slot-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: var(--space-md);
        }
        .status-badge {
          display: flex;
          align-items: center;
          gap: 4px;
          font-size: 11px;
          padding: 2px 8px;
          border-radius: var(--radius-sm);
          background: var(--bg-tertiary);
          color: var(--text-secondary);
        }
        .status-badge.ready {
          background: rgba(76, 175, 80, 0.1);
          color: var(--success);
        }
        .status-badge.pending {
          background: rgba(33, 150, 243, 0.1);
          color: var(--info);
        }
        .status-badge.error {
          background: rgba(244, 67, 54, 0.1);
          color: var(--error);
        }
        .slot-preview {
          /* Fixed height + ratio-driven width = uniform-height gallery with
             varying widths. aspect-ratio is applied inline per-image. */
          height: 320px;
          width: auto;
          background: var(--bg-tertiary);
          border-radius: var(--radius-md);
          overflow: hidden;
          margin-bottom: var(--space-md);
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .slot-preview img {
          width: 100%;
          height: 100%;
          object-fit: cover;
        }
        .slot-placeholder {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: var(--space-sm);
          color: var(--text-muted);
        }
        .slot-error {
          display: flex;
          align-items: center;
          gap: var(--space-xs);
          font-size: 12px;
          color: var(--error);
          margin-bottom: var(--space-sm);
        }
        .slot-actions {
          display: flex;
          gap: var(--space-sm);
        }
        .slot-actions .btn {
          flex: 1;
          font-size: 13px;
        }
        /* Archive grid: same uniform-height / varying-width approach. */
        .archive-grid {
          display: flex;
          flex-wrap: wrap;
          gap: 12px;
          align-items: flex-start;
        }
        .archive-item {
          padding: 8px;
          cursor: pointer;
          width: fit-content;
          min-width: 160px;
        }
        .archive-item.selected {
          border-color: var(--accent-primary);
          border-width: 2px;
        }
        .archive-item-preview {
          height: 240px;
          width: auto;
          background: var(--bg-tertiary);
          border-radius: 4px;
          overflow: hidden;
        }
        .archive-item-preview img {
          width: 100%;
          height: 100%;
          object-fit: cover;
          display: block;
        }
        .archive-item-info {
          margin-top: 8px;
        }
        .archive-item-name {
          font-size: 12px;
          color: var(--text-secondary);
          display: block;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .archive-item-delete {
          margin-top: 4px;
          padding: 4px 8px;
          font-size: 11px;
          color: #ef4444;
          width: 100%;
        }
        .archive-item-move-wrapper {
          position: relative;
          margin-top: 4px;
        }
        .archive-item-move-btn {
          padding: 4px 8px;
          font-size: 11px;
          width: 100%;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 4px;
        }
        .archive-move-menu {
          position: absolute;
          bottom: 100%;
          left: 0;
          right: 0;
          max-height: 200px;
          overflow-y: auto;
          background: var(--bg-secondary);
          border: 1px solid var(--border-default);
          border-radius: 6px;
          padding: 4px;
          z-index: 100;
          box-shadow: var(--shadow-elevated);
          margin-bottom: 4px;
        }
        .archive-move-option {
          display: block;
          width: 100%;
          padding: 6px 8px;
          background: none;
          border: none;
          text-align: left;
          cursor: pointer;
          border-radius: 4px;
          font-size: 12px;
        }
        .archive-move-empty {
          padding: 6px 8px;
          font-size: 11px;
          color: var(--text-muted);
        }
        .spinner-dot {
          width: 10px;
          height: 10px;
          border-radius: 50%;
          border: 2px solid currentColor;
          border-top-color: transparent;
          animation: spin 0.8s linear infinite;
          display: inline-block;
        }
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
        .mode-toggle {
          display: flex;
          background: var(--bg-tertiary);
          border-radius: var(--radius-md);
          padding: 4px;
        }
        .mode-btn {
          display: flex;
          align-items: center;
          gap: var(--space-xs);
          padding: var(--space-sm) var(--space-md);
          border: none;
          background: transparent;
          border-radius: var(--radius-sm);
          cursor: pointer;
          font-size: 14px;
          color: var(--text-secondary);
          transition: all var(--transition-default);
        }
        .mode-btn.active {
          background: var(--bg-primary);
          color: var(--text-primary);
          box-shadow: var(--shadow-subtle);
        }
        .image-lightbox {
          position: fixed;
          inset: 0;
          background: rgba(0, 0, 0, 0.85);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1000;
          cursor: zoom-out;
        }
        .image-lightbox img {
          max-width: 90vw;
          max-height: 90vh;
          object-fit: contain;
          border-radius: 8px;
          box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
          cursor: default;
        }
        .image-lightbox-close {
          position: fixed;
          top: 16px;
          right: 20px;
          background: rgba(255, 255, 255, 0.1);
          border: none;
          color: white;
          font-size: 24px;
          cursor: pointer;
          padding: 8px 12px;
          border-radius: 6px;
          line-height: 1;
          z-index: 1001;
        }
        .image-lightbox-close:hover {
          background: rgba(255, 255, 255, 0.2);
        }
      `}</style>
      {selectedArchiveImage && (
        <div className="image-lightbox" onClick={() => setSelectedArchiveImage(null)}>
          <button className="image-lightbox-close" onClick={() => setSelectedArchiveImage(null)}>×</button>
          <img
            src={`/api/archive/images/${selectedArchiveImage}/serve`}
            alt="preview"
            onClick={e => e.stopPropagation()}
          />
        </div>
      )}
    </div>
  );
}
