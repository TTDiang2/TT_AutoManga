import { memo, useEffect, useRef } from 'react';
import { FiChevronDown, FiChevronRight, FiLayers, FiList, FiZap } from 'react-icons/fi';
import { fill, useTranslation } from '../../hooks/useTranslation';
import { useTips } from '../../hooks/useTips';
import { entryAt, entryLabel, listOf, targetLabel, type Outline, type OutlineEntry, type OutlineKind, type OutlinePage, type OutlinePanel as Panel, type OutlineScene, type OutlineWords } from './outline';

interface Props {
  outline: Outline;
  caret: number;                       // the editor's caret (debounced)
  open: boolean;
  onToggle: () => void;
  mode: OutlineKind;
  onMode: (mode: OutlineKind) => void;
  words: OutlineWords;
  aiBlocked: string | null;            // why the AI buttons are off (no LLM, a rewrite open), else null
  onPick: (kind: OutlineKind, entry: OutlineEntry) => void;
  onAi: (kind: OutlineKind, entry: OutlineEntry) => void;
  onBatch: () => void;                 // "Batch AI…"
  batchBlocked: string | null;         // why it is off (no LLM, a batch running elsewhere), else null
}

const name = (id: string) => (id ? id[0].toUpperCase() + id.slice(1) : id);

/** The Script view's outline: the script's pages, scenes or panels; the one holding the caret is marked. */
export const OutlinePanel = memo(function OutlinePanel({ outline, caret, open, onToggle, mode, onMode, words, aiBlocked, onPick, onAi, onBatch, batchBlocked }: Props) {
  const { t } = useTranslation();
  const c = t.comics;
  const tip = useTips().comics;
  const listRef = useRef<HTMLUListElement>(null);
  const entries = listOf(outline, mode);
  const active = open ? entryAt(entries, caret, outline.length) : null;
  const activeId = active?.id ?? null;
  const panelsById = new Map(outline.panels.map(p => [p.id, p]));

  // keep the caret's entry in sight (the list only, never the page)
  useEffect(() => {
    const list = listRef.current;
    if (!list || !activeId) return;
    const el = list.querySelector<HTMLElement>('[aria-current="location"]');
    if (!el) return;
    const top = el.offsetTop, bottom = top + el.offsetHeight;
    if (top < list.scrollTop) list.scrollTop = top - 4;
    else if (bottom > list.scrollTop + list.clientHeight) list.scrollTop = bottom - list.clientHeight + 4;
  }, [activeId, mode]);

  const count = (n: number) => (n === 1 ? c.outlineCountOne : fill(c.outlineCount, { n }));
  const castOf = (ids: string[]) => {
    const out: string[] = [];
    for (const id of ids) for (const who of panelsById.get(id)?.cast ?? []) if (!out.includes(who)) out.push(who);
    return out;
  };

  const meta = (e: OutlineEntry) => {
    if (mode === 'page') {
      const p = e as OutlinePage;
      return [count(p.panels.length), castOf(p.panels).map(name).join(', ')];
    }
    if (mode === 'scene') {
      const s = e as OutlineScene;
      return [count(s.panels.length), s.cast.map(name).join(', ')];
    }
    const p = e as Panel;
    return [p.cast.map(name).join(', '), p.shot];
  };

  const tabs: { id: OutlineKind; label: string }[] = [
    { id: 'page', label: c.outlinePages }, { id: 'scene', label: c.outlineScenes }, { id: 'panel', label: c.outlinePanels },
  ];

  return (
    <nav className={`comics-outline ${open ? 'open' : 'collapsed'}`} aria-label={c.outline}>
      <div className="comics-outline-head">
        <button className="comics-outline-toggle" onClick={onToggle} aria-expanded={open}
          data-tip={open ? c.outlineHide : c.outlineShow}>
          {open ? <FiChevronDown size={13} /> : <FiChevronRight size={13} />} <FiList size={13} /> {c.outline}
        </button>
        {open && (
          <div className="comics-outline-tabs" role="group" aria-label={c.outline}>
            {tabs.map(tab => (
              <button key={tab.id} className={mode === tab.id ? 'active' : ''} aria-pressed={mode === tab.id} onClick={() => onMode(tab.id)} data-tip={tip.outlineMode}>
                {tab.label}
              </button>
            ))}
          </div>
        )}
        {open && (
          <button className="comics-outline-batch" onClick={onBatch} disabled={!!batchBlocked}
            data-tip={batchBlocked ?? c.batchOpenHint}>
            <FiLayers size={12} /> {c.batchOpen}
          </button>
        )}
      </div>
      {open && (
        entries.length ? (
          <ul className="comics-outline-list" ref={listRef} title={c.outlineHint}>
            {entries.map(e => {
              const label = entryLabel(mode, e, words);
              const full = targetLabel({ kind: mode, start: e.startOffset, end: e.endOffset, entry: e }, words);
              const [m1, m2] = meta(e);
              const isActive = e.id === activeId;
              const desc = mode === 'panel' ? (e as Panel).firstDescription : '';
              return (
                <li key={e.id} className={isActive ? 'active' : ''}>
                  <button className="comics-outline-entry" aria-current={isActive ? 'location' : undefined}
                    onClick={() => onPick(mode, e)} data-tip={fill(c.outlineSelect, { label: full })}>
                    <span className="comics-outline-label">
                      {label}
                      {e.uncut && <span className="comics-badge uncut" title={c.uncutBadgeHint}>{c.uncutBadge}</span>}
                      {e.todo && <span className="comics-badge stale" title={c.outlineTodoHint}>{c.outlineTodo}</span>}
                    </span>
                    {desc && <span className="comics-outline-desc">{desc}</span>}
                    {(m1 || m2) && <span className="comics-outline-meta">{[m1, m2].filter(Boolean).join(' · ')}</span>}
                  </button>
                  <button className="comics-outline-ai" disabled={!!aiBlocked} onClick={() => onAi(mode, e)}
                    aria-label={fill(c.outlineAi, { label: full })} data-tip={aiBlocked ?? fill(c.outlineAi, { label: full })}>
                    <FiZap size={12} /> AI
                  </button>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="comics-outline-empty text-sm text-muted">{c.outlineEmpty}</p>
        )
      )}
    </nav>
  );
});
