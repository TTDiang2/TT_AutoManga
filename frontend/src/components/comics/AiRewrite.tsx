import { useEffect, useMemo, useRef, useState } from 'react';
import { FiAlertTriangle, FiCheck, FiRefreshCw, FiX, FiZap } from 'react-icons/fi';
import { fill, useTranslation } from '../../hooks/useTranslation';
import { findBlock, type AiBlock } from './aiBlock';
import './aiRewrite.css';

export type AiAction = 'tighten_dialogue' | 'enrich_description' | 'draft_uncut' | 'custom';

interface RewriteResult {
  suggestion: string;
  original: string;
  plan: { ok: boolean; error: string | null; line: number | null };
  model: string;
  durationMs: number;
}

interface Props {
  script: string;
  text: string;                                 // the editor text now
  caret: { start: number; end: number };        // the editor selection when the popover opened
  model: string;                                // the configured LLM model, shown to the owner
  onAccept: (start: number, end: number, replacement: string) => void;
  onClose: (block: { start: number; end: number } | null) => void;   // focus goes back to the editor there
}

/** Original and suggestion lines, each marked when the other side lacks it (a cheap line diff). */
function marked(lines: string[], other: string[]) {
  const set = new Set(other.map(l => l.trim()));
  return lines.map(l => ({ l, changed: !!l.trim() && !set.has(l.trim()) }));
}

