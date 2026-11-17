import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { FiBookOpen, FiCheck, FiCopy, FiCpu, FiEye, FiFileText, FiGrid, FiLayers, FiPlay, FiPlus, FiRefreshCw, FiSave, FiShuffle, FiSquare, FiTerminal, FiUpload, FiZap } from 'react-icons/fi';
import { useProjectStore } from '../../store/projectStore';
import { pinSeed } from './pinSeed';
import { AiRewrite, type AiTarget } from './AiRewrite';
import { OutlinePanel } from './OutlinePanel';
import { BatchDialog, type BatchStartBody } from './BatchDialog';
import { BatchReview } from './BatchReview';
import { applyAccepted, finished, mergeBatch, type Batch, type BatchResult } from './batchApply';
import { toApply, useBatchReview } from './batchDecisions';
import { parseOutline, targetAt, targetLabel, type OutlineEntry, type OutlineKind, type OutlineWords } from './outline';
import { useComicsDrafts, openedDraft, isDirty } from './scriptDrafts';
import { comicFiles, postUpload, uploaded, uploadSummary, type UploadResult } from './comicsUpload';
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

type View = 'script' | 'log' | 'pages' | 'panels' | 'batch';

const BATCH_URL = '/api/comics/rewrite-batch/current';
const BATCH_POLL_MS = 2000;

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

/** The outline's open state and tab, per browser (storage may be off: private mode, blocked site data). */
const OUTLINE_OPEN_KEY = 'automanga.comics.outline.open';
const OUTLINE_MODE_KEY = 'automanga.comics.outline.mode';
function readStored(key: string): string | null {
  try { return window.localStorage.getItem(key); } catch { return null; }
}
function writeStored(key: string, value: string) {
  try { window.localStorage.setItem(key, value); } catch { /* not kept: fine */ }
}

/** AI rewrite shortcuts in the editor: Mod+Shift+E the panel at the caret, Mod+Shift+L its scene. (Mod+Shift+S
    is "save as" / screenshots and Mod+Shift+P print / private window in some browsers; E and L are free in
    Chrome, Safari and Firefox on macOS.) */
const IS_MAC = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
const SHORTCUTS: Record<'panel' | 'scene', { code: string; label: string }> = {
  panel: { code: 'KeyE', label: IS_MAC ? '⌘⇧E' : 'Ctrl+Shift+E' },
  scene: { code: 'KeyL', label: IS_MAC ? '⌘⇧L' : 'Ctrl+Shift+L' },
};
const shortcutOf = (e: React.KeyboardEvent): 'panel' | 'scene' | null => {
  if (!(e.metaKey || e.ctrlKey) || !e.shiftKey || e.altKey) return null;
  for (const k of ['panel', 'scene'] as const) {
    const sc = SHORTCUTS[k];
    if (e.code === sc.code || e.key.toLowerCase() === sc.code.slice(3).toLowerCase()) return k;
  }
  return null;
};

/** Scroll the editor so `offset` sits a few lines below its top. Lines wrap in the textarea, so the height of the
    text before it is measured in a hidden copy of the editor; if that fails, the line number is used. */
