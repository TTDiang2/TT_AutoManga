import { useEffect, useState } from 'react';
import { FiDownload, FiX } from 'react-icons/fi';
import { fill, useTranslation } from '../../hooks/useTranslation';
import { clampScale, exportPercent } from './collectionUtils';
import type { Collection, CollectionExportJob } from './collectionUtils';

type Format = 'pdf' | 'zip' | 'both';

/** Export a whole collection: options → background job → progress → download links. */
export function CollectionExportDialog({ collection, onClose }: {
  collection: Collection;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [format, setFormat] = useState<Format>('pdf');
  const [scale, setScale] = useState(2);
  const [pageNumbers, setPageNumbers] = useState(true);
  const [titlePages, setTitlePages] = useState(true);
  const [cover, setCover] = useState(true);
  const [job, setJob] = useState<CollectionExportJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const running = starting || job?.status === 'running';
  const jobId = job?.status === 'running' ? job.id : null;

  // poll the running job once a second
  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    const timer = window.setInterval(async () => {
      try {
        const r = await fetch(`/api/collections/exports/${jobId}`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data = (await r.json()) as CollectionExportJob;
        if (!cancelled) setJob(data);
      } catch (e) {
        if (!cancelled) setError(String(e));
      }
    }, 1000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [jobId]);

  const start = async () => {
    setStarting(true);
    setError(null);
    setJob(null);
    try {
      const r = await fetch(`/api/collections/${collection.id}/export`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          format, scale: clampScale(scale), pageNumbers,
          episodeTitlePages: titlePages, cover,
        }),
      });
      const data = await r.json().catch(() => ({}));
      if (r.status === 409) {
        setError(t.showcase.exportBusy);
      } else if (!r.ok) {
        setError(fill(t.showcase.exportFailed, { error: data.detail || `HTTP ${r.status}` }));
      } else {
        setJob(data as CollectionExportJob);
      }
    } catch (e) {
      setError(fill(t.showcase.exportFailed, { error: String(e) }));
    } finally {
      setStarting(false);
    }
  };

  const pct = exportPercent(job);

  return (
    <div className="modal-overlay" onClick={() => { if (!running) onClose(); }}>
      <div className="modal-content collection-export" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3>{t.showcase.exportCollection}</h3>
          <button className="btn btn-ghost btn-sm" onClick={onClose} title={t.showcase.close}>
            <FiX size={16} />
          </button>
        </div>
        <p className="text-sm text-secondary mt-sm">{collection.name}</p>

        <div className="collection-export-options mt-md">
          <label className="collection-export-row">
            <span>{t.showcase.format}</span>
            <select className="select" value={format} disabled={running}
              onChange={e => setFormat(e.target.value as Format)}>
              <option value="pdf">PDF</option>
              <option value="zip">ZIP (PNG)</option>
              <option value="both">PDF + ZIP</option>
            </select>
          </label>
          <label className="collection-export-row">
            <span>{t.showcase.scale}</span>
            <input className="input" type="number" min={0.5} max={8} step={0.5}
              value={scale} disabled={running}
              onChange={e => setScale(Number(e.target.value))}
              onBlur={() => setScale(s => clampScale(s))} />
          </label>
          <label className="collection-export-check">
            <input type="checkbox" checked={pageNumbers} disabled={running}
              onChange={e => setPageNumbers(e.target.checked)} />
            {t.showcase.pageNumbers}
          </label>
          <label className="collection-export-check">
            <input type="checkbox" checked={titlePages} disabled={running}
              onChange={e => setTitlePages(e.target.checked)} />
            {t.showcase.episodeTitlePages}
          </label>
          <label className="collection-export-check">
            <input type="checkbox" checked={cover} disabled={running}
              onChange={e => setCover(e.target.checked)} />
            {t.showcase.collectionCover}
          </label>
        </div>

        {job && (
          <div className="collection-export-progress mt-md" aria-live="polite">
            <div className="collection-progress-bar">
              <div className="collection-progress-fill" style={{ width: `${pct}%` }} />
            </div>
            <p className="text-sm text-secondary mt-sm">
              {job.status === 'running' && fill(t.showcase.exporting, { done: job.done, total: job.total })}
              {job.status === 'done' && fill(t.showcase.exportDone, { n: job.done })}
              {job.status === 'error' && (
                <span className="collection-error">
                  {fill(t.showcase.exportFailed, { error: job.error || '?' })}
                </span>
              )}
            </p>
            {job.warnings?.length > 0 && (
              <ul className="collection-warnings text-sm">
                {job.warnings.map(w => <li key={w}>{w}</li>)}
              </ul>
            )}
            {job.status === 'done' && (
              <div className="flex gap-sm mt-sm">
                {job.pdf && (
                  <a className="btn btn-primary btn-sm" href={job.pdf.url} download>
                    <FiDownload size={14} /> {t.showcase.downloadPdf}
                  </a>
                )}
                {job.zip && (
                  <a className="btn btn-secondary btn-sm" href={job.zip.url} download>
                    <FiDownload size={14} /> {t.showcase.downloadZip}
                  </a>
                )}
              </div>
            )}
          </div>
        )}
        {error && <p className="collection-error text-sm mt-md">{error}</p>}

        <div className="flex gap-sm mt-lg justify-end">
          <button className="btn btn-secondary" onClick={onClose}>{t.showcase.close}</button>
          <button className="btn btn-primary" onClick={start} disabled={running}>
            <FiDownload size={14} /> {t.showcase.startExport}
          </button>
        </div>
      </div>
    </div>
  );
}
