import { useEffect, useMemo, useRef, useState } from 'react';
import { FiLayers, FiX, FiZap } from 'react-icons/fi';
import { fill, useTranslation } from '../../hooks/useTranslation';
import { useTips } from '../../hooks/useTips';
import type { AiAction } from './AiRewrite';
import { batchCandidates, chooseBlocks, draftUncutAllowed, estimate, requestBlocks, type BatchScope } from './batchPlan';
import type { OutlineKind, OutlineWords } from './outline';
import './aiBatch.css';

export interface BatchStartBody {
  text: string;
  blocks: ReturnType<typeof requestBlocks>;
  action: AiAction;
  instruction?: string;
  remove_todo?: boolean;
}

interface Props {
  text: string;                   // the editor text: the blocks are cut from it, and it is what is sent
  words: OutlineWords;
  model: string;
  blocked: string | null;         // why a batch can't start now (no LLM, one running), else null
  replaces: number;               // accepted suggestions of the current batch not applied yet (a warning)
  onStart: (body: BatchStartBody) => Promise<void>;   // throws with the server's message
  onClose: () => void;
}

/** "Batch AI…": pick the blocks (scenes, pages or panels; all, uncut only or a chosen few) and the action. */
export function BatchDialog({ text, words, model, blocked, replaces, onStart, onClose }: Props) {
  const { t } = useTranslation();
  const c = t.comics;
  const tip = useTips().comics;
  const ref = useRef<HTMLDialogElement>(null);
  const [kind, setKind] = useState<OutlineKind>('scene');
  const [scope, setScope] = useState<BatchScope>('all');
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [action, setAction] = useState<AiAction>('tighten_dialogue');
  const [instruction, setInstruction] = useState('');
  const [removeTodo, setRemoveTodo] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // the text as the dialog opened: the blocks and the request are cut from the same string
  const [snapshot] = useState(text);
  const cands = useMemo(() => batchCandidates(snapshot, kind, words), [snapshot, kind, words]);
  const blocks = chooseBlocks(cands, scope, chosen);
  const uncutCount = cands.filter(b => b.uncut).length;
  const draftOk = draftUncutAllowed(blocks);
  const chosenAction: AiAction = action === 'draft_uncut' && !draftOk ? 'tighten_dialogue' : action;
  const est = estimate(blocks.length);
  const needsInstruction = chosenAction === 'custom' && !instruction.trim();

  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
    return () => { if (d?.open) d.close(); };
  }, []);

  const pickKind = (k: OutlineKind) => { setKind(k); setChosen(new Set()); };
  const toggle = (id: string) => setChosen(prev => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  const start = async () => {
    if (blocked || !blocks.length || needsInstruction) return;
    setBusy(true);
    setError(null);
    try {
      await onStart({
        text: snapshot, blocks: requestBlocks(blocks), action: chosenAction,
        instruction: instruction.trim() || undefined,
        ...(chosenAction === 'draft_uncut' ? { remove_todo: removeTodo } : {}),
      });
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };

  const kinds: { id: OutlineKind; label: string }[] = [
    { id: 'scene', label: c.outlineScenes }, { id: 'page', label: c.outlinePages }, { id: 'panel', label: c.outlinePanels },
  ];
  const actions: { id: AiAction; label: string; hint: string; off?: boolean }[] = [
    { id: 'tighten_dialogue', label: c.aiTighten, hint: c.aiTightenHint },
    { id: 'enrich_description', label: c.aiEnrich, hint: c.aiEnrichHint },
    { id: 'draft_uncut', label: c.aiDraftUncut, hint: draftOk ? c.aiDraftUncutHint : c.batchDraftUncutOnly, off: !draftOk },
    { id: 'custom', label: c.aiCustom, hint: c.aiCustomHint },
  ];

  return (
    // Escape (the dialog's cancel event) closes it like the Close button
    <dialog ref={ref} className="ai-batch-dialog" aria-labelledby="ai-batch-title" onCancel={e => { e.preventDefault(); if (!busy) onClose(); }}>
      <div className="ai-rewrite-head">
        <FiLayers size={14} />
        <b id="ai-batch-title">{c.batchTitle}</b>
        <button className="btn btn-ghost btn-icon ai-rewrite-close" onClick={onClose} disabled={busy} data-tip={`${c.batchClose} (Esc)`} aria-label={c.batchClose}>
          <FiX size={14} />
        </button>
      </div>

      <fieldset className="ai-batch-field">
        <legend>{c.batchGrouping}</legend>
        <div className="ai-rewrite-actions" role="radiogroup" aria-label={c.batchGrouping}>
          {kinds.map(k => (
            <button key={k.id} role="radio" aria-checked={kind === k.id} disabled={busy}
              className={`ai-rewrite-action ${kind === k.id ? 'active' : ''}`} onClick={() => pickKind(k.id)} data-tip={tip.batchKind}>{k.label}</button>
          ))}
        </div>
      </fieldset>

      <fieldset className="ai-batch-field">
        <legend>{c.batchScope}</legend>
        <div className="ai-rewrite-actions" role="radiogroup" aria-label={c.batchScope}>
          {([['all', fill(c.batchScopeAll, { n: cands.length })], ['uncut', fill(c.batchScopeUncut, { n: uncutCount })],
            ['chosen', fill(c.batchScopeChosen, { n: chooseBlocks(cands, 'chosen', chosen).length })]] as [BatchScope, string][]).map(([id, label]) => (
            <button key={id} role="radio" aria-checked={scope === id} disabled={busy || (id === 'uncut' && !uncutCount)}
              className={`ai-rewrite-action ${scope === id ? 'active' : ''}`} onClick={() => setScope(id)} data-tip={id === 'all' ? tip.scopeAll : id === 'uncut' ? tip.scopeUncut : tip.scopeChosen}>{label}</button>
          ))}
        </div>
        {scope === 'chosen' && (
          <div className="ai-batch-choose">
            <div className="ai-batch-choose-head">
              <button className="btn btn-ghost" disabled={busy} onClick={() => setChosen(new Set(cands.map(b => b.id)))}>{c.batchSelectAll}</button>
              <button className="btn btn-ghost" disabled={busy} onClick={() => setChosen(new Set())}>{c.batchSelectNone}</button>
            </div>
            <ul>
              {cands.map(b => (
                <li key={b.id}>
                  <label className="comics-check">
                    <input type="checkbox" checked={chosen.has(b.id)} disabled={busy} onChange={() => toggle(b.id)} />
                    <span>{b.label}</span>
                    {b.uncut && <span className="comics-badge uncut">{c.uncutBadge}</span>}
                    {b.todo && <span className="comics-badge stale">{c.outlineTodo}</span>}
                  </label>
                </li>
              ))}
            </ul>
          </div>
        )}
        {!cands.length && <p className="text-sm text-muted">{c.batchNone}</p>}
      </fieldset>

      <fieldset className="ai-batch-field">
        <legend>{c.batchAction}</legend>
        <div className="ai-rewrite-actions" role="radiogroup" aria-label={c.batchAction}>
          {actions.map(a => (
            <button key={a.id} role="radio" aria-checked={chosenAction === a.id} disabled={busy || a.off}
              className={`ai-rewrite-action ${chosenAction === a.id ? 'active' : ''}`} onClick={() => setAction(a.id)} data-tip={a.hint}>
              {a.label}
            </button>
          ))}
        </div>
        <textarea className="input ai-rewrite-instruction" rows={2} maxLength={2000} disabled={busy}
          placeholder={chosenAction === 'custom' ? c.aiInstructionCustom : c.aiInstruction}
          aria-label={chosenAction === 'custom' ? c.aiInstructionCustom : c.aiInstruction}
          value={instruction} onChange={e => setInstruction(e.target.value)} data-tip={tip.batchInstruction} />
        {chosenAction === 'draft_uncut' && blocks.some(b => b.todo) && (
          <label className="comics-check" data-tip={tip.aiRemoveTodo}>
            <input type="checkbox" checked={removeTodo} disabled={busy} onChange={e => setRemoveTodo(e.target.checked)} /> {c.aiRemoveTodo}
          </label>
        )}
      </fieldset>

      {replaces > 0 && !blocked && <div className="comics-note">{fill(c.batchReplaces, { n: replaces })}</div>}
      {blocked && <div className="comics-note">{blocked}</div>}
      {error && <div className="comics-error ai-rewrite-error" onClick={() => setError(null)}>{error}</div>}

      <div className="ai-rewrite-foot">
        <span className="text-sm text-muted">
          {fill(c.aiModel, { model: model || '—' })} · {fill(c.batchEstimate, { n: est.blocks, m: est.minutes, s: est.secondsPerBlock })}
        </span>
        <button className="btn btn-secondary" onClick={onClose} disabled={busy}>{c.batchClose}</button>
        <button className="btn btn-primary" onClick={start} disabled={busy || !!blocked || !blocks.length || needsInstruction} data-tip={tip.batchStart}>
          <FiZap size={14} /> {c.batchStart}
        </button>
      </div>
    </dialog>
  );
}