function scrollEditorTo(ed: HTMLTextAreaElement, offset: number) {
  const cs = getComputedStyle(ed);
  const lh = parseFloat(cs.lineHeight) || 20;
  let top: number;
  try {
    const div = document.createElement('div');
    for (const prop of ['fontFamily', 'fontSize', 'fontWeight', 'fontStyle', 'lineHeight', 'letterSpacing', 'wordSpacing',
      'tabSize', 'textTransform', 'textIndent', 'paddingTop', 'paddingRight', 'paddingLeft'] as const) div.style[prop] = cs[prop];
    Object.assign(div.style, {
      position: 'absolute', visibility: 'hidden', left: '-10000px', top: '0', boxSizing: 'border-box', border: '0',
      width: `${ed.clientWidth}px`, whiteSpace: 'pre-wrap', overflowWrap: 'break-word', wordBreak: cs.wordBreak,
    });
    div.textContent = ed.value.slice(0, offset);
    const mark = document.createElement('span');
    mark.textContent = '\u200b';
    div.appendChild(mark);
    document.body.appendChild(div);
    top = mark.offsetTop - (parseFloat(cs.paddingTop) || 0);
    div.remove();
  } catch {
    top = (ed.value.slice(0, offset).split('\n').length - 1) * lh;
  }
  ed.scrollTop = Math.max(0, top - 3 * lh);
}

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
  const [viewState, setView] = useState<View>('script');
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
  const [uploadNotice, setUploadNotice] = useState<{ text: string; warn: boolean } | null>(null);
  const [dropping, setDropping] = useState(false);
  const uploadInput = useRef<HTMLInputElement>(null);
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
  const [ai, setAi] = useState<{ start: number; end: number; target?: AiTarget; seq: number } | null>(null);
  const aiSeq = useRef(0);
  // a run is going or a suggestion waits in the popover: the outline's AI buttons don't replace it then
  const [aiLocked, setAiLocked] = useState(false);
  const [llm, setLlm] = useState<{ endpoint: string; model: string } | null>(null);
  useEffect(() => {
    fetch('/api/settings/').then(r => (r.ok ? r.json() : null))
      .then(d => setLlm(d?.api ? { endpoint: d.api.endpoint || '', model: d.api.model || '' } : null))
      .catch(() => setLlm(null));
  }, []);
  const llmReady = !!(llm?.endpoint && llm.model);

  // Batch AI rewrite: the job lives on the server (one at a time, survives reloads); read once on open, followed
  // every 2 s while it runs. The owner's Accept/Reject choices are in useBatchReview.
  const [batch, setBatch] = useState<Batch | null>(null);
  const batchRef = useRef<Batch | null>(null);
  useEffect(() => { batchRef.current = batch; }, [batch]);
  const [batchDialog, setBatchDialog] = useState(false);
  // the batch view needs this script's batch (it may be cleared, or be another script's)
  const view: View = viewState === 'batch' && !(batch && batch.script === selected) ? 'script' : viewState;
  const [batchNotice, setBatchNotice] = useState<string | null>(null);
  const batchDecisions = useBatchReview(s => (batch ? s.decisions[batch.id] : undefined));
  const batchApplied = useBatchReview(s => (batch ? s.applied[batch.id] : undefined));
  useEffect(() => {
    fetch(BATCH_URL).then(r => (r.ok ? r.json() : null)).then(d => { if (d) setBatch(d.batch ?? null); }).catch(() => {});
  }, []);
  const batchRunning = batch?.status === 'running';
  const batchId = batch?.id;
  useEffect(() => {
    if (!batchRunning) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const poll = async () => {
      const cur = batchRef.current;
      if (!cur || cancelled) return;
      try {
        const { batch: next } = await json<{ batch: Batch | null }>(await fetch(`${BATCH_URL}?since=${cur.seq}`));
        if (cancelled) return;
        const merged = mergeBatch(cur, next);
        setBatch(merged);
        if (!merged || merged.id !== cur.id || merged.status !== 'running') return;
      } catch { /* the server restarts now and then; keep polling */ }
      if (!cancelled) timer = setTimeout(poll, BATCH_POLL_MS);
    };
    timer = setTimeout(poll, BATCH_POLL_MS);
    return () => { cancelled = true; if (timer) clearTimeout(timer); };
  }, [batchRunning, batchId]);

  // the outline: parsed from the editor text 200 ms after the last keystroke, the caret's entry 150 ms after it moves
  const [outlineText, setOutlineText] = useState(text);
  useEffect(() => {
    const timer = setTimeout(() => setOutlineText(text), 200);
    return () => clearTimeout(timer);
  }, [text]);
  const outline = useMemo(() => parseOutline(outlineText), [outlineText]);
  const [caretPos, setCaretPos] = useState(0);
  const caretTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (caretTimer.current) clearTimeout(caretTimer.current); }, []);
  const trackCaret = () => {
    if (caretTimer.current) clearTimeout(caretTimer.current);
    caretTimer.current = setTimeout(() => setCaretPos(editorRef.current?.selectionStart ?? 0), 150);
  };
  const [outlineOpen, setOutlineOpen] = useState(() => readStored(OUTLINE_OPEN_KEY) !== '0');
  const [outlineMode, setOutlineMode] = useState<OutlineKind>(() => {
    const m = readStored(OUTLINE_MODE_KEY);
    return m === 'page' || m === 'panel' ? m : 'scene';
  });
  const toggleOutline = useCallback(() => setOutlineOpen(o => { writeStored(OUTLINE_OPEN_KEY, o ? '0' : '1'); return !o; }), []);
  const pickMode = useCallback((m: OutlineKind) => { setOutlineMode(m); writeStored(OUTLINE_MODE_KEY, m); }, []);
  const c = t.comics;
  const words: OutlineWords = useMemo(() => ({
    page: c.outlinePage, uncutPage: c.outlineUncutPage, noPlace: c.outlineNoPlace, panel: c.outlinePanel, scene: c.outlineScene,
  }), [c]);

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
    setAi({ start: ed?.selectionStart ?? 0, end: ed?.selectionEnd ?? 0, seq: ++aiSeq.current });
  };

  /** Select a block in the editor and scroll it into view. */
  const selectRange = (start: number, end: number) => {
    setCaretPos(start);
    requestAnimationFrame(() => {
      const ed = editorRef.current;
      if (!ed) return;
      ed.focus();
      ed.setSelectionRange(start, end);
      scrollEditorTo(ed, start);
    });
  };

  /** Open the AI popover on an outline entry (or the block of `kind` at the caret). */
  const aiOn = (kind: OutlineKind, entry: OutlineEntry | null, anchor?: number) => {
    if (!llmReady || aiLocked) return;
    const at = anchor ?? entry?.startOffset ?? 0;
    const target: AiTarget = entry
      ? { kind, start: entry.startOffset, end: entry.endOffset, anchor: at, label: targetLabel({ kind, start: entry.startOffset, end: entry.endOffset, entry }, words) }
      : { kind, start: at, end: at, anchor: at, label: '' };
    setView('script');
    if (entry) selectRange(entry.startOffset, entry.endOffset);
    setAi({ start: at, end: at, target, seq: ++aiSeq.current });
  };

  // stable for the memoised outline panel: the latest handlers through a ref
  const handlers = useRef({ aiOn, selectRange });
  useEffect(() => { handlers.current = { aiOn, selectRange }; });
  const onOutlinePick = useCallback((_kind: OutlineKind, e: OutlineEntry) => handlers.current.selectRange(e.startOffset, e.endOffset), []);
  const onOutlineAi = useCallback((kind: OutlineKind, e: OutlineEntry) => handlers.current.aiOn(kind, e), []);
  const onAiLock = useCallback((locked: boolean) => setAiLocked(locked), []);
  const onOutlineBatch = useCallback(() => setBatchDialog(true), []);

  /** The shortcut's block at the caret, in the live text. */
  const aiAtCaret = (kind: 'panel' | 'scene') => {
    const ed = editorRef.current;
    const caret = ed?.selectionStart ?? 0;
    const tgt = targetAt(parseOutline(text), caret, kind);
    aiOn(kind, tgt?.entry ?? null, caret);
  };

  /** The Panels view's "AI rewrite": the plan panel's block in the script (by its line while the plan is current,
      else by its id). */
  const aiOnPlanPanel = (p: PlanPanel) => {
    const o = parseOutline(text);
    const entry = (!planStale && o.panels.find(x => x.line === p.line)) || o.panels.find(x => x.id === p.id) || null;
    if (entry) aiOn('panel', entry);
    else setError(`${p.id}: not found in the script; wait for the check to catch up`);
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
    setAiLocked(false);
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
      scrollEditorTo(ed, at);
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

  // .comic files from the upload button or dropped on the list; an existing script is replaced only after a confirm
  const upload = async (all: File[]) => {
    const files = comicFiles(all);
    if (!files.length) { if (all.length) setUploadNotice({ text: `${all.map(f => f.name).join(', ')}: not a .comic file`, warn: true }); return; }
    setUploadNotice(null);
    try {
      let results: UploadResult[] = await postUpload(files, false);
      const exists = results.filter(r => r.status === 'exists');
      if (exists.length) {
        const drafts = useComicsDrafts.getState().drafts;
        const dirty = exists.filter(r => isDirty(drafts[r.name!])).map(r => `${r.name}.comic`);
        let msg = fill(c.uploadReplace, { names: exists.map(r => `${r.name}.comic`).join(', ') });
        if (dirty.length) msg += fill(c.uploadReplaceDirty, { names: dirty.join(', ') });
        if (window.confirm(msg)) {
          const again = await postUpload(files.filter(f => exists.some(r => r.file === f.name)), true);
          results = results.map(r => (r.status === 'exists' && again.find(a => a.file === r.file)) || r);
        }
      }
      const done = results.filter(uploaded);
      // a replaced script's editor draft goes: it opens with the uploaded text
      const { setDraft: putDraft } = useComicsDrafts.getState();
      for (const r of done) if (r.status === 'replaced') putDraft(r.name!, { text: '', savedText: '' });
      setUploadNotice(uploadSummary(results, c));
      await loadScripts();
      const open = done.find(r => r.name === selected) ?? done[0];
      if (open) { await openScript(open.name!); setView('script'); }
    } catch (e) { setUploadNotice({ text: (e as Error).message, warn: true }); }
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

  const startBatch = async (body: BatchStartBody) => {
    if (!selected) return;
    let b: Batch;
    try {
      b = await json<Batch>(await fetch(`/api/comics/scripts/${selected}/rewrite-batch`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      }));
    } catch (e) {
      // another device may have started one: show it
      fetch(BATCH_URL).then(r => (r.ok ? r.json() : null)).then(d => { if (d) setBatch(d.batch ?? null); }).catch(() => {});
      throw e;
    }
    setBatch({ ...b, partial: false });
    setBatchDialog(false);
    setBatchNotice(null);
    setView('batch');
  };

  const stopBatch = async () => {
    try { await json(await fetch(`${BATCH_URL}/stop`, { method: 'POST' })); }
    catch (e) { setError((e as Error).message); }
  };

  const clearBatch = async () => {
    const id = batch?.id;
    try {
      await json(await fetch(BATCH_URL, { method: 'DELETE' }));
      if (id) useBatchReview.getState().forget(id);
      setBatch(null);
      setView('script');
    } catch (e) { setError((e as Error).message); }
  };

  /** "Apply N accepted to editor": into the editor text (unsaved), bottom-up; blocks whose text changed meanwhile are
      skipped and named. */
  const applyBatch = (results: BatchResult[]) => {
    if (!batch || !selected) return;
    const report = applyAccepted(text, results);
    if (report.applied.length) {
      setText(report.text);
      useBatchReview.getState().markApplied(batch.id, report.applied);
    }
    const reasons = { missing: c.batchSkipMissing, ambiguous: c.batchSkipAmbiguous, overlap: c.batchSkipOverlap, 'no-suggestion': c.batchSkipNone };
    const skipped = report.skipped.map(s => `${s.label || `#${s.index + 1}`} (${reasons[s.reason]})`).join('; ');
    setBatchNotice([fill(c.batchApplied, { n: report.applied.length }),
      report.skipped.length ? fill(c.batchSkipped, { n: report.skipped.length, list: skipped }) : ''].filter(Boolean).join(' '));
    setView('script');
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
  const shortcutHint = fill(c.aiShortcuts, { panel: SHORTCUTS.panel.label, scene: SHORTCUTS.scene.label });
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
  const batchHere = batch && batch.script === selected ? batch : null;
  const batchBlocked = !llmReady ? c.aiNoLlm
    : batchRunning && batch ? (batch.script === selected ? c.batchRunningHere : fill(c.batchRunningOther, { script: batch.script }))
      : null;
  const batchUnapplied = batch && !batchRunning ? toApply(batch.results, batchDecisions, batchApplied).length : 0;

  return (
    <div className="comics-tab">
      <aside className={`comics-list ${dropping ? 'dropping' : ''}`}
        onDragOver={e => { if (e.dataTransfer.types.includes('Files')) { e.preventDefault(); setDropping(true); } }}
        onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDropping(false); }}
        onDrop={e => { e.preventDefault(); setDropping(false); upload([...e.dataTransfer.files]); }}>
        <div className="comics-list-head">
          <span className="text-sm text-muted" title={comicsDir}>{scripts.length} scripts</span>
          <div className="flex gap-xs">
            <button className="btn btn-ghost btn-icon" onClick={loadScripts} title="Refresh"><FiRefreshCw size={14} /></button>
            <button className="btn btn-ghost btn-icon" onClick={() => uploadInput.current?.click()} title={c.uploadOpen} aria-label={c.uploadOpen}><FiUpload size={14} /></button>
            <button className="btn btn-secondary btn-icon" onClick={() => setNewName('')} title="New script"><FiPlus size={14} /></button>
            <input ref={uploadInput} type="file" accept=".comic,.txt" multiple hidden
              onChange={e => { upload([...(e.target.files ?? [])]); e.target.value = ''; }} />
          </div>
        </div>
        {dropping && <div className="comics-drop-hint">{c.uploadDrop}</div>}
        {uploadNotice && (
          <div className={`comics-upload-notice ${uploadNotice.warn ? 'warn' : ''}`} onClick={() => setUploadNotice(null)} title="Dismiss">
            {uploadNotice.text}
          </div>
        )}
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
            {batchNotice && <div className="comics-note" role="status" onClick={() => setBatchNotice(null)}>{batchNotice}</div>}
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
              {batchHere && (
                <button className={view === 'batch' ? 'active' : ''} onClick={() => setView('batch')} title={c.batchTabHint}>
                  <FiCpu size={13} /> {fill(c.batchTab, { a: finished(batchHere), b: batchHere.total })}{batchHere.status === 'running' ? ' …' : ''}
                </button>
              )}
              {view === 'script' && (
                <>
                  <button className="comics-save" onClick={openAi} disabled={!llmReady || !!ai}
                    title={llmReady ? `${t.comics.aiRewriteHint}\n${shortcutHint}` : t.comics.aiNoLlm}
                    aria-keyshortcuts={IS_MAC ? 'Meta+Shift+E Meta+Shift+L' : 'Control+Shift+E Control+Shift+L'}>
                    <FiZap size={13} /> {t.comics.aiRewrite}
                  </button>
                  <button onClick={() => save()} disabled={!dirty || scriptBusy}>
                    <FiSave size={13} /> Save
                  </button>
                </>
              )}
            </div>

            {view === 'script' && (
              <div className={`comics-script ${outlineOpen ? 'with-outline' : ''}`}>
                <OutlinePanel outline={outline} caret={caretPos} open={outlineOpen} onToggle={toggleOutline}
                  mode={outlineMode} onMode={pickMode} words={words}
                  aiBlocked={!llmReady ? c.aiNoLlm : aiLocked ? c.aiLocked : null}
                  onPick={onOutlinePick} onAi={onOutlineAi} onBatch={onOutlineBatch} batchBlocked={batchBlocked} />
                <div className="comics-editor-wrap">
                  <textarea
                    ref={editorRef}
                    className="comics-editor"
                    spellCheck={false}
                    value={text}
                    aria-label={current.name}
                    onChange={e => setText(e.target.value)}
                    onSelect={trackCaret}
                    onKeyDown={e => {
                      if ((e.metaKey || e.ctrlKey) && !e.shiftKey && e.key === 's') {
                        e.preventDefault();
                        if (dirty && !scriptBusy) save();   // the Save button's own check
                        return;
                      }
                      const sc = shortcutOf(e);
                      if (sc) {
                        e.preventDefault();
                        aiAtCaret(sc);
                      }
                    }}
                  />
                  {ai && (
                    <AiRewrite key={`${current.name}:${ai.seq}`} script={current.name} text={text} caret={ai} model={llm?.model ?? ''}
                      target={ai.target} words={words} onLockChange={onAiLock}
                      onAccept={acceptAi}
                      onClose={block => { setAi(null); setAiLocked(false); focusEditor(block?.start ?? ai.start); }} />
                  )}
                </div>
              </div>
            )}
            {batchDialog && (
              <BatchDialog text={text} words={words} model={llm?.model ?? ''} blocked={batchBlocked}
                replaces={batchUnapplied} onStart={startBatch} onClose={() => setBatchDialog(false)} />
            )}
            {view === 'batch' && batchHere && (
              <BatchReview batch={batchHere} editorText={text} onApply={applyBatch} onStop={stopBatch} onClear={clearBatch} />
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
                          <button className="btn btn-ghost comics-panel-ai" onClick={() => aiOnPlanPanel(p)}
                            disabled={!llmReady || aiLocked} title={!llmReady ? c.aiNoLlm : aiLocked ? c.aiLocked : c.aiPanelCardHint}
                            aria-label={fill(c.outlineAi, { label: `${c.outlinePanel} ${p.id}` })}>
                            <FiZap size={13} /> {c.aiPanelCard}
                          </button>
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
