import { useCallback, useEffect, useRef, useState } from 'react';
import { FiBookOpen, FiEye, FiFileText, FiLayers, FiPlay, FiPlus, FiRefreshCw, FiSave, FiSquare, FiTerminal } from 'react-icons/fi';
import { useProjectStore } from '../../store/projectStore';
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
}

interface Run {
  id: string;
  script: string;
  mode: 'paint' | 'no-paint' | 'dry-run';
  face: boolean;
  status: 'running' | 'done' | 'failed' | 'stopped';
  exit_code: number | null;
  started: number;
  ended: number | null;
  lines: string[];
  next: number;
  project_id: string | null;
}

interface PageImage { file: string; url: string; mtime: number }

type View = 'script' | 'log' | 'pages';

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

const MODE_LABEL = { 'paint': 'Paint & import', 'no-paint': 'Import (no painting)', 'dry-run': 'Dry run' };

async function json<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
  return body as T;
}

/** "painting 6 panels" then one "  1.2 56.3s" line per panel: progress of the paint step. */
function paintProgress(lines: string[]) {
  let total = 0, done = 0;
  for (const l of lines) {
    const m = l.match(/^painting (\d+) panels?/);
    if (m) { total = Number(m[1]); done = 0; }
    else if (total && /^\s+\d+\.\d+ (\d|variant|from variant)/.test(l)) done++;
  }
  return total ? { done, total } : null;
}

export function ComicsTab() {
  const { setCurrentProject, setComposerProjectId, loadProjectWithImages, setActiveTab } = useProjectStore();
  const [scripts, setScripts] = useState<Script[]>([]);
  const [comicsDir, setComicsDir] = useState('');
  const [listError, setListError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [text, setText] = useState('');
  const [savedText, setSavedText] = useState('');
  const [view, setView] = useState<View>('script');
  const [face, setFace] = useState(false);
  const [run, setRun] = useState<Run | null>(null);
  const [pages, setPages] = useState<PageImage[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [newName, setNewName] = useState<string | null>(null);
  const logRef = useRef<HTMLPreElement>(null);
  const runRef = useRef<Run | null>(null);
  runRef.current = run;

  const dirty = text !== savedText;
  const current = scripts.find(s => s.name === selected) || null;
  const running = run?.status === 'running';
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
      const data = await json<{ pages: PageImage[] }>(await fetch(`/api/comics/scripts/${name}/pages`));
      setPages(data.pages);
    } catch { setPages([]); }
  }, []);

  const openScript = useCallback(async (name: string) => {
    setError(null);
    try {
      const data = await json<Script & { text: string }>(await fetch(`/api/comics/scripts/${name}`));
      setSelected(name);
      setText(data.text);
      setSavedText(data.text);
      loadPages(name);
    } catch (e) { setError((e as Error).message); }
  }, [loadPages]);

  // on open: the scripts, and a run that may still be going (the page was reloaded mid-run)
  useEffect(() => {
    (async () => {
      const list = await loadScripts();
      const { run: r } = await json<{ run: Run | null }>(await fetch('/api/comics/runs/current'));
      if (r) { setRun(r); await openScript(r.script); if (r.status === 'running') setView('log'); }
      else if (list.length) await openScript(list[0].name);
    })().catch(e => setError((e as Error).message));
  }, [loadScripts, openScript]);

  // follow the run's log while it runs
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(async () => {
      const r = runRef.current;
      if (!r) return;
      try {
        const { run: next } = await json<{ run: Run | null }>(await fetch(`/api/comics/runs/current?since=${r.next}`));
        if (!next || next.id !== r.id) return;
        setRun({ ...next, lines: [...r.lines, ...next.lines] });
        if (next.status !== 'running') { loadScripts(); loadPages(next.script); }
      } catch { /* the server restarts now and then; keep polling */ }
    }, 1000);
    return () => clearInterval(timer);
  }, [running, loadScripts, loadPages]);

  useEffect(() => {
    if (view === 'log' && logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [run?.lines.length, view]);

  const save = async () => {
    if (!selected) return false;
    try {
      await json(await fetch(`/api/comics/scripts/${selected}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }),
      }));
      setSavedText(text);
      loadScripts();
      return true;
    } catch (e) { setError((e as Error).message); return false; }
  };

  const start = async (mode: Run['mode']) => {
    if (!selected) return;
    setError(null);
    if (dirty && !(await save())) return;
    try {
      const r = await json<Run>(await fetch('/api/comics/runs', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ script: selected, mode, face }),
      }));
      setRun(r);
      setView('log');
    } catch (e) { setError((e as Error).message); }
  };

  const stop = async () => {
    try { await json(await fetch('/api/comics/runs/current/stop', { method: 'POST' })); }
    catch (e) { setError((e as Error).message); }
  };

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
    if (dirty && !window.confirm('Discard your unsaved changes to this script?')) return;
    openScript(name);
    setView(run?.script === name && run.status === 'running' ? 'log' : 'script');
  };

  const openInComposer = async (projectId: string) => {
    try {
      const data = await json<{ project: any }>(await fetch(`/api/projects/load/${projectId}`));
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
  const projectId = (runIsHere && run?.project_id) || current?.project_id || null;
  const elapsed = run ? Math.round(((run.ended ?? Date.now() / 1000) - run.started)) : 0;

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

            {runIsHere && run && (
              <div className={`comics-status comics-status-${run.status}`}>
                <span>
                  {MODE_LABEL[run.mode]}{run.face ? ' + face pass' : ''}: {
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
              {view === 'script' && (
                <button className="comics-save" onClick={save} disabled={!dirty || Boolean(running && runIsHere)}>
                  <FiSave size={13} /> Save
                </button>
              )}
            </div>

            {view === 'script' && (
              <textarea
                className="comics-editor"
                spellCheck={false}
                value={text}
                onChange={e => setText(e.target.value)}
                onKeyDown={e => { if ((e.metaKey || e.ctrlKey) && e.key === 's') { e.preventDefault(); save(); } }}
              />
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
          </>
        )}
      </section>
    </div>
  );
}
