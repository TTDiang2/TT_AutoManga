import { useCallback, useEffect, useState } from 'react';
import {
  FiArrowDown, FiArrowUp, FiDownload, FiEdit2, FiEye, FiGrid, FiLayers, FiMove,
  FiPlus, FiStar, FiTrash2, FiX, FiZap, FiChevronLeft,
} from 'react-icons/fi';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import type { DragEndEvent } from '@dnd-kit/core';
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { fill, useTranslation } from '../../hooks/useTranslation';
import { useTips } from '../../hooks/useTips';
import type { Project } from '../../types';
import { CollectionExportDialog } from './CollectionExportDialog';
import { MatureCover } from './MatureCover';
import { addEpisodes, episodeTitle, moveItem } from './collectionUtils';
import type { Collection, CollectionEpisode } from './collectionUtils';
import './collections.css';

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, init && init.body
    ? { ...init, headers: { 'Content-Type': 'application/json', ...(init.headers || {}) } }
    : init);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
  return data as T;
}

interface Toast { text: string; error?: boolean }

interface EpisodeActions {
  onView: (projectId: string) => void;
  onEdit: (projectId: string) => void;
  onExport: (projectId: string) => void;
  exportingId: string | null;
}

/** Showcase "Collections": series of projects (episodes), reorder, export. */
export function CollectionsView({ projects, openId, onOpen, onView, onEdit, onExport, exportingId }: EpisodeActions & {
  projects: Project[];
  /** the open collection (kept by the Showcase across the reader) */
  openId: string | null;
  onOpen: (id: string | null) => void;
}) {
  const { t } = useTranslation();
  const tip = useTips().showcase;
  const [collections, setCollections] = useState<Collection[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [toast, setToast] = useState<Toast | null>(null);
  const [nameModal, setNameModal] = useState<{ mode: 'new' | 'edit'; name: string; description: string } | null>(null);
  const [picker, setPicker] = useState<string[] | null>(null);
  const [exporting, setExporting] = useState<Collection | null>(null);

  const showError = useCallback((e: unknown) => {
    setToast({ text: fill(t.showcase.requestFailed, { error: e instanceof Error ? e.message : String(e) }), error: true });
  }, [t]);

  const reload = useCallback(async () => {
    try {
      const data = await api<{ collections: Collection[] }>('/api/collections');
      setCollections(data.collections || []);
    } catch (e) {
      showError(e);
    } finally {
      setLoaded(true);
    }
  }, [showError]);

  // the projects list changes on delete/create in the Comics view
  const projectKey = projects.map(p => p.id).join(',');
  useEffect(() => { void reload(); }, [reload, projectKey]);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 5000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const open = collections.find(c => c.id === openId) || null;

  const replace = (col: Collection) =>
    setCollections(list => list.map(c => (c.id === col.id ? col : c)));

  const patch = async (id: string, body: Record<string, unknown>) => {
    try {
      const data = await api<{ collection: Collection }>(`/api/collections/${id}`, {
        method: 'PATCH', body: JSON.stringify(body),
      });
      replace(data.collection);
    } catch (e) {
      showError(e);
      void reload();
    }
  };

  const reorder = (col: Collection, ids: string[]) => {
    // optimistic: show the new order right away, the PATCH confirms it
    const byId = new Map(col.episodes.map(e => [e.id, e]));
    replace({ ...col, projectIds: ids, episodes: ids.map(i => byId.get(i)).filter((e): e is CollectionEpisode => !!e) });
    void patch(col.id, { projectIds: ids });
  };

  const episodeIds = (col: Collection) => col.episodes.map(e => e.id);

  const handleAutoGroup = async () => {
    try {
      const r = await api<{ created: unknown[]; updated: unknown[]; skipped: unknown[]; collections: Collection[] }>(
        '/api/collections/auto-group', { method: 'POST' });
      setCollections(r.collections || []);
      const nothing = r.created.length === 0 && r.updated.length === 0;
      setToast({
        text: nothing && r.skipped.length === 0
          ? t.showcase.autoGroupNone
          : fill(t.showcase.autoGroupResult, {
            created: r.created.length, updated: r.updated.length, skipped: r.skipped.length,
          }),
      });
    } catch (e) {
      showError(e);
    }
  };

  const saveNameModal = async () => {
    if (!nameModal || !nameModal.name.trim()) return;
    try {
      if (nameModal.mode === 'new') {
        const data = await api<{ collection: Collection }>('/api/collections', {
          method: 'POST',
          body: JSON.stringify({ name: nameModal.name, description: nameModal.description }),
        });
        setCollections(list => [...list, data.collection]);
        onOpen(data.collection.id);
      } else if (open) {
        await patch(open.id, { name: nameModal.name, description: nameModal.description });
      }
      setNameModal(null);
    } catch (e) {
      showError(e);
    }
  };

  const handleDelete = async (col: Collection) => {
    if (!confirm(fill(t.showcase.confirmDeleteCollection, { name: col.name }))) return;
    try {
      await api(`/api/collections/${col.id}`, { method: 'DELETE' });
      setCollections(list => list.filter(c => c.id !== col.id));
      onOpen(null);
    } catch (e) {
      showError(e);
    }
  };

  const toastEl = toast && (
    <div className={`collection-toast${toast.error ? ' error' : ''}`} role="status">
      <span>{toast.text}</span>
      <button className="btn btn-ghost btn-sm" onClick={() => setToast(null)} aria-label={tip.dismiss} data-tip={tip.dismiss}><FiX size={14} /></button>
    </div>
  );

  const nameModalEl = nameModal && (
    <div className="modal-overlay" onClick={() => setNameModal(null)}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <h3>{nameModal.mode === 'new' ? t.showcase.newCollection : t.showcase.editCollection}</h3>
        <input
          className="input mt-md"
          placeholder={t.showcase.collectionName}
          value={nameModal.name}
          onChange={e => setNameModal({ ...nameModal, name: e.target.value })}
          onKeyDown={e => { if (e.key === 'Enter') void saveNameModal(); }}
          data-tip={tip.collectionName}
          autoFocus
        />
        <textarea
          className="input textarea mt-sm"
          rows={2}
          placeholder={t.showcase.collectionDescription}
          value={nameModal.description}
          onChange={e => setNameModal({ ...nameModal, description: e.target.value })}
          data-tip={tip.collectionDescription}
        />
        <div className="flex gap-sm mt-lg justify-end">
          <button className="btn btn-secondary" onClick={() => setNameModal(null)}>{t.showcase.cancel}</button>
          <button className="btn btn-primary" onClick={saveNameModal} disabled={!nameModal.name.trim()} data-tip={tip.saveCollection}>
            {nameModal.mode === 'new' ? t.showcase.create : t.showcase.save}
          </button>
        </div>
      </div>
    </div>
  );

  if (open) {
    const available = projects.filter(p => !open.projectIds.includes(p.id));
    return (
      <div className="collection-detail">
        <div className="collection-detail-head">
          <button className="btn btn-secondary btn-sm" onClick={() => onOpen(null)} data-tip={tip.allCollections}>
            <FiChevronLeft size={14} /> {t.showcase.allCollections}
          </button>
          <div className="collection-detail-title">
            <h3>{open.name}</h3>
            <p className="text-sm text-secondary">
              {open.episodes.length === 1 ? t.showcase.episodeCountOne
                : fill(t.showcase.episodeCount, { n: open.episodes.length })}
              {' • '}{fill(t.showcase.pageCount, { n: open.pages })}
              {open.missing.length > 0 && ` • ${fill(t.showcase.missingEpisodes, { n: open.missing.length })}`}
            </p>
            {open.description && <p className="text-sm text-muted mt-sm">{open.description}</p>}
          </div>
          <div className="flex gap-sm">
            <button className="btn btn-secondary btn-sm" onClick={() => setPicker([])} data-tip={tip.addEpisodes}>
              <FiPlus size={14} /> {t.showcase.addEpisodes}
            </button>
            <button className="btn btn-secondary btn-sm" data-tip={tip.editCollection}
              onClick={() => setNameModal({ mode: 'edit', name: open.name, description: open.description || '' })}>
              <FiEdit2 size={14} /> {t.showcase.editCollection}
            </button>
            <button className="btn btn-primary btn-sm" onClick={() => setExporting(open)} data-tip={tip.exportCollection}
              disabled={open.episodes.every(e => e.pages === 0)}>
              <FiDownload size={14} /> {t.showcase.exportCollection}
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => handleDelete(open)} aria-label={t.showcase.deleteCollection} data-tip={tip.deleteCollection}>
              <FiTrash2 size={14} />
            </button>
          </div>
        </div>

        {open.episodes.length === 0 ? (
          <div className="empty-state"><FiLayers size={40} /><p>{t.showcase.noEpisodes}</p></div>
        ) : (
          <EpisodeList
            collection={open}
            onReorder={ids => reorder(open, ids)}
            onRemove={id => patch(open.id, { projectIds: episodeIds(open).filter(i => i !== id) })}
            onSetCover={ep => patch(open.id, { cover: { projectId: ep.id, pageId: ep.firstPageId } })}
            onView={onView}
            onEdit={onEdit}
            onExport={onExport}
            exportingId={exportingId}
          />
        )}

        {picker && (
          <div className="modal-overlay" onClick={() => setPicker(null)}>
            <div className="modal-content collection-picker" onClick={e => e.stopPropagation()}>
              <h3>{t.showcase.pickProjects}</h3>
              {available.length === 0 ? (
                <p className="text-sm text-secondary mt-md">{t.showcase.noMoreProjects}</p>
              ) : (
                <div className="collection-picker-list mt-md">
                  {available.map(p => (
                    <label key={p.id} className="collection-picker-item" data-tip={tip.pickProject}>
                      <input
                        type="checkbox"
                        checked={picker.includes(p.id)}
                        onChange={e => setPicker(e.target.checked
                          ? [...picker, p.id] : picker.filter(i => i !== p.id))}
                      />
                      <span className="collection-picker-name">{p.name}</span>
                      <span className="text-sm text-muted">
                        {fill(t.showcase.pageCount, { n: p.composerPages?.length || 0 })}
                      </span>
                    </label>
                  ))}
                </div>
              )}
              <div className="flex gap-sm mt-lg justify-end">
                <button className="btn btn-secondary" onClick={() => setPicker(null)}>{t.showcase.cancel}</button>
                <button className="btn btn-primary" disabled={picker.length === 0} data-tip={tip.addPicked}
                  onClick={() => {
                    void patch(open.id, { projectIds: addEpisodes(episodeIds(open), picker) });
                    setPicker(null);
                  }}>
                  {t.showcase.add}
                </button>
              </div>
            </div>
          </div>
        )}
        {exporting && <CollectionExportDialog collection={exporting} onClose={() => setExporting(null)} />}
        {nameModalEl}
        {toastEl}
      </div>
    );
  }

  return (
    <div className="collections-view">
      <div className="flex gap-sm mb-lg">
        <button className="btn btn-secondary" onClick={() => setNameModal({ mode: 'new', name: '', description: '' })} data-tip={tip.newCollection}>
          <FiPlus size={14} /> {t.showcase.newCollection}
        </button>
        <button className="btn btn-secondary" onClick={handleAutoGroup} data-tip={tip.autoGroup}>
          <FiZap size={14} /> {t.showcase.autoGroup}
        </button>
      </div>

      {loaded && collections.length === 0 ? (
        <div className="empty-state">
          <FiLayers size={48} />
          <h3>{t.showcase.noCollections}</h3>
          <p>{t.showcase.noCollectionsDesc}</p>
        </div>
      ) : (
        <div className="collections-grid">
          {collections.map(col => (
            <button key={col.id} className="collection-card card" onClick={() => onOpen(col.id)} data-tip={tip.openCollection}>
              <div className="collection-strip">
                {col.episodes.length === 0 ? (
                  <div className="cover-placeholder"><FiGrid size={24} /></div>
                ) : (
                  col.episodes.slice(0, 4).map(ep => (
                    <div key={ep.id} className="collection-strip-cell">
                      <MatureCover id={ep.id} src={ep.cover} alt={ep.name} mature={ep.contentRating === 'mature'}
                        interactive={false} placeholder={<div className="cover-placeholder"><FiGrid size={16} /></div>} />
                    </div>
                  ))
                )}
              </div>
              <div className="project-info">
                <h4>
                  {col.name}
                  {col.auto && <span className="badge collection-auto-badge">{t.showcase.auto}</span>}
                  {col.mature && <span className="mature-badge">{t.showcase.matureBadge}</span>}
                </h4>
                <p className="text-sm text-muted">
                  {col.episodes.length === 1 ? t.showcase.episodeCountOne
                    : fill(t.showcase.episodeCount, { n: col.episodes.length })}
                  {' • '}{fill(t.showcase.pageCount, { n: col.pages })}
                </p>
              </div>
            </button>
          ))}
        </div>
      )}
      {nameModalEl}
      {toastEl}
    </div>
  );
}

