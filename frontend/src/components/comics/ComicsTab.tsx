import { useCallback, useEffect, useRef, useState } from 'react';
import { FiBookOpen, FiCheck, FiCopy, FiEye, FiFileText, FiGrid, FiLayers, FiPlay, FiPlus, FiRefreshCw, FiSave, FiShuffle, FiSquare, FiTerminal, FiZap } from 'react-icons/fi';
import { useProjectStore } from '../../store/projectStore';
import { pinSeed } from './pinSeed';
import { AiRewrite } from './AiRewrite';
import { useComicsDrafts, openedDraft } from './scriptDrafts';
import { fill, useTranslation } from '../../hooks/useTranslation';
import type { Project } from '../../types';
import './comics.css';

interface Script {
  name: string;
  title: string;
  subtitle: string | null;
  pages: number;
  panels: number;
  painted: number;
  project_id: string | null;
  updated: string;
  uncut?: number;                     // PAGE uncut / PANEL uncut blocks in the saved script
  uncut_slots?: number;               // of them, todo slots not written yet
  uncut_project_id?: string | null;   // the uncut edition's AutoManga project
}

interface Run {
  id: string;
  script: string;
  mode: 'paint' | 'no-paint' | 'dry-run' | 'repaint' | 'variants';
  face: boolean;
  uncut?: boolean;
  status: 'running' | 'done' | 'failed' | 'stopped';
  exit_code: number | null;
  started: number;
  ended: number | null;
  lines: string[];
  next: number;
  project_id: string | null;
}

interface PageImage { file: string; url: string; mtime: number }

/** One panel of comic.js --plan. */
interface PlanPanel {
  id: string;
  page: number;
  n: number;
  line: number;
  seedLine: number | null;
  seed: number;
  seedPinned: boolean;
  gen: [number, number];
  model: string;
  face: boolean;
  prompt: string;
  negative: string;
  fix: string | null;
  painted: boolean;
  current: boolean;    // painted from this prompt and seed
  prev: boolean;
  mtime: number | null;
  variants: { seed: number; same: boolean; mtime?: number }[];   // same: painted from this prompt, so pinning it reuses the image
  // --plan --uncut only
  edition?: 'regular' | 'uncut';
  stem?: string;       // its file: p01-02, p01-u01, u01-02
  regular?: boolean;   // the regular edition's painting of it is copied in, not painted again
  rating?: 'sfw' | 'mature';
  notice?: string;
}

interface UncutSlot { line: number; kind: 'page' | 'panel'; id: string; cast?: string[] }

type Plan = { ok: true; panels: PlanPanel[]; edition?: 'uncut'; slots?: UncutSlot[] } | { ok: false; error: string; line: number | null };

type View = 'script' | 'log' | 'pages' | 'panels';

const NEW_SCRIPT = `// A new comic. Format: see the Comics repo README.
title: Untitled
seed: 1000

PAGE
layout: 1-2

PANEL h=1.2
place: cafe, morning
shot: establishing
A small coffee shop in the morning.
CAPTION: Monday.

PANEL
shot: medium
Describe the picture here.

PANEL
shot: closeup
Describe the picture here.
`;

const MODE_LABEL = {
  'paint': 'Paint & import', 'no-paint': 'Import (no painting)', 'dry-run': 'Dry run',
  'repaint': 'Repaint & import', 'variants': 'Seed variants',
};

/** The run log kept in the browser: the last lines only (a long paint prints thousands). */
const MAX_LOG_LINES = 2000;
const capLog = (lines: string[]) => (lines.length > MAX_LOG_LINES ? lines.slice(-MAX_LOG_LINES) : lines);

const pad2 = (n: number) => String(n).padStart(2, '0');
const panelStem = (p: PlanPanel) => p.stem ?? `p${pad2(p.page)}-${pad2(p.n)}`;
/** A pinned seed with a variant painted from the current prompt, not yet in the panel: "Apply pinned" copies it. */
const pinnedPending = (p: PlanPanel) => p.seedPinned && !p.current && p.variants.some(v => v.seed === p.seed && v.same);