export function AiRewrite({ script, text, caret, model, onAccept, onClose }: Props) {
  const { t } = useTranslation();
  const c = t.comics;
  const [page, setPage] = useState(false);
  const [action, setAction] = useState<AiAction>('enrich_description');
  const [instruction, setInstruction] = useState('');
  const [removeTodo, setRemoveTodo] = useState(false);
  const [busySince, setBusySince] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [error, setError] = useState<string | null>(null);
  // the run's block and the text it was cut from, fixed when the run starts
  const [ran, setRan] = useState<{ block: AiBlock; original: string } | null>(null);
  const [result, setResult] = useState<RewriteResult | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  const live = useMemo(() => findBlock(text, caret.start, caret.end, page), [text, caret.start, caret.end, page]);
  const block = ran?.block ?? live;
  const busy = busySince !== null;
  const actions: { id: AiAction; label: string; hint: string }[] = [
    { id: 'tighten_dialogue', label: c.aiTighten, hint: c.aiTightenHint },
    { id: 'enrich_description', label: c.aiEnrich, hint: c.aiEnrichHint },
    ...(block?.uncut ? [{ id: 'draft_uncut' as const, label: c.aiDraftUncut, hint: c.aiDraftUncutHint }] : []),
    { id: 'custom', label: c.aiCustom, hint: c.aiCustomHint },
  ];
  const chosen = action === 'draft_uncut' && !block?.uncut ? 'enrich_description' : action;

  useEffect(() => {
    if (!busy) return;
    const timer = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(timer);
  }, [busy]);

  // a run still going when the popover goes away is cancelled
  useEffect(() => () => abortRef.current?.abort(), []);

  useEffect(() => { rootRef.current?.querySelector<HTMLElement>('button, textarea')?.focus(); }, []);

  const close = () => {
    abortRef.current?.abort();
    onClose(block ? { start: block.start, end: block.end } : null);
  };

  // Escape closes, wherever the focus is
  const closeRef = useRef(close);
  useEffect(() => { closeRef.current = close; });
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.preventDefault(); closeRef.current(); } };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  const run = async () => {
    const b = live;
    if (!b) return;
    if (chosen === 'custom' && !instruction.trim()) { setError(c.aiInstructionCustom); return; }
    const original = text.slice(b.start, b.end);
    abortRef.current?.abort();
    const ctl = new AbortController();
    abortRef.current = ctl;
    setRan({ block: b, original });
    setResult(null);
    setError(null);
    setBusySince(Date.now());
    setNow(Date.now());
    try {
      const res = await fetch(`/api/comics/scripts/${script}/rewrite`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: ctl.signal,
        body: JSON.stringify({
          text, start: b.start, end: b.end, action: chosen,
          instruction: instruction.trim() || undefined,
          ...(chosen === 'draft_uncut' ? { remove_todo: removeTodo } : {}),
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `HTTP ${res.status}`);
      if (!ctl.signal.aborted) setResult(body as RewriteResult);
    } catch (e) {
      if (!ctl.signal.aborted) { setError((e as Error).message); setRan(null); }
    } finally {
      if (abortRef.current === ctl) { abortRef.current = null; setBusySince(null); }
    }
  };

  const cancel = () => { abortRef.current?.abort(); abortRef.current = null; setBusySince(null); setRan(null); };

  const discard = () => { setResult(null); setRan(null); setError(null); };

  const accept = () => {
    if (!ran || !result) return;
    const { block: b, original } = ran;
    if (text.slice(b.start, b.end) !== original) { setError(c.aiChanged); return; }
    onAccept(b.start, b.end, result.suggestion);
  };

  const elapsed = busySince !== null ? Math.max(0, Math.floor((now - busySince) / 1000)) : 0;
  const kindLabel = block ? { selection: c.aiBlockSelection, panel: c.aiBlockPanel, page: c.aiBlockPage }[block.kind] : '';
  const origLines = (ran?.original ?? '').replace(/\r/g, '').replace(/\n+$/, '').split('\n');
  const suggLines = (result?.suggestion ?? '').replace(/\r/g, '').replace(/\n+$/, '').split('\n');

  return (
    <div className="ai-rewrite" ref={rootRef} role="dialog" aria-label={c.aiRewrite}>
      <div className="ai-rewrite-head">
        <FiZap size={14} />
        <b>{c.aiRewrite}</b>
        {block ? (
          <span className="ai-rewrite-block">{kindLabel} · {fill(c.aiLines, { a: block.firstLine, b: block.lastLine })}</span>
        ) : (
          <span className="ai-rewrite-block">{c.aiNoBlock}</span>
        )}
        {caret.start === caret.end && !ran && (
          <label className="comics-check">
            <input type="checkbox" checked={page} onChange={e => setPage(e.target.checked)} /> {c.aiWholePage}
          </label>
        )}
        <button className="btn btn-ghost btn-icon ai-rewrite-close" onClick={close} title={`${c.aiClose} (Esc)`}><FiX size={14} /></button>
      </div>

      {!result && (
        <>
          <div className="ai-rewrite-actions" role="radiogroup">
            {actions.map(a => (
              <button key={a.id} role="radio" aria-checked={chosen === a.id} disabled={busy}
                className={`ai-rewrite-action ${chosen === a.id ? 'active' : ''}`} onClick={() => setAction(a.id)} title={a.hint}>
                {a.label}
              </button>
            ))}
          </div>
          <textarea className="input ai-rewrite-instruction" rows={2} maxLength={2000} disabled={busy}
            placeholder={chosen === 'custom' ? c.aiInstructionCustom : c.aiInstruction}
            value={instruction} onChange={e => setInstruction(e.target.value)}
            onKeyDown={e => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter' && !busy) { e.preventDefault(); run(); } }} />
          {chosen === 'draft_uncut' && block?.todo && (
            <label className="comics-check">
              <input type="checkbox" checked={removeTodo} disabled={busy} onChange={e => setRemoveTodo(e.target.checked)} /> {c.aiRemoveTodo}
            </label>
          )}
          <div className="ai-rewrite-foot">
            <span className="text-sm text-muted">{fill(c.aiModel, { model: model || '—' })}</span>
            {busy ? (
              <>
                <span className="ai-rewrite-busy"><span className="ai-rewrite-spinner" /> {fill(c.aiRunning, { s: elapsed })}</span>
                <button className="btn btn-secondary" onClick={cancel}>{c.aiCancel}</button>
              </>
            ) : (
              <button className="btn btn-primary" onClick={run} disabled={!block || (chosen === 'custom' && !instruction.trim())}>
                <FiZap size={14} /> {c.aiRun}
              </button>
            )}
          </div>
        </>
      )}

      {error && <div className="comics-error ai-rewrite-error" onClick={() => setError(null)}>{error}</div>}

      {result && ran && (
        <>
          <div className="ai-rewrite-diff">
            <div>
              <div className="ai-rewrite-col-head">{c.aiOriginal}</div>
              <pre>{marked(origLines, suggLines).map((x, i) => <div key={i} className={x.changed ? 'removed' : ''}>{x.l || ' '}</div>)}</pre>
            </div>
            <div>
              <div className="ai-rewrite-col-head">{c.aiSuggestion} <span className="text-muted">· {result.model} · {fill(c.aiTook, { s: Math.round(result.durationMs / 100) / 10 })}</span></div>
              <pre>{marked(suggLines, origLines).map((x, i) => <div key={i} className={x.changed ? 'added' : ''}>{x.l || ' '}</div>)}</pre>
            </div>
          </div>
          <div className={`ai-rewrite-plan ${result.plan.ok ? 'ok' : 'bad'}`}>
            {result.plan.ok ? <><FiCheck size={13} /> {c.aiPlanOk}</> : (
              <><FiAlertTriangle size={13} /> {c.aiPlanError}{result.plan.line != null && <b> · line {result.plan.line}</b>}: {(result.plan.error || '').replace(/^[^\n]*?:\d+: /, '')}</>
            )}
          </div>
          <div className="ai-rewrite-foot">
            <button className="btn btn-ghost" onClick={discard}>{c.aiDiscard}</button>
            <button className="btn btn-secondary" onClick={run}><FiRefreshCw size={14} /> {c.aiRetry}</button>
            <button className="btn btn-primary" onClick={accept}><FiCheck size={14} /> {c.aiAccept}</button>
          </div>
        </>
      )}
    </div>
  );
}
