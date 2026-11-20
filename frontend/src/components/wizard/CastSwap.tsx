import { useMemo, useState } from 'react';
import { FiCornerUpLeft, FiPlus, FiRepeat, FiUser } from 'react-icons/fi';
import { useTranslation, fill } from '../../hooks/useTranslation';
import { useTips } from '../../hooks/useTips';
import { findInLibrary, parseNames, type LibraryCharacter } from './wizardLogic';
import { storyNames, swapNames } from './swapLogic';

/** Story step: replace the people in a pasted story with library characters. */
export function CastSwap({ storyText, cast, library, disabled, onApply }: {
  storyText: string;
  cast: string[];
  library: LibraryCharacter[];
  disabled?: boolean;
  onApply: (storyText: string, cast: string[]) => void;
}) {
  const w = useTranslation().t.wizard.story;
  const tip = useTips().wizard.story;
  const [swaps, setSwaps] = useState<Record<string, string>>({});
  const [extra, setExtra] = useState<string[]>([]);
  const [typed, setTyped] = useState('');
  const [undo, setUndo] = useState<{ before: string; cast: string[]; after: string; n: number } | null>(null);

  const found = useMemo(() => storyNames(storyText), [storyText]);
  const names = useMemo(() => parseNames([...found, ...extra].join(',')), [found, extra]);
  const picked = Object.entries(swaps).filter(([from, to]) => to && names.includes(from));

  const addName = () => {
    const name = typed.trim();
    if (!name) return;
    setExtra(x => [...x, name]);
    setTyped('');
  };

  const apply = () => {
    const chosen = Object.fromEntries(picked);
    const next = swapNames(storyText, chosen);
    const targets = Object.values(chosen);
    // the swapped-out names are gone from the story; the library ones are now in it
    const gone = new Set(Object.keys(chosen).map(n => n.toLowerCase()));
    const nextCast = parseNames([...cast.filter(n => !gone.has(n.toLowerCase())), ...targets].join(','));
    setUndo({ before: storyText, cast, after: next, n: picked.length });
    setSwaps({});
    setExtra([]);
    onApply(next, nextCast);
  };

  const canUndo = undo && undo.after === storyText;

  return (
    <div className="wizard-field" data-tour="wizard-swap">
      <span>{w.swap} <em className="text-muted">({w.optional})</em></span>
      {names.length > 0 ? (
        <div className="wizard-swaps">
          {names.map(name => {
            const own = findInLibrary(name, library);
            return (
              <label key={name} className="wizard-swap-row">
                <span className="wizard-swap-from wizard-person">
                  {own?.image ? <img src={own.image} alt="" /> : <FiUser size={14} />}
                  {name}
                </span>
                <span aria-hidden className="text-muted">→</span>
                <select className="input select" value={swaps[name] || ''} disabled={disabled}
                  aria-label={fill(w.swapFor, { name })} data-tip={fill(tip.swapPick, { name })}
                  onChange={e => setSwaps(s => ({ ...s, [name]: e.target.value }))}>
                  <option value="">{w.swapKeep}</option>
                  {library.filter(c => c.name.trim().toLowerCase() !== name.toLowerCase()).map(c => (
                    <option key={c.id || c.name} value={c.name.trim()}>{c.name.trim()}</option>
                  ))}
                </select>
              </label>
            );
          })}
        </div>
      ) : (
        <span className="text-sm text-muted wizard-note">{w.swapNone}</span>
      )}
      <div className="wizard-swap-actions">
        <input className="input" value={typed} onChange={e => setTyped(e.target.value)} maxLength={40}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addName(); } }}
          placeholder={w.swapAddPlaceholder} disabled={disabled} data-tip={tip.swapAdd} />
        <button type="button" className="btn btn-ghost" onClick={addName} disabled={disabled || !typed.trim()}
          data-tip={tip.swapAdd}>
          <FiPlus size={14} /> {w.swapAdd}
        </button>
        <span className="wizard-swap-spacer" />
        {canUndo && (
          <button type="button" className="btn btn-ghost" disabled={disabled} data-tip={tip.swapUndo}
            onClick={() => { onApply(undo.before, undo.cast); setUndo(null); }}>
            <FiCornerUpLeft size={14} /> {w.swapUndo}
          </button>
        )}
        <button type="button" className="btn btn-secondary" onClick={apply} disabled={disabled || !picked.length}
          data-tip={tip.swapApply}>
          <FiRepeat size={14} /> {picked.length ? fill(w.swapApplyN, { n: picked.length }) : w.swapApply}
        </button>
      </div>
      <span className="text-sm text-muted wizard-note">
        {canUndo ? fill(w.swapDone, { n: undo.n }) : w.swapHint}
      </span>
    </div>
  );
}