function EpisodeList({ collection, onReorder, onRemove, onSetCover, ...actions }: EpisodeActions & {
  collection: Collection;
  onReorder: (ids: string[]) => void;
  onRemove: (id: string) => void;
  onSetCover: (ep: CollectionEpisode) => void;
}) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const ids = collection.episodes.map(e => e.id);

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    onReorder(moveItem(ids, ids.indexOf(String(active.id)), ids.indexOf(String(over.id))));
  };

  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
      <SortableContext items={ids} strategy={verticalListSortingStrategy}>
        <ol className="episode-list">
          {collection.episodes.map((ep, i) => (
            <EpisodeRow
              key={ep.id}
              ep={ep}
              index={i}
              count={ids.length}
              collectionName={collection.name}
              isCover={collection.cover?.projectId === ep.id}
              onMove={to => onReorder(moveItem(ids, i, to))}
              onRemove={() => onRemove(ep.id)}
              onSetCover={() => onSetCover(ep)}
              {...actions}
            />
          ))}
        </ol>
      </SortableContext>
    </DndContext>
  );
}

function EpisodeRow({ ep, index, count, collectionName, isCover, onMove, onRemove, onSetCover,
  onView, onEdit, onExport, exportingId }: EpisodeActions & {
  ep: CollectionEpisode;
  index: number;
  count: number;
  collectionName: string;
  isCover: boolean;
  onMove: (to: number) => void;
  onRemove: () => void;
  onSetCover: () => void;
}) {
  const { t } = useTranslation();
  const tip = useTips().showcase;
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: ep.id });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };
  return (
    <li ref={setNodeRef} style={style} className="episode-row card">
      <span className="drag-handle episode-handle" data-tip={tip.dragEpisode} {...attributes} {...listeners}>
        <FiMove size={14} />
      </span>
      <span className="episode-index">{index + 1}</span>
      <div className="episode-thumb">
        <MatureCover id={ep.id} src={ep.cover} alt={ep.name} mature={ep.contentRating === 'mature'}
          placeholder={<div className="cover-placeholder"><FiGrid size={14} /></div>} />
      </div>
      <div className="episode-info">
        <div className="episode-name">
          {episodeTitle(collectionName, ep.name)}
          {ep.contentRating === 'mature' && <span className="mature-badge">{t.showcase.matureBadge}</span>}
        </div>
        <div className="text-sm text-muted">
          {fill(t.showcase.pageCount, { n: ep.pages })}
          {isCover && <span className="badge collection-auto-badge">{t.showcase.isCover}</span>}
        </div>
      </div>
      <div className="episode-actions">
        <button className="btn btn-ghost btn-sm" onClick={() => onMove(index - 1)} disabled={index === 0} aria-label={t.showcase.moveUp} data-tip={tip.moveUp}>
          <FiArrowUp size={14} />
        </button>
        <button className="btn btn-ghost btn-sm" onClick={() => onMove(index + 1)} disabled={index === count - 1} aria-label={t.showcase.moveDown} data-tip={tip.moveDown}>
          <FiArrowDown size={14} />
        </button>
        <button className="btn btn-ghost btn-sm" onClick={onSetCover} disabled={isCover || ep.pages === 0} aria-label={t.showcase.setCover} data-tip={tip.setCover}>
          <FiStar size={14} />
        </button>
        <button className="btn btn-secondary btn-sm" onClick={() => onView(ep.id)} aria-label={t.showcase.view} data-tip={tip.viewEpisode}>
          <FiEye size={14} />
        </button>
        <button className="btn btn-secondary btn-sm" onClick={() => onEdit(ep.id)} aria-label={t.showcase.edit} data-tip={tip.editEpisode}>
          <FiEdit2 size={14} />
        </button>
        <button className="btn btn-secondary btn-sm" onClick={() => onExport(ep.id)}
          disabled={exportingId === ep.id} aria-label={t.showcase.exportEpisode} data-tip={tip.exportEpisode}>
          <FiDownload size={14} />
        </button>
        <button className="btn btn-ghost btn-sm" onClick={onRemove} aria-label={t.showcase.removeEpisode} data-tip={tip.removeEpisode}>
          <FiX size={14} />
        </button>
      </div>
    </li>
  );
}
