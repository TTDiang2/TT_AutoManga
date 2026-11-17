import { useState, useEffect, useMemo } from 'react';
import { FiX, FiImage, FiUpload, FiFolder } from 'react-icons/fi';
import { useTranslation } from '../../hooks/useTranslation';
import { useComposerStore } from '../../store/composerStore';

interface ImagePickerProps {
  onSelect: (src: string) => void;
  onClose: () => void;
}

interface PanelImage {
  id: string;
  src: string;
  name?: string;
}

interface ArchiveImage {
  id: string;
  name: string;
  path: string;
  folder_id: string | null;
  created_at: string;
}

interface ArchiveFolder {
  id: string;
  name: string;
  parent_id: string | null;
  created_at: string;
}

type ImageSource = 'panels' | 'archive';

export function ImagePicker({ onSelect, onClose }: ImagePickerProps) {
  const { t } = useTranslation();
  const composerPages = useComposerStore(s => s.pages);
  const projectId = useComposerStore(s => s.projectId);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');

  // Source tab
  const [source, setSource] = useState<ImageSource>('panels');

  // Panels source (Composer page images)
  const panelsLoading = false; // panel images are derived, never async

  // Archive source
  const [archiveFolders, setArchiveFolders] = useState<ArchiveFolder[]>([]);
  const [archiveImages, setArchiveImages] = useState<ArchiveImage[]>([]);
  const [archiveFolder, setArchiveFolder] = useState<string | null>(null);
  const [archiveLoading, setArchiveLoading] = useState(false);

  // Panel images are a pure derivation of the composer pages
  const panelImages = useMemo<PanelImage[]>(() => {
    const imgs: PanelImage[] = [];
    composerPages.forEach(page => {
      page.elements.forEach(el => {
        if (el.type === 'image' && el.src) {
          imgs.push({ id: el.id, src: el.src, name: el.src.split('/').pop()?.substring(0, 20) });
        }
      });
    });
    return imgs;
  }, [composerPages]);

  // Loading starts the moment the archive tab opens; adjust during render
  // (react.dev pattern) so the effect below only performs the fetches.
  const [prevSource, setPrevSource] = useState(source);
  if (prevSource !== source) {
    setPrevSource(source);
    setArchiveLoading(source === 'archive');
  }

  // Load archive folders + images
  useEffect(() => {
    if (source !== 'archive') return;
    Promise.all([
      fetch('/api/archive/folders'),
      fetch(`/api/archive/images${archiveFolder ? `?folder_id=${archiveFolder}` : ''}`),
    ])
      .then(([foldersRes, imagesRes]) =>
        Promise.all([foldersRes.json(), imagesRes.json()])
      )
      .then(([folders, images]) => {
        setArchiveFolders(Array.isArray(folders) ? folders : []);
        setArchiveImages(Array.isArray(images) ? images : []);
      })
      .catch(() => {
        setArchiveFolders([]);
        setArchiveImages([]);
      })
      .finally(() => setArchiveLoading(false));
  }, [source, archiveFolder]);

  // Upload to the asset store and reference it by URL: a data URL would be
  // stored in the page, re-sent on every autosave and kept in undo history.
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const input = e.target;
    const file = input.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadError('');
    try {
      const form = new FormData();
      form.append('file', file);
      form.append('kind', 'upload');
      if (projectId) form.append('project_id', projectId);
      const res = await fetch('/api/assets/file', { method: 'POST', body: form });
      const data = res.ok ? await res.json().catch(() => null) : null;
      if (!data?.url) throw new Error(res.ok ? 'no url in response' : `HTTP ${res.status}`);
      onSelect(data.url);
    } catch (err) {
      console.error('image upload failed:', err);
      setUploadError(`Upload failed${err instanceof Error ? ` (${err.message})` : ''}`);
    } finally {
      setUploading(false);
      input.value = '';
    }
  };

  const getArchiveImageSrc = (img: ArchiveImage) => `/api/archive/images/${img.id}/serve`;

  const renderImageGrid = (imgs: PanelImage[] | ArchiveImage[], isArchive: boolean) => {
    if (archiveLoading || panelsLoading) {
      return (
        <div className="composer-image-picker-empty">
          <span>Loading...</span>
        </div>
      );
    }
    if (imgs.length === 0) {
      const noImagesMsg = isArchive
        ? (t.composer.noArchiveImages || t.composer.noImages)
        : t.composer.noImages;
      const noImagesDesc = isArchive
        ? (t.composer.noArchiveImagesDesc || t.composer.noImagesDesc)
        : t.composer.noImagesDesc;
      return (
        <div className="composer-image-picker-empty">
          <FiImage size={28} style={{ opacity: 0.3 }} />
          <p>{noImagesMsg}</p>
          <span>{noImagesDesc}</span>
        </div>
      );
    }
    return (
      <>
        {imgs.map(img => {
          const src = isArchive ? getArchiveImageSrc(img as ArchiveImage) : (img as PanelImage).src;
          const name = isArchive ? (img as ArchiveImage).name : (img as PanelImage).name;
          return (
            <div
              key={img.id}
              className="composer-image-picker-item"
              onClick={() => onSelect(src)}
              title={name || 'Image'}
            >
              <img src={src} alt={name || ''} />
            </div>
          );
        })}
      </>
    );
  };

  return (
    <div className="composer-image-picker-overlay" onClick={onClose}>
      <div className="composer-image-picker" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="composer-image-picker-header">
          <h3>{t.composer.selectImage}</h3>
          <button className="composer-tool-btn" onClick={onClose} title="Close">
            <FiX size={16} />
          </button>
        </div>

        {/* Source tabs */}
        <div className="composer-image-picker-source-tabs">
          <button
            className={`composer-source-tab ${source === 'panels' ? 'active' : ''}`}
            onClick={() => setSource('panels')}
          >
            {t.composer.fromPanels || 'Panels'}
          </button>
          <button
            className={`composer-source-tab ${source === 'archive' ? 'active' : ''}`}
            onClick={() => setSource('archive')}
          >
            {t.composer.fromArchive || 'Archive'}
          </button>
        </div>

        {/* Archive folder selector */}
        {source === 'archive' && (
          <div className="composer-image-picker-folder-row">
            <FiFolder size={14} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
            <select
              className="composer-folder-select"
              value={archiveFolder ?? ''}
              onChange={e => setArchiveFolder(e.target.value || null)}
            >
              <option value="">{t.composer.allImages || 'All Images'}</option>
              {archiveFolders.map(f => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Image grid */}
        <div className="composer-image-picker-grid">
          {source === 'panels'
            ? renderImageGrid(panelImages, false)
            : renderImageGrid(archiveImages, true)}
        </div>

        {/* Footer */}
        <div className="composer-image-picker-footer">
          <label className="composer-upload-label">
            <FiUpload size={14} />
            {uploading ? 'Uploading…' : t.composer.uploadFile}
            <input type="file" accept="image/*" onChange={handleFileUpload} disabled={uploading} />
          </label>
          {uploadError && (
            <span style={{ fontSize: 12, color: 'var(--error)', marginLeft: 8 }}>
              {uploadError}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