async function json<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
  return body as T;
}

/** "painting 6 panels" then one "  1.2 56.3s" line per panel: progress of the paint step. With --variants (named
    in the log's first line, the command) each panel prints one line per variant. */
function paintProgress(lines: string[]) {
  let total = 0, done = 0;
  const per = Number(lines[0]?.match(/--variants (\d+)/)?.[1] || 1);
  for (const l of lines) {
    const m = l.match(/^painting (\d+) panels?/);
    if (m) { total = Number(m[1]) * per; done = 0; }
    else if (total && /^\s+u?\d+\.u?\d+ (\d|variant|from variant)/.test(l)) done++;
  }
  return total ? { done, total } : null;
}

export function ComicsTab() {
  const { setCurrentProject, setComposerProjectId, loadProjectWithImages, setActiveTab } = useProjectStore();
  const { t } = useTranslation();
  const [scripts, setScripts] = useState<Script[]>([]);
  const [comicsDir, setComicsDir] = useState('');
  const [listError, setListError] = useState<string | null>(null);
  // the open script and its editor text live in a store: they survive tab and script switches
  const selected = useComicsDrafts(s => s.selected);
  const setDraft = useComicsDrafts(s => s.setDraft);
  const draft = useComicsDrafts(s => (s.selected ? s.drafts[s.selected] : undefined));
  const text = draft?.text ?? '';
  const savedText = draft?.savedText ?? '';
  const setText = (value: string) => { if (selected) setDraft(selected, { text: value }); };
  const [view, setView] = useState<View>('script');
  const [face, setFace] = useState(false);
  // the uncut edition: runs, the plan, the pages and the panels are its own (out/<name>-uncut/)
  const [uncut, setUncut] = useState(false);
  const uncutRef = useRef(uncut);
  useEffect(() => { uncutRef.current = uncut; }, [uncut]);
  const edQuery = uncut ? 'uncut=1&' : '';
  const [run, setRun] = useState<Run | null>(null);
  const [pages, setPages] = useState<PageImage[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [newName, setNewName] = useState<string | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [planText, setPlanText] = useState<string | null>(null);   // the editor text the plan was made from
  const [planTick, setPlanTick] = useState(0);   // bump to re-plan the same text (after a run, a pin)
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const logRef = useRef<HTMLPreElement>(null);
  const editorRef = useRef<HTMLTextAreaElement>(null);
  const runRef = useRef<Run | null>(null);
  useEffect(() => { runRef.current = run; }, [run]);
  const selectedRef = useRef<string | null>(selected);
  useEffect(() => { selectedRef.current = selected; }, [selected]);
  // AI rewrite: the editor selection it opened on, and the LLM from Settings (endpoint + model)
  const [ai, setAi] = useState<{ start: number; end: number } | null>(null);
  const [llm, setLlm] = useState<{ endpoint: string; model: string } | null>(null);
  useEffect(() => {
    fetch('/api/settings/').then(r => (r.ok ? r.json() : null))
      .then(d => setLlm(d?.api ? { endpoint: d.api.endpoint || '', model: d.api.model || '' } : null))
      .catch(() => setLlm(null));
  }, []);
  const llmReady = !!(llm?.endpoint && llm.model);

  const dirty = text !== savedText;
  // the plan was made from other text (typing, or the 600 ms check hasn't caught up): its line numbers
  // and panel ids may be off, so the buttons acting on them wait for the next check
  const planStale = planText !== text;
  const current = scripts.find(s => s.name === selected) || null;
  const running = run?.status === 'running';
  // the run's elapsed time ticks from a clock state, not a Date.now() during render
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(timer);
  }, [running]);
  const runIsHere = run && run.script === selected;

  const loadScripts = useCallback(async () => {
    try {
      const data = await json<{ comics_dir: string; scripts: Script[] }>(await fetch('/api/comics/scripts'));
      setScripts(data.scripts);
      setComicsDir(data.comics_dir);
      setListError(null);
      return data.scripts;
    } catch (e) {
      setListError((e as Error).message);
      return [];
    }
  }, []);

  const loadPages = useCallback(async (name: string) => {
    try {
      const data = await json<{ pages: PageImage[] }>(await fetch(`/api/comics/scripts/${name}/pages${uncutRef.current ? '?uncut=1' : ''}`));
      setPages(data.pages);
    } catch { setPages([]); }
  }, []);

  const openScript = useCallback(async (name: string) => {
    setError(null);
    try {
      const data = await json<Script & { text: string }>(await fetch(`/api/comics/scripts/${name}`));
      const { drafts, setDraft: putDraft, setSelected: select } = useComicsDrafts.getState();
      putDraft(name, openedDraft(drafts[name], data.text));
      select(name);
      setPlan(null);
      setPlanText(null);
      setPicked(new Set());
      setAi(null);
      loadPages(name);
    } catch (e) { setError((e as Error).message); }
  }, [loadPages]);

  // on open: the scripts, and a run that may still be going (the page was reloaded mid-run)
  useEffect(() => {
    (async () => {
      const list = await loadScripts();
      const { run: r } = await json<{ run: Run | null }>(await fetch('/api/comics/runs/current'));
      if (r) setRun({ ...r, lines: capLog(r.lines) });
      // back on the tab: the script that was open (its unsaved edits are kept), else the run's, else the first
      const remembered = useComicsDrafts.getState().selected;
      const name = remembered && list.some(s => s.name === remembered) ? remembered : r?.script ?? list[0]?.name;
      if (!name) return;
      await openScript(name);
      if (r && r.script === name && r.status === 'running') setView('log');
    })().catch(e => setError((e as Error).message));
  }, [loadScripts, openScript]);

  // follow the run's log while it runs. A setTimeout chain (not setInterval)
  // so one poll's response always lands before the next request goes out.
  useEffect(() => {
    if (!running) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const finished = (r: Run) => {
      loadScripts(); setPlanTick(t => t + 1);
      // the pages of the run's script, if it is still the one open
      if (r.script === selectedRef.current) loadPages(r.script);
      if (r.mode === 'repaint' || r.mode === 'variants') setView(v => (v === 'log' && r.status === 'done' ? 'panels' : v));
    };
    const poll = async () => {
      const r = runRef.current;
      if (!r || cancelled) return;
      try {
        const { run: next } = await json<{ run: Run | null }>(await fetch(`/api/comics/runs/current?since=${r.next}`));
        if (cancelled) return;
        if (next && next.id === r.id) {
          setRun({ ...next, lines: capLog([...r.lines, ...next.lines]) });
          if (next.status !== 'running') { finished(next); return; }
        } else {
          // the server no longer reports this run as current: it has ended.
          // Refresh once (full log); if it's still unknown, give up on it.
          const { run: full } = await json<{ run: Run | null }>(await fetch('/api/comics/runs/current'));
          if (cancelled) return;
          if (full && full.id === r.id) {
            setRun({ ...full, lines: capLog(full.lines) });
            if (full.status !== 'running') { finished(full); return; }
          } else {
            setRun({
              ...r,
              status: 'failed',
              ended: r.ended ?? Date.now() / 1000,
              lines: [...r.lines, '[the server lost track of this run]'],
            });
            setError('The server lost track of this run');
            finished(r);
            return;
          }
        }
      } catch { /* the server restarts now and then; keep polling */ }
      if (!cancelled) timer = setTimeout(poll, 1000);
    };
    timer = setTimeout(poll, 1000);
    return () => { cancelled = true; if (timer) clearTimeout(timer); };
  }, [running, loadScripts, loadPages]);

  // live check: comic.js --plan on the editor text, 600 ms after the last keystroke; a newer request aborts an older
  useEffect(() => {
    if (!selected) return;
    const ctl = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const p = await json<Plan>(await fetch(`/api/comics/scripts/${selected}/plan`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text, face, uncut }), signal: ctl.signal,
        }));
        if (!ctl.signal.aborted) { setPlan(p); setPlanText(text); }
      } catch (e) {
        if (!ctl.signal.aborted) { setPlan({ ok: false, error: (e as Error).message, line: null }); setPlanText(text); }
      }
    }, 600);
    return () => { clearTimeout(timer); ctl.abort(); };
  }, [selected, text, face, uncut, planTick]);

  // another edition: its pages (its panel ids are its own too: the toggle clears the selection)
  useEffect(() => {
    if (selectedRef.current) loadPages(selectedRef.current);
  }, [uncut, loadPages]);

  useEffect(() => {
    if (view === 'log' && logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [run?.lines.length, view]);

  const save = async (body = text) => {
    if (!selected) return false;
    const name = selected;   // the script being saved, even if another is opened meanwhile
    try {
      await json(await fetch(`/api/comics/scripts/${name}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: body }),
      }));
      setDraft(name, { savedText: body });
      loadScripts();
      return true;
    } catch (e) { setError((e as Error).message); return false; }
  };

  const start = async (mode: Run['mode'], extra: { panels?: string[]; force?: boolean; variants?: number } = {}) => {
    if (!selected) return;
    setError(null);
    if (dirty && !(await save())) return;
    try {
      const r = await json<Run>(await fetch('/api/comics/runs', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ script: selected, mode, face, uncut, ...extra }),
      }));
      setRun(r);
      setView('log');
    } catch (e) { setError((e as Error).message); }
  };

  const stop = async () => {
    try { await json(await fetch('/api/comics/runs/current/stop', { method: 'POST' })); }
    catch (e) { setError((e as Error).message); }
  };

  /** "Use seed N": pin it in the script, save, and re-plan (the variant then shows as pinned). */
  const chooseSeed = async (p: PlanPanel, seed: number) => {
    setError(null);
    if (planStale) { setError(`${p.id}: the script changed since the check; wait for it to catch up`); return; }
    let next: string;
    try { next = pinSeed(text, p, seed); } catch (e) { setError(`${p.id}: ${(e as Error).message}; wait for the check to catch up`); return; }
    setText(next);
    if (await save(next)) setPlanTick(t => t + 1);
  };

  const openAi = () => {
    const ed = editorRef.current;
    setAi({ start: ed?.selectionStart ?? 0, end: ed?.selectionEnd ?? 0 });
  };

  /** Back in the editor after the AI popover, the cursor at the block (selecting it after an accept). */
  const focusEditor = (start: number, end = start) => {
    requestAnimationFrame(() => {
      const ed = editorRef.current;
      if (!ed) return;
      ed.focus();
      ed.setSelectionRange(start, end);
    });
  };

  const acceptAi = (start: number, end: number, replacement: string) => {
    setText(text.slice(0, start) + replacement + text.slice(end));
    setAi(null);
    focusEditor(start, start + replacement.length);
  };

  /** Show a line of the script in the editor and put the cursor on it. */
  const gotoLine = (line: number) => {
    setView('script');
    requestAnimationFrame(() => {
      const ed = editorRef.current;
      if (!ed) return;
      const lines = ed.value.split('\n');
      const at = lines.slice(0, line - 1).reduce((n, l) => n + l.length + 1, 0);
      ed.focus();
      ed.setSelectionRange(at, at + (lines[line - 1]?.length ?? 0));
      const lh = parseFloat(getComputedStyle(ed).lineHeight) || 20;
      ed.scrollTop = Math.max(0, (line - 4) * lh);
    });
  };

  const togglePick = (id: string) => setPicked(prev => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  const copy = (s: string) => { navigator.clipboard?.writeText(s).catch(() => setError('Could not copy')); };

  const create = async () => {
    const name = (newName || '').trim().toLowerCase().replace(/\s+/g, '-');
    if (!/^[a-z0-9][a-z0-9_-]{0,80}$/.test(name)) { setError('Use letters, digits, - and _ for the name'); return; }
    if (scripts.some(s => s.name === name)) { setError(`${name}.comic already exists`); return; }
    try {
      await json(await fetch(`/api/comics/scripts/${name}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: NEW_SCRIPT }),
      }));
      setNewName(null);
      await loadScripts();
      await openScript(name);
      setView('script');
    } catch (e) { setError((e as Error).message); }
  };

  const select = (name: string) => {
    if (name === selected) return;
    // no confirm: the draft of this script stays in useComicsDrafts and comes back when it is reopened
    openScript(name);
    setView(run?.script === name && run.status === 'running' ? 'log' : 'script');
  };

  const openInComposer = async (projectId: string) => {
    try {
      const data = await json<{ project: Project }>(await fetch(`/api/projects/load/${projectId}`));
      setCurrentProject(data.project);
      setComposerProjectId(projectId);
      loadProjectWithImages(projectId);
      setActiveTab('composer');
    } catch (e) { setError((e as Error).message); }
  };

  if (listError) {
    return (
      <div className="empty-state">
        <FiBookOpen size={48} />
        <h3>Comics repo not found</h3>
        <p>{listError}</p>
      </div>
    );
  }

  const progress = runIsHere && run ? paintProgress(run.lines) : null;
  const projectId = (runIsHere && Boolean(run?.uncut) === uncut && run?.project_id)
    || (uncut ? current?.uncut_project_id : current?.project_id) || null;
  const elapsed = run ? Math.round(((run.ended ?? Math.max(now, run.started)) - run.started)) : 0;
  const planPanels = plan?.ok ? plan.panels : [];
  const stale = planPanels.filter(p => p.painted && !p.current).length;
  const unpainted = planPanels.filter(p => !p.painted).length;
  const pinned = planPanels.filter(pinnedPending).map(p => p.id);
  const pickedIds = planPanels.filter(p => picked.has(p.id)).map(p => p.id);   // in script order, still existing
  const scriptBusy = Boolean(running && runIsHere);
  // variant files carry no mtime in older comic.js --plan output: the last run's end busts the cache
  const variantStamp = Math.floor(run?.ended ?? run?.started ?? 0);

  return (
    <div className="comics-tab">
      <aside className="comics-list">
        <div className="comics-list-head">
          <span className="text-sm text-muted" title={comicsDir}>{scripts.length} scripts</span>
          <div className="flex gap-xs">
            <button className="btn btn-ghost btn-icon" onClick={loadScripts} title="Refresh"><FiRefreshCw size={14} /></button>
            <button className="btn btn-secondary btn-icon" onClick={() => setNewName('')} title="New script"><FiPlus size={14} /></button>
          </div>
        </div>
        {newName !== null && (
          <form className="comics-new" onSubmit={e => { e.preventDefault(); create(); }}>
            <input className="input" autoFocus placeholder="file name, e.g. rooftop-static" value={newName}
              onChange={e => setNewName(e.target.value)} onKeyDown={e => e.key === 'Escape' && setNewName(null)} />
            <button className="btn btn-primary" type="submit">Create</button>
          </form>
        )}
        {scripts.map(s => (
          <button key={s.name} className={`comics-item ${s.name === selected ? 'active' : ''}`} onClick={() => select(s.name)}>
            <span className="comics-item-title">{s.title}</span>
            {s.subtitle && <span className="comics-item-sub">{s.subtitle}</span>}
            <span className="comics-item-meta">
              {s.name}.comic · {s.pages}p · {s.painted}/{s.panels} painted
              {!!s.uncut_slots && <span className="comics-uncut-slots" title={t.comics.uncutSlotsHint}> · {fill(t.comics.uncutSlots, { n: s.uncut_slots })}</span>}
              {run?.script === s.name && run.status === 'running' && <span className="comics-dot" title="Running" />}
            </span>
          </button>
        ))}
      </aside>

      <section className="comics-main">
        {!current ? (
          <div className="empty-state">
            <FiFileText size={48} />
            <h3>No script selected</h3>
            <p>Pick a script on the left, or create one.</p>
          </div>
        ) : (
          <>
            <div className="comics-toolbar">
              <div className="comics-title">
                <h2>{current.title}{current.subtitle && <small> · {current.subtitle}</small>}</h2>
                <span className="text-sm text-muted">
                  {current.pages} pages · {current.panels} panels · {current.painted} painted
                  {current.project_id && ' · in AutoManga'}
                </span>
              </div>
              <div className="comics-actions">
                <label className="comics-check" title="A second pass on the face of single-character panels">
                  <input type="checkbox" checked={face} onChange={e => setFace(e.target.checked)} disabled={running} /> Face pass
                </label>
                <label className="comics-check" title={t.comics.uncutEditionHint}>
                  <input type="checkbox" checked={uncut} onChange={e => { setUncut(e.target.checked); setPicked(new Set()); }} disabled={running} /> {t.comics.uncutEdition}
                </label>
                <button className="btn btn-secondary" onClick={() => start('dry-run')} disabled={running} title="Lay out with placeholders; no painting, nothing sent to AutoManga">
                  <FiEye size={14} /> Dry run
                </button>
                <button className="btn btn-secondary" onClick={() => start('no-paint')} disabled={running} title="Use the panels already painted; unpainted ones stay empty">
                  <FiLayers size={14} /> Import
                </button>
                <button className="btn btn-primary" onClick={() => start('paint')} disabled={running} title="Paint missing or changed panels on SwarmUI, then import">
                  <FiPlay size={14} /> Paint & import
                </button>
                {running && runIsHere && (
                  <button className="btn btn-secondary comics-stop" onClick={stop}><FiSquare size={14} /> Stop</button>
                )}
                {projectId && !running && (
                  <button className="btn btn-secondary" onClick={() => openInComposer(projectId)}>
                    <FiBookOpen size={14} /> Open in Composer
                  </button>
                )}
              </div>
            </div>

            {error && <div className="comics-error" onClick={() => setError(null)}>{error}</div>}
            {running && !runIsHere && run && (
              <div className="comics-note">Converting <b>{run.script}</b>; one run at a time.</div>
            )}

            {plan && (plan.ok ? (
              <div className="comics-plan comics-plan-ok">
                <FiCheck size={13} /> {planPanels.length} panels
                {stale > 0 && <> · {stale} stale</>}
                {unpainted > 0 && <> · {unpainted} unpainted</>}
                {pinned.length > 0 && <> · {pinned.length} pinned to apply</>}
                {plan.edition === 'uncut' && !!plan.slots?.length && (
                  <span title={t.comics.uncutSlotsHint}> · {fill(t.comics.uncutSlots, { n: plan.slots.length })}</span>
                )}
              </div>
            ) : (
              <button className="comics-plan comics-plan-error" disabled={plan.line == null}
                onClick={() => plan.line != null && gotoLine(plan.line)} title={plan.line != null ? 'Go to the line' : undefined}>
                {plan.line != null && <b>line {plan.line}</b>} {plan.error.replace(/^[^\n]*?:\d+: /, '')}
              </button>
            ))}

            {runIsHere && run && (
              <div className={`comics-status comics-status-${run.status}`}>
                <span>
                  {MODE_LABEL[run.mode]}{run.face ? ' + face pass' : ''}{run.uncut ? ` · ${t.comics.uncutEdition}` : ''}: {
                    run.status === 'running' ? (progress ? `painting ${progress.done}/${progress.total}` : 'running')
                      : run.status === 'done' ? 'done' : run.status === 'stopped' ? 'stopped' : `failed (exit ${run.exit_code})`
                  } · {Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, '0')}
                </span>
                {progress && run.status === 'running' && (
                  <div className="comics-progress"><div style={{ width: `${(100 * progress.done) / progress.total}%` }} /></div>
                )}
              </div>
            )}

            <div className="comics-views">
              <button className={view === 'script' ? 'active' : ''} onClick={() => setView('script')}>
                <FiFileText size={13} /> Script{dirty ? ' •' : ''}
              </button>
              <button className={view === 'log' ? 'active' : ''} onClick={() => setView('log')} disabled={!runIsHere}>
                <FiTerminal size={13} /> Log
              </button>
              <button className={view === 'pages' ? 'active' : ''} onClick={() => { setView('pages'); loadPages(current.name); }}>
                <FiEye size={13} /> Pages{pages.length ? ` (${pages.length})` : ''}
              </button>
              <button className={view === 'panels' ? 'active' : ''} onClick={() => setView('panels')}>
                <FiGrid size={13} /> Panels{stale ? ` (${stale} stale)` : ''}
              </button>
              {view === 'script' && (
                <>
                  <button className="comics-save" onClick={openAi} disabled={!llmReady || !!ai}
                    title={llmReady ? t.comics.aiRewriteHint : t.comics.aiNoLlm}>
                    <FiZap size={13} /> {t.comics.aiRewrite}
                  </button>
                  <button onClick={() => save()} disabled={!dirty || scriptBusy}>
                    <FiSave size={13} /> Save
                  </button>
                </>
              )}
            </div>

            {view === 'script' && (
              <div className="comics-editor-wrap">
                <textarea
                  ref={editorRef}
                  className="comics-editor"
                  spellCheck={false}
                  value={text}
                  onChange={e => setText(e.target.value)}
                  onKeyDown={e => {
                    if ((e.metaKey || e.ctrlKey) && e.key === 's') {
                      e.preventDefault();
                      if (dirty && !scriptBusy) save();   // the Save button's own check
                    }
                  }}
                />
                {ai && (
                  <AiRewrite key={current.name} script={current.name} text={text} caret={ai} model={llm?.model ?? ''}
                    onAccept={acceptAi}
                    onClose={block => { setAi(null); focusEditor(block?.start ?? ai.start); }} />
                )}
              </div>
            )}
            {view === 'log' && runIsHere && run && (
              <pre className="comics-log" ref={logRef}>{run.lines.join('\n')}</pre>
            )}
            {view === 'pages' && (
              pages.length ? (
                <div className="comics-pages">
                  {pages.map(p => (
                    <a key={p.file} href={`${p.url}?v=${p.mtime}`} target="_blank" rel="noreferrer" title={p.file}>
                      <img src={`${p.url}?v=${p.mtime}`} alt={p.file} loading="lazy" />
                      <span>{p.file.replace('.png', '')}</span>
                    </a>
                  ))}
                </div>
              ) : (
                <div className="empty-state"><FiEye size={40} /><h3>No pages yet</h3><p>Run a dry run or an import to render them.</p></div>
              )
            )}
            {view === 'panels' && (
              !plan?.ok ? (
                <div className="empty-state"><FiGrid size={40} /><h3>{plan ? 'The script has an error' : 'Checking the script…'}</h3>
                  <p>{plan ? 'Fix it (see above) to see its panels.' : ''}</p></div>
              ) : (
                <>
                  <div className="comics-panel-actions">
                    <label className="comics-check">
                      <input type="checkbox" checked={pickedIds.length > 0 && pickedIds.length === planPanels.length}
                        onChange={e => setPicked(new Set(e.target.checked ? planPanels.map(p => p.id) : []))} />
                      {pickedIds.length ? `${pickedIds.length} selected` : 'Select all'}
                    </label>
                    <button className="btn btn-secondary" disabled={running || planStale || !pickedIds.length}
                      onClick={() => start('repaint', { panels: pickedIds, force: true })} title="Paint the selected panels again, even if they are current, then import">
                      <FiRefreshCw size={14} /> Repaint selected
                    </button>
                    {[2, 4, 6].map(n => (
                      <button key={n} className="btn btn-secondary" disabled={running || planStale || !pickedIds.length}
                        onClick={() => start('variants', { panels: pickedIds, variants: n })} title={`Paint ${n} seeds of each selected panel to choose from (nothing is imported)`}>
                        <FiShuffle size={14} /> Variants ×{n}
                      </button>
                    ))}
                    <button className="btn btn-primary" disabled={running || planStale || !pinned.length}
                      onClick={() => start('repaint', { panels: pinned })} title="Put the pinned variants into their panels (no painting), then import">
                      <FiCheck size={14} /> Apply pinned{pinned.length ? ` (${pinned.length})` : ''}
                    </button>
                  </div>
                  <div className="comics-pages comics-panels">
                    {planPanels.map(p => {
                      // not painted in the uncut edition yet, but copied from the regular one on the next run: show that
                      const fromRegular = uncut && !p.painted && !!p.regular;
                      const url = `/api/comics/scripts/${current.name}/panel/${panelStem(p)}.png?${fromRegular ? '' : edQuery}v=${p.mtime}`;
                      return (
                        <div key={p.id} className={`comics-panel ${picked.has(p.id) ? 'picked' : ''}`}>
                          <div className="comics-panel-thumb" style={{ aspectRatio: `${p.gen[0]} / ${p.gen[1]}` }} onClick={() => togglePick(p.id)}>
                            {p.painted || fromRegular ? <img src={url} alt={p.id} loading="lazy" /> : <span>not painted</span>}
                          </div>
                          <div className="comics-panel-head">
                            <label className="comics-check">
                              <input type="checkbox" checked={picked.has(p.id)} onChange={() => togglePick(p.id)} /> <b>{p.id}</b>
                            </label>
                            <span className="comics-badges">
                              <span className={`comics-badge ${p.seedPinned ? 'pinned' : ''}`} title={p.seedPinned ? 'Seed set in the script' : 'Seed from the base seed'}>
                                seed {p.seed}{p.seedPinned ? ' · pinned' : ''}
                              </span>
                              {p.painted && !p.current && <span className="comics-badge stale" title="Painted from an older prompt or seed">stale</span>}
                              {pinnedPending(p) && <span className="comics-badge pinned" title="Apply pinned copies the variant in">to apply</span>}
                              {p.edition === 'uncut' && <span className="comics-badge uncut" title={t.comics.uncutBadgeHint}>{t.comics.uncutBadge}</span>}
                              {fromRegular && <span className="comics-badge" title={t.comics.fromRegularHint}>{t.comics.fromRegular}</span>}
                              {p.notice && <span className="comics-badge stale" title={p.notice}>SFW</span>}
                            </span>
                          </div>
                          <details className="comics-panel-prompt">
                            <summary>Prompt</summary>
                            <dl>
                              <dt>prompt <button className="btn btn-ghost btn-icon" onClick={() => copy(p.prompt)} title="Copy"><FiCopy size={12} /></button></dt>
                              <dd>{p.prompt}</dd>
                              {p.fix && <><dt>pair fix</dt><dd>{p.fix}</dd></>}
                              <dt>negative <button className="btn btn-ghost btn-icon" onClick={() => copy(p.negative)} title="Copy"><FiCopy size={12} /></button></dt>
                              <dd>{p.negative}</dd>
                              <dt>model</dt><dd>{p.model}{p.face ? ' · face pass' : ''}</dd>
                              <dt>size</dt><dd>{p.gen.join('×')}</dd>
                            </dl>
                          </details>
                          {p.variants.length > 0 && (
                            <div className="comics-variants">
                              {p.variants.map(v => {
                                const chosen = p.seedPinned && v.seed === p.seed;
                                const variantUrl = `/api/comics/scripts/${current.name}/variant/${panelStem(p)}_seed${v.seed}.png?${edQuery}v=${v.mtime ?? variantStamp}`;
                                return (
                                  <figure key={v.seed} className={chosen ? 'chosen' : ''}>
                                    <a href={variantUrl} target="_blank" rel="noreferrer">
                                      <img src={variantUrl} alt={`seed ${v.seed}`} loading="lazy" />
                                    </a>
                                    <figcaption>
                                      {chosen ? <span>seed {v.seed} ✓</span> : (
                                        <button className="btn btn-ghost" disabled={scriptBusy || planStale} onClick={() => chooseSeed(p, v.seed)}
                                          title={v.same ? 'Pin this seed; Apply pinned then uses this picture' : 'Painted from an older prompt: pinning the seed repaints it'}>
                                          Use seed {v.seed}{v.same ? '' : ' *'}
                                        </button>
                                      )}
                                    </figcaption>
                                  </figure>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </>
              )
            )}
          </>
        )}
      </section>
    </div>
  );
}
