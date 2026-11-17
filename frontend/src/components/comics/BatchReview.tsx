import { useEffect, useMemo, useRef, useState } from 'react';
import { FiAlertTriangle, FiCheck, FiCheckCircle, FiCircle, FiLoader, FiShield, FiSquare, FiTrash2, FiX, FiXCircle } from 'react-icons/fi';
import { fill, useTranslation } from '../../hooks/useTranslation';
import { PlanStatus, RewriteDiff } from './AiRewrite';
import { finished, textHash, type Batch, type BatchResult } from './batchApply';
import { filterResults, flagged, passing, toApply, useBatchReview, type BatchFilter } from './batchDecisions';
import './aiRewrite.css';
import './aiBatch.css';

interface Props {
  batch: Batch;
  editorText: string;
  onApply: (results: BatchResult[]) => void;
  onStop: () => void;
  onClear: () => void;
}

const NO_DECISIONS = {};
const NO_APPLIED: number[] = [];

/** The batch AI rewrite's review: its blocks with their outcome, one block's suggestion beside its original,
    Accept / Reject per block (and in bulk), and "Apply N accepted to editor". */
export function BatchReview({ batch, editorText, onApply, onStop, onClear }: Props) {
  const { t } = useTranslation();
  const c = t.comics;
  const decisions = useBatchReview(s => s.decisions[batch.id] ?? NO_DECISIONS) as Record<number, 'accept' | 'reject'>;
  const applied = useBatchReview(s => s.applied[batch.id] ?? NO_APPLIED);
  const decide = useBatchReview(s => s.decide);
  const [filter, setFilter] = useState<BatchFilter>('all');
  const [picked, setSel] = useState<number | null>(null);
  const listRef = useRef<HTMLUListElement>(null);

  const shown = useMemo(() => filterResults(batch.results, filter), [batch.results, filter]);
  // the selection stays on a shown block (the first, when the picked one is filtered out)
  const sel = picked !== null && shown.some(r => r.index === picked) ? picked : shown[0]?.index ?? null;
  const current = batch.results.find(r => r.index === sel) ?? null;
  const appliedSet = useMemo(() => new Set(applied), [applied]);
  const pending = toApply(batch.results, decisions, applied);
  const running = batch.status === 'running';
  const drift = textHash(editorText) !== batch.snapshotHash;

  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest' });
  }, [sel]);

  const canDecide = (r: BatchResult) => r.status === 'done' && r.suggestion != null && !appliedSet.has(r.index);
  const toggle = (r: BatchResult, d: 'accept' | 'reject') => {
    if (!canDecide(r)) return;
    decide(batch.id, [r.index], decisions[r.index] === d ? null : d);
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const i = shown.findIndex(r => r.index === sel);
    const move = (to: number) => { e.preventDefault(); const r = shown[Math.max(0, Math.min(shown.length - 1, to))]; if (r) setSel(r.index); };
    if (e.key === 'ArrowDown') move(i + 1);
    else if (e.key === 'ArrowUp') move(i - 1);
    else if (e.key === 'Home') move(0);
    else if (e.key === 'End') move(shown.length - 1);
    else if ((e.key === 'a' || e.key === 'A') && current) { e.preventDefault(); toggle(current, 'accept'); }
    else if ((e.key === 'r' || e.key === 'R') && current) { e.preventDefault(); toggle(current, 'reject'); }
  };

  const statusText = (r: BatchResult) => {
    if (appliedSet.has(r.index)) return c.batchResApplied;
    if (r.status === 'pending') return c.batchResPending;
    if (r.status === 'running') return c.batchResRunning;
    if (r.status === 'failed') return c.batchResFailed;
    if (r.status === 'refused') return c.batchResRefused;
    return passing(r) ? c.batchResPassing : c.batchResFlagged;
  };
  const icon = (r: BatchResult) => {
    if (r.status === 'pending') return <FiCircle className="st-pending" />;
    if (r.status === 'running') return <FiLoader className="st-running" />;
    if (r.status === 'failed') return <FiXCircle className="st-failed" />;
    if (r.status === 'refused') return <FiShield className="st-refused" />;
    return passing(r) ? <FiCheckCircle className="st-ok" /> : <FiAlertTriangle className="st-flagged" />;
  };

  const filters: { id: BatchFilter; label: string; n: number }[] = [
    { id: 'all', label: c.batchFilterAll, n: batch.results.length },
    { id: 'passing', label: c.batchFilterPassing, n: batch.results.filter(passing).length },
    { id: 'flagged', label: c.batchFilterFlagged, n: batch.results.filter(flagged).length },
    { id: 'failed', label: c.batchFilterFailed, n: batch.failed },
    { id: 'refused', label: c.batchFilterRefused, n: batch.refused },
  ];
  const statusName = { running: c.batchStatusRunning, done: c.batchStatusDone, stopped: c.batchStatusStopped, failed: c.batchStatusFailed }[batch.status];
  const actionName: Record<string, string> = { tighten_dialogue: c.aiTighten, enrich_description: c.aiEnrich, draft_uncut: c.aiDraftUncut, custom: c.aiCustom };
  const pct = batch.total ? (100 * finished(batch)) / batch.total : 0;
  const decidable = batch.results.filter(canDecide);

  return (
    <div className="ai-batch">
      <div className="ai-batch-bar">
        <span className="ai-batch-status">
          <b>{actionName[batch.action] ?? batch.action}</b> · {statusName} · {fill(c.batchSummary, { done: batch.done, failed: batch.failed, refused: batch.refused, total: batch.total })}
          <span className="text-muted"> · {batch.model}</span>
        </span>
        <div className="comics-progress ai-batch-progress" role="progressbar" aria-valuemin={0} aria-valuemax={batch.total} aria-valuenow={finished(batch)}>
          <div style={{ width: `${pct}%` }} />
        </div>
        {running ? (
          <button className="btn btn-secondary comics-stop" onClick={onStop}><FiSquare size={14} /> {c.batchStop}</button>
        ) : (
          <button className="btn btn-ghost" onClick={onClear} title={c.batchClearHint}><FiTrash2 size={14} /> {c.batchClear}</button>
        )}
      </div>
      {batch.error && <div className="comics-error">{batch.error}</div>}
      {drift && pending.length > 0 && <div className="comics-note">{c.batchDrift}</div>}

      <div className="ai-batch-tools">
        <div className="comics-outline-tabs ai-batch-filters" role="group" aria-label={c.batchFilter}>
          {filters.map(f => (
            <button key={f.id} className={filter === f.id ? 'active' : ''} aria-pressed={filter === f.id} onClick={() => setFilter(f.id)}>
              {f.label} ({f.n})
            </button>
          ))}
        </div>
        <span className="text-sm text-muted ai-batch-keys">{c.batchKeys}</span>
        <button className="btn btn-ghost" disabled={!decidable.some(passing)}
          onClick={() => decide(batch.id, decidable.filter(passing).map(r => r.index), 'accept')}>
          <FiCheck size={14} /> {c.batchAcceptAllPassing}
        </button>
        <button className="btn btn-ghost" disabled={!decidable.length}
          onClick={() => decide(batch.id, decidable.map(r => r.index), 'reject')}>
          <FiX size={14} /> {c.batchRejectAll}
        </button>
        <button className="btn btn-primary" disabled={!pending.length} onClick={() => onApply(pending)} title={c.batchApplyHint}>
          {fill(c.batchApply, { n: pending.length })}
        </button>
      </div>

      <div className="ai-batch-body">
        {shown.length ? (
          <ul className="ai-batch-list" role="listbox" ref={listRef} tabIndex={0} aria-label={`${c.batchList}. ${c.batchKeys}`}
            aria-activedescendant={sel !== null ? `ai-batch-${batch.id}-${sel}` : undefined} onKeyDown={onKey}>
            {shown.map(r => {
              const d = decisions[r.index];
              return (
                <li key={r.index} id={`ai-batch-${batch.id}-${r.index}`} role="option" aria-selected={r.index === sel}
                  className={`${r.index === sel ? 'selected' : ''} ${d ?? ''} ${appliedSet.has(r.index) ? 'applied' : ''}`}
                  onClick={() => { setSel(r.index); listRef.current?.focus(); }}>
                  <span className="ai-batch-icon" aria-hidden="true">{icon(r)}</span>
                  <span className="ai-batch-label">{r.label || `#${r.index + 1}`}</span>
                  <span className="ai-batch-meta">
                    {statusText(r)}
                    {d === 'accept' && !appliedSet.has(r.index) && <b className="ai-batch-dec accept"> · {c.batchAccept}</b>}
                    {d === 'reject' && <b className="ai-batch-dec reject"> · {c.batchReject}</b>}
                  </span>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="ai-batch-list text-sm text-muted">{c.batchEmpty}</p>
        )}

        <div className="ai-batch-detail">
          {!current ? <p className="text-sm text-muted">{c.batchPick}</p> : (
            <>
              <div className="ai-batch-detail-head">
                <b>{current.label || `#${current.index + 1}`}</b>
                <span className="text-sm text-muted">{statusText(current)}{current.durationMs != null && current.status !== 'pending' ? ` · ${fill(c.aiTook, { s: Math.round(current.durationMs / 100) / 10 })}` : ''}</span>
                {canDecide(current) && (
                  <span className="ai-batch-decide">
                    <button className={`btn ${decisions[current.index] === 'accept' ? 'btn-primary' : 'btn-secondary'}`} aria-pressed={decisions[current.index] === 'accept'}
                      onClick={() => toggle(current, 'accept')} title="A"><FiCheck size={14} /> {c.batchAccept}</button>
                    <button className={`btn ${decisions[current.index] === 'reject' ? 'btn-primary' : 'btn-secondary'}`} aria-pressed={decisions[current.index] === 'reject'}
                      onClick={() => toggle(current, 'reject')} title="R"><FiX size={14} /> {c.batchReject}</button>
                  </span>
                )}
              </div>
              {current.status === 'done' && current.suggestion != null ? (
                <>
                  <RewriteDiff original={current.original} suggestion={current.suggestion} />
                  {current.plan && <PlanStatus plan={current.plan} />}
                </>
              ) : (
                <>
                  {current.error && <div className="comics-error ai-rewrite-error">{current.error}</div>}
                  {current.status === 'pending' && !running && <p className="text-sm text-muted">{c.batchNotRun}</p>}
                  <pre className="ai-batch-original">{current.original}</pre>
                </>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
