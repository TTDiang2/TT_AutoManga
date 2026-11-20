import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  FiArrowLeft, FiArrowRight, FiArrowUp, FiArrowDown, FiCheck, FiDownload, FiUpload,
  FiImage, FiLayers, FiPlus, FiRefreshCw, FiTrash2, FiZap, FiEdit3,
} from 'react-icons/fi';
import { useProjectStore } from '../../store/projectStore';
import { useTranslation, fill } from '../../hooks/useTranslation';
import { useTips } from '../../hooks/useTips';
import { useExportScale } from '../../hooks/useExportScale';
import type { Panel, Project } from '../../types';
import { useStoryImport } from '../storyboard/useStoryImport';
import {
  STEPS, STYLE_PRESETS, DEFAULT_STATE, castFromPanels, emptyScenes, guessPromptFormat,
  maxReachableStep, movePanel, newPanel, parseNames, prefersVerticalBubbles, promptForPanel,
  readSavedState, writeSavedState, type StepId, type WizardState,
} from './wizardLogic';
import './wizard.css';

type ProjectSettings = {
  style?: string;
  characters?: { name: string; prompt_block: string }[];
};
type WizardProject = Project & { settings?: ProjectSettings & Record<string, unknown> };

const SHOTS = ['', 'wide', 'medium', 'close-up', 'extreme-close-up', 'splash'] as const;

async function api<T = unknown>(url: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const { json, ...rest } = init || {};
  const res = await fetch(url, {
    ...rest,
    headers: json !== undefined ? { 'Content-Type': 'application/json' } : rest.headers,
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  const text = await res.text();
  let data: unknown = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) {
    const detail = (data && typeof data === 'object' && 'detail' in data)
      ? String((data as { detail: unknown }).detail) : `HTTP ${res.status}`;
    throw new Error(detail);
  }
  return data as T;
}

export function WizardTab() {
  const { t } = useTranslation();
  const w = t.wizard;
  const tip = useTips().wizard;
  const { setCurrentProject, setComposerProjectId, setActiveTab, settings } = useProjectStore();

  const [state, setState] = useState<WizardState>(readSavedState);
  const [project, setProject] = useState<WizardProject | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const update = useCallback((patch: Partial<WizardState>) => {
    setState(s => ({ ...s, ...patch }));
  }, []);
  useEffect(() => { writeSavedState(state); }, [state]);

  const refresh = useCallback(async (id = state.projectId) => {
    if (!id) { setProject(null); return null; }
    try {
      const data = await api<{ project: WizardProject }>(`/api/agent/projects/${encodeURIComponent(id)}`);
      setProject(data.project);
      setCurrentProject(data.project);   // the expert tabs see the same project
      return data.project;
    } catch (e) {
      // the project was deleted elsewhere: start over instead of failing every step
      if (String(e).includes('not found')) setState({ ...DEFAULT_STATE });
      else setError(String((e as Error).message || e));
      return null;
    }
  }, [state.projectId, setCurrentProject]);

  useEffect(() => { refresh(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // a step other than Story needs its project; wait for the first load
  const loading = !!state.projectId && !project && !error && !busy;
  const panels = project?.panels || [];
  const pages = project?.composerPages || [];
  const facts = {
    hasProject: !!project,
    panels: panels.length,
    panelsWithImage: panels.filter(p => p.image).length,
    pages: pages.length,
  };
  const reach = maxReachableStep(facts);
  const stepIndex = STEPS.indexOf(state.step);

  const goTo = (step: StepId) => { setError(null); update({ step }); };

  const run = async (label: string, fn: () => Promise<void>) => {
    setBusy(label);
    setError(null);
    try { await fn(); } catch (e) { setError(String((e as Error).message || e)); } finally { setBusy(null); }
  };

  const startOver = () => {
    if (!confirm(w.startOverConfirm)) return;
    setProject(null);
    setError(null);
    setState({ ...DEFAULT_STATE, reading: state.reading, promptFormat: state.promptFormat });
  };

  const stepProps = { state, update, project, refresh, run, busy, goTo, w, panels, pages };

  return (
    <div className="wizard">
      <ol className="wizard-steps" aria-label={w.progress} data-tour="wizard-steps">
        {STEPS.map((id, i) => {
          const status = i === stepIndex ? 'current' : i < stepIndex || i <= reach ? 'open' : 'locked';
          return (
            <li key={id} className={`wizard-step is-${status}`}>
              <button
                type="button"
                disabled={status === 'locked' || !!busy}
                onClick={() => goTo(id)}
                data-tip={tip.stepper}
                aria-current={status === 'current' ? 'step' : undefined}
              >
                <span className="wizard-step-num">{i < stepIndex ? <FiCheck size={14} /> : i + 1}</span>
                <span className="wizard-step-label">{w.steps[id].title}</span>
              </button>
            </li>
          );
        })}
      </ol>

      <section className="wizard-card card" data-tour="wizard-card">
        <header className="wizard-card-head">
          <div>
            <h2>{w.steps[state.step].title}</h2>
            <p className="text-secondary">{w.steps[state.step].intro}</p>
          </div>
          {project && (
            <div className="wizard-project" data-tour="wizard-project">
              <span className="badge">{project.name}</span>
              <button type="button" className="btn btn-ghost" onClick={startOver} disabled={!!busy} data-tip={tip.startOver}>
                {w.startOver}
              </button>
            </div>
          )}
        </header>

        {error && <div className="wizard-error" role="alert">{error}</div>}

        {loading ? (
          <div className="wizard-loading"><span className="loading-spinner" /></div>
        ) : <>
        {state.step === 'story' && <StoryStep key={project?.id || 'new'} {...stepProps} />}
        {state.step === 'panels' && <PanelsStep key={project?.id} {...stepProps} />}
        {state.step === 'look' && <LookStep {...stepProps} swarmModel={settings.swarmui.currentModel} />}
        {state.step === 'art' && <ArtStep {...stepProps} />}
        {state.step === 'pages' && <PagesStep {...stepProps} />}
        {state.step === 'finish' && (
          <FinishStep
            {...stepProps}
            openComposer={() => {
              if (!project) return;
              setComposerProjectId(project.id);
              setActiveTab('composer');
            }}
            startNew={() => { setProject(null); setState({ ...DEFAULT_STATE, reading: state.reading, promptFormat: state.promptFormat }); }}
          />
        )}
        </>}
      </section>

      <p className="wizard-footnote text-muted text-sm">{w.footnote}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------

type W = ReturnType<typeof useTranslation>['t']['wizard'];
interface StepProps {
  state: WizardState;
  update: (p: Partial<WizardState>) => void;
  project: WizardProject | null;
  refresh: (id?: string | null) => Promise<WizardProject | null>;
  run: (label: string, fn: () => Promise<void>) => Promise<void>;
  busy: string | null;
  goTo: (s: StepId) => void;
  w: W;
  panels: Panel[];
  pages: NonNullable<WizardProject['composerPages']>;
}

function Nav({ back, next, nextLabel, nextTip, nextDisabled, busy, extra }: {
  back?: () => void; next?: () => void; nextLabel?: string; nextTip?: string; nextDisabled?: boolean;
  busy: string | null; extra?: React.ReactNode;
}) {
  const { t } = useTranslation();
  const tip = useTips().wizard;
  return (
    <div className="wizard-nav" data-tour="wizard-nav">
      {back ? (
        <button type="button" className="btn btn-secondary" onClick={back} disabled={!!busy} data-tip={tip.back}>
          <FiArrowLeft size={16} /> {t.wizard.back}
        </button>
      ) : <span />}
      <div className="wizard-nav-right">
        {extra}
        {next && (
          <button type="button" className="btn btn-primary" onClick={next} disabled={!!busy || nextDisabled}
            data-tip={nextTip || tip.next}>
            {busy ? <span className="loading-spinner" /> : null}
            {nextLabel || t.wizard.next} <FiArrowRight size={16} />
          </button>
        )}
      </div>
    </div>
  );
}

function Tip({ children }: { children: React.ReactNode }) {
  return <div className="wizard-tip" data-tour="wizard-tip">{children}</div>;
}

// --- 1. Story --------------------------------------------------------------

function StoryStep({ state, update, project, refresh, run, busy, goTo, w }: StepProps) {
  const tip = useTips().wizard;
  const [name, setName] = useState(project?.name || '');
  const [existing, setExisting] = useState<{ id: string; name: string; stats: { panels: number } }[]>([]);
  useEffect(() => {
    if (project) return;
    api<{ projects: typeof existing }>('/api/agent/projects')
      .then(d => setExisting(d.projects || []))
      .catch(() => setExisting([]));
  }, [project]);

  const ensureProject = async (): Promise<string> => {
    if (state.projectId && project) {
      if (name.trim() && name.trim() !== project.name) {
        await api('/api/projects/save', { method: 'POST', json: { ...project, name: name.trim() } });
      }
      return state.projectId;
    }
    const data = await api<{ project: WizardProject }>('/api/agent/projects', {
      method: 'POST', json: { name: name.trim() || w.story.untitled },
    });
    update({ projectId: data.project.id, coverPageId: null });
    await refresh(data.project.id);
    return data.project.id;
  };

  const withAI = () => run('ai', async () => {
    if (project?.panels.length && !confirm(w.story.replaceConfirm)) return;
    const id = await ensureProject();
    await api('/api/agent/storyboard', {
      method: 'POST',
      json: { project_id: id, text: state.storyText, detail_level: state.detailLevel, replace: true },
    }).catch((e: Error) => { throw new Error(`${e.message} — ${w.story.llmHint}`); });
    await refresh(id);
    goTo('panels');
  });

  const manually = () => run('manual', async () => {
    const id = await ensureProject();
    await refresh(id);
    goTo('panels');
  });

  const resume = (id: string) => run('resume', async () => {
    update({ projectId: id, coverPageId: null });
    const p = await refresh(id);
    if (p) goTo('panels');
  });

  const count = ['~1-2', '~3-4', '~5-6', '~7-8', '~10+'][state.detailLevel - 1];
  const storyImport = useStoryImport(state.storyText, text => update({ storyText: text }));

  return (
    <div className="wizard-body">
      <label className="wizard-field">
        <span>{w.story.name}</span>
        <input className="input" value={name} onChange={e => setName(e.target.value)}
          placeholder={w.story.namePlaceholder} maxLength={120} data-tip={tip.story.name} />
      </label>

      <div className="wizard-field">
        <div className="wizard-field-head">
          <label htmlFor="wizard-story-text">{w.story.text}</label>
          {storyImport.fileInput}
          <button type="button" className="btn btn-ghost" onClick={storyImport.open} disabled={!!busy}
            data-tip={tip.story.importFile}>
            <FiUpload size={14} /> {w.story.importFile}
          </button>
        </div>
        <textarea id="wizard-story-text" className={`input textarea wizard-story${storyImport.dragOver ? ' is-drop' : ''}`}
          rows={9} value={state.storyText}
          onChange={e => update({ storyText: e.target.value })}
          {...storyImport.dropProps}
          placeholder={w.story.textPlaceholder} data-tip={tip.story.text} />
      </div>

      <div className="wizard-row">
        <label className="wizard-field">
          <span>{w.story.length} <em className="text-muted">({fill(w.story.panelCount, { n: count })})</em></span>
          <input type="range" className="slider" min={1} max={5} value={state.detailLevel}
            onChange={e => update({ detailLevel: Number(e.target.value) })} data-tip={tip.story.length} />
          <div className="wizard-range-labels text-muted"><span>{w.story.short}</span><span>{w.story.long}</span></div>
        </label>
        <div className="wizard-field">
          <span>{w.story.reading}</span>
          <div className="wizard-choice">
            {(['rtl', 'ltr'] as const).map(r => (
              <button key={r} type="button" className={`wizard-chip ${state.reading === r ? 'is-on' : ''}`}
                onClick={() => update({ reading: r })} data-tip={r === 'rtl' ? tip.story.rtl : tip.story.ltr}>
                {r === 'rtl' ? w.story.rtl : w.story.ltr}
              </button>
            ))}
          </div>
        </div>
      </div>

      <Tip>{w.story.tip}</Tip>

      <Nav
        busy={busy}
        next={withAI}
        nextLabel={busy === 'ai' ? w.story.writing : w.story.withAI}
        nextTip={tip.story.withAI}
        nextDisabled={!state.storyText.trim()}
        extra={
          <button type="button" className="btn btn-secondary" onClick={manually} disabled={!!busy} data-tip={tip.story.manual}>
            <FiEdit3 size={16} /> {project?.panels.length ? w.story.keepPanels : w.story.manual}
          </button>
        }
      />

      {!project && existing.length > 0 && (
        <details className="wizard-resume">
          <summary>{w.story.continueExisting}</summary>
          <ul>
            {existing.slice(0, 30).map(p => (
              <li key={p.id}>
                <button type="button" className="btn btn-ghost" onClick={() => resume(p.id)} disabled={!!busy} data-tip={tip.story.resume}>
                  {p.name || p.id} <span className="text-muted">· {fill(w.story.panelsN, { n: p.stats?.panels ?? 0 })}</span>
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

// --- 2. Panels -------------------------------------------------------------

function PanelsStep({ state, project, refresh, run, busy, goTo, w, panels: saved }: StepProps) {
  const tip = useTips().wizard;
  const [list, setList] = useState<Panel[]>(() => (saved.length ? saved : [newPanel([])]));
  const [charText, setCharText] = useState<Record<string, string>>({});

  const edit = (i: number, patch: Partial<Panel>) =>
    setList(l => l.map((p, j) => (j === i ? { ...p, ...patch } : p)));

  const empty = emptyScenes(list);

  const save = () => run('save', async () => {
    if (!project) return;
    const body = list.map((p, i) => {
      const out: Panel = { ...p, order: i, characters: parseNames(charText[p.id] ?? (p.characters || []).join(', ')) };
      if (!out.shot) delete out.shot;
      return out;
    });
    await api(`/api/agent/projects/${encodeURIComponent(project.id)}/panels`, { method: 'PUT', json: { panels: body } });
    await refresh(state.projectId);
    goTo('look');
  });

  return (
    <div className="wizard-body">
      <Tip>{w.panels.tip}</Tip>
      <div className="wizard-panels">
        {list.map((p, i) => (
          <div key={p.id} className="wizard-panel">
            <div className="wizard-panel-head">
              <span className="badge">{fill(w.panels.panelN, { n: i + 1 })}</span>
              <div className="wizard-panel-tools">
                <button type="button" className="btn btn-ghost" data-tip={tip.panels.up} aria-label={w.panels.up}
                  disabled={i === 0} onClick={() => setList(l => movePanel(l, i, i - 1))}><FiArrowUp size={14} /></button>
                <button type="button" className="btn btn-ghost" data-tip={tip.panels.down} aria-label={w.panels.down}
                  disabled={i === list.length - 1} onClick={() => setList(l => movePanel(l, i, i + 1))}><FiArrowDown size={14} /></button>
                <button type="button" className="btn btn-ghost" data-tip={tip.panels.remove} aria-label={w.panels.remove}
                  disabled={list.length === 1} onClick={() => setList(l => l.filter((_, j) => j !== i))}><FiTrash2 size={14} /></button>
              </div>
            </div>
            <div className="wizard-panel-grid">
              {p.image && <img className="wizard-panel-thumb" src={p.image} alt="" />}
              <label className="wizard-field wizard-span">
                <span>{w.panels.scene}</span>
                <textarea className={`input textarea ${!p.scene.trim() ? 'is-missing' : ''}`} rows={2} value={p.scene}
                  placeholder={w.panels.scenePlaceholder} onChange={e => edit(i, { scene: e.target.value })} data-tip={tip.panels.scene} />
              </label>
              <label className="wizard-field">
                <span>{w.panels.characters}</span>
                <input className="input" placeholder={w.panels.charactersPlaceholder} data-tip={tip.panels.characters}
                  value={charText[p.id] ?? (p.characters || []).join(', ')}
                  onChange={e => setCharText(c => ({ ...c, [p.id]: e.target.value }))} />
              </label>
              <label className="wizard-field">
                <span>{w.panels.shot}</span>
                <select className="input" value={p.shot || ''} onChange={e => edit(i, { shot: e.target.value || undefined })} data-tip={tip.panels.shot}>
                  {SHOTS.map(s => <option key={s} value={s}>{w.shots[s || 'auto']}</option>)}
                </select>
              </label>
              <label className="wizard-field wizard-span">
                <span>{w.panels.dialogue}</span>
                <textarea className="input textarea" rows={2} value={p.dialogue}
                  placeholder={w.panels.dialoguePlaceholder} onChange={e => edit(i, { dialogue: e.target.value })} data-tip={tip.panels.dialogue} />
              </label>
            </div>
          </div>
        ))}
      </div>
      <button type="button" className="btn btn-secondary wizard-add" onClick={() => setList(l => [...l, newPanel(l)])} data-tip={tip.panels.add}>
        <FiPlus size={16} /> {w.panels.add}
      </button>
      {empty.length > 0 && <p className="text-sm wizard-warn">{fill(w.panels.needScene, { list: empty.join(', ') })}</p>}
      <Nav busy={busy} back={() => goTo('story')} next={save} nextDisabled={empty.length > 0} />
    </div>
  );
}

// --- 3. Look ---------------------------------------------------------------

function LookStep({ state, update, project, refresh, run, busy, goTo, w, panels, swarmModel }: StepProps & { swarmModel: string }) {
  const tip = useTips().wizard;
  const cast = useMemo(() => castFromPanels(panels), [panels]);
  const [style, setStyle] = useState(project?.settings?.style || '');
  const [blocks, setBlocks] = useState<Record<string, string>>(() => {
    const out: Record<string, string> = {};
    for (const c of project?.settings?.characters || []) out[c.name] = c.prompt_block;
    return out;
  });
  const guessed = guessPromptFormat(swarmModel || '');

  const save = () => run('save', async () => {
    if (!project) return;
    const keep = (project.settings?.characters || []).filter(c => !cast.includes(c.name));
    const chars = [
      ...keep,
      ...cast.filter(n => (blocks[n] || '').trim()).map(n => ({ name: n, prompt_block: blocks[n].trim() })),
    ];
    await api(`/api/agent/projects/${encodeURIComponent(project.id)}/settings`, {
      method: 'PUT', json: { style, characters: chars },
    });
    await refresh(state.projectId);
    goTo('art');
  });

  return (
    <div className="wizard-body">
      <div className="wizard-field">
        <span>{w.look.style}</span>
        <div className="wizard-choice">
          {STYLE_PRESETS.map(p => (
            <button key={p.id} type="button" className={`wizard-chip ${style === p.prompt ? 'is-on' : ''}`}
              onClick={() => setStyle(p.prompt)} data-tip={tip.look.preset}>
              {w.look.presets[p.id as keyof typeof w.look.presets]}
            </button>
          ))}
        </div>
        <textarea className="input textarea" rows={2} value={style} placeholder={w.look.stylePlaceholder}
          onChange={e => setStyle(e.target.value)} data-tip={tip.look.style} />
      </div>

      <div className="wizard-field">
        <span>{w.look.format}</span>
        <div className="wizard-options">
          {(['danbooru', 'prose'] as const).map(f => (
            <button key={f} type="button" className={`wizard-option ${state.promptFormat === f ? 'is-on' : ''}`}
              onClick={() => update({ promptFormat: f })} data-tip={f === 'prose' ? tip.look.prose : tip.look.tags}>
              <strong>{w.look.formats[f].title}{f === guessed && swarmModel ? ` · ${w.look.suggested}` : ''}</strong>
              <span className="text-secondary text-sm">{w.look.formats[f].desc}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="wizard-field">
        <span>{w.look.cast}</span>
        {cast.length === 0 ? (
          <p className="text-muted text-sm">{w.look.noCast}</p>
        ) : (
          <div className="wizard-cast">
            {cast.map(n => (
              <label key={n} className="wizard-field">
                <span className="badge">{n}</span>
                <input className="input" value={blocks[n] || ''} placeholder={w.look.appearancePlaceholder}
                  onChange={e => setBlocks(b => ({ ...b, [n]: e.target.value }))} data-tip={tip.look.appearance} />
              </label>
            ))}
          </div>
        )}
      </div>
      <Tip>{w.look.tip}</Tip>
      <Nav busy={busy} back={() => goTo('panels')} next={save} />
    </div>
  );
}

// --- 4. Art ----------------------------------------------------------------

type JobSnap = { status: string; total: number; done: number; items: { panel_id: string; status: string; error?: string }[] };

function ArtStep({ state, project, refresh, run, busy, goTo, w, panels }: StepProps) {
  const tip = useTips().wizard;
  const [swarm, setSwarm] = useState<'checking' | 'ok' | 'down'>('checking');
  const [job, setJob] = useState<JobSnap | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    api<{ connected: boolean }>('/api/assets/swarmui/test')
      .then(d => setSwarm(d.connected ? 'ok' : 'down'))
      .catch(() => setSwarm('down'));
  }, []);

  useEffect(() => {
    if (!jobId) return;
    let stopped = false;
    const poll = async () => {
      try {
        const snap = await api<JobSnap>(`/api/agent/jobs/${jobId}`);
        if (stopped) return;
        setJob(snap);
        await refresh(state.projectId);
        if (snap.status === 'done') { setJobId(null); return; }
      } catch {
        if (stopped) return;
        setJobId(null);   // server restarted: the job table is gone
        return;
      }
      timer.current = window.setTimeout(poll, 2500);
    };
    poll();
    return () => { stopped = true; if (timer.current) clearTimeout(timer.current); };
  }, [jobId]); // eslint-disable-line react-hooks/exhaustive-deps

  const generate = (targets: Panel[]) => run('gen', async () => {
    if (!project || !targets.length) return;
    const res = await api<{ job_id: string }>('/api/agent/generate-batch', {
      method: 'POST',
      json: {
        project_id: project.id,
        concurrency: 1,
        jobs: targets.map(p => ({
          panel_id: p.id,
          prompt: promptForPanel(p, state.promptFormat),
          negative_prompt: p.prompt?.negativePrompt || '',
          seed: p.prompt?.seed,
          prompt_format: state.promptFormat,
        })),
      },
    });
    setJob(null);
    setJobId(res.job_id);
  });

  const statusOf = (id: string) => job?.items.find(i => i.panel_id === id);
  const missing = panels.filter(p => !p.image);
  const running = !!jobId;
  const withArt = panels.length - missing.length;

  return (
    <div className="wizard-body">
      <div className={`wizard-status is-${swarm}`}>
        {swarm === 'checking' ? w.art.checking : swarm === 'ok' ? w.art.connected : w.art.disconnected}
      </div>

      <div className="wizard-art-bar">
        <button type="button" className="btn btn-primary" disabled={!!busy || running || swarm === 'down' || !missing.length}
          onClick={() => generate(missing)} data-tip={tip.art.generate}>
          {running ? <span className="loading-spinner" /> : <FiZap size={16} />}
          {missing.length ? fill(w.art.generateMissing, { n: missing.length }) : w.art.allDone}
        </button>
        {job && (
          <div className="wizard-progress" aria-live="polite">
            <div className="wizard-progress-bar"><div style={{ width: `${(job.done / Math.max(1, job.total)) * 100}%` }} /></div>
            <span className="text-sm text-secondary">{fill(w.art.progress, { done: job.done, total: job.total })}</span>
          </div>
        )}
      </div>

      <div className="wizard-art-grid">
        {panels.map((p, i) => {
          const st = statusOf(p.id);
          const working = running && st && (st.status === 'queued' || st.status === 'running' || st.status === 'pending');
          return (
            <figure key={p.id} className="wizard-art">
              <div className="wizard-art-img">
                {p.image ? <img src={p.image} alt={p.scene} /> : <FiImage size={28} />}
                {working && <div className="wizard-art-overlay"><span className="loading-spinner" /></div>}
              </div>
              <figcaption>
                <span className="badge">{i + 1}</span>
                <span className="wizard-art-scene" title={p.scene}>{p.scene}</span>
                <button type="button" className="btn btn-ghost" data-tip={tip.art.redo} aria-label={w.art.redo}
                  disabled={!!busy || running || swarm === 'down'} onClick={() => generate([p])}>
                  <FiRefreshCw size={14} />
                </button>
              </figcaption>
              {st?.error && <p className="wizard-art-error text-sm">{st.error}</p>}
            </figure>
          );
        })}
      </div>
      <Tip>{w.art.tip}</Tip>
      <Nav busy={busy} back={() => goTo('look')} next={() => goTo('pages')}
        nextDisabled={running || withArt === 0}
        nextLabel={missing.length && withArt ? fill(w.art.continueWith, { n: withArt }) : undefined} />
    </div>
  );
}

// --- 5. Pages --------------------------------------------------------------

function PagesStep({ state, update, project, refresh, run, busy, goTo, w, pages, panels }: StepProps) {
  const tip = useTips().wizard;
  const [stamp, setStamp] = useState(() => Date.now());

  const build = () => run('build', async () => {
    if (!project) return;
    if (pages.length && !confirm(w.pages.rebuildConfirm)) return;
    const base = `/api/agent/projects/${encodeURIComponent(project.id)}`;
    for (const pg of pages) await api(`${base}/pages/${encodeURIComponent(pg.id)}`, { method: 'DELETE' });
    await api(`${base}/plan-pages`, {
      method: 'POST',
      json: {
        panels_per_page: state.panelsPerPage, reading: state.reading, dynamic: state.dynamic, apply: true,
        bubbles: { vertical: prefersVerticalBubbles(panels) },
      },
    });
    update({ coverPageId: null });
    await refresh(state.projectId);
    setStamp(Date.now());
  });

  return (
    <div className="wizard-body">
      <div className="wizard-row">
        <div className="wizard-field">
          <span>{w.pages.perPage}</span>
          <div className="wizard-choice">
            {[2, 3, 4, 5, 6].map(n => (
              <button key={n} type="button" className={`wizard-chip ${state.panelsPerPage === n ? 'is-on' : ''}`}
                onClick={() => update({ panelsPerPage: n })} data-tip={tip.pages.perPage}>{n}</button>
            ))}
          </div>
        </div>
        <label className="wizard-toggle">
          <input type="checkbox" checked={state.dynamic} onChange={e => update({ dynamic: e.target.checked })} data-tip={tip.pages.dynamic} />
          <span><strong>{w.pages.dynamic}</strong><br /><span className="text-sm text-secondary">{w.pages.dynamicDesc}</span></span>
        </label>
      </div>
      <button type="button" className="btn btn-primary" onClick={build} disabled={!!busy} data-tip={tip.pages.build}>
        {busy === 'build' ? <span className="loading-spinner" /> : <FiLayers size={16} />}
        {pages.length ? w.pages.rebuild : w.pages.build}
      </button>

      {pages.length > 0 && project && (
        <div className="wizard-pages">
          {[...pages].sort((a, b) => a.order - b.order).map((pg, i) => (
            <a key={pg.id} className="wizard-page" target="_blank" rel="noreferrer"
              href={`/api/agent/projects/${encodeURIComponent(project.id)}/pages/${encodeURIComponent(pg.id)}/preview.png?scale=2`}>
              <img loading="lazy" alt={fill(w.pages.pageN, { n: i + 1 })}
                src={`/api/agent/projects/${encodeURIComponent(project.id)}/pages/${encodeURIComponent(pg.id)}/preview.png?scale=0.6&v=${stamp}`} />
              <span className="text-sm text-secondary">{fill(w.pages.pageN, { n: i + 1 })}</span>
            </a>
          ))}
        </div>
      )}
      <Tip>{w.pages.tip}</Tip>
      <Nav busy={busy} back={() => goTo('art')} next={() => goTo('finish')} nextDisabled={!pages.length} />
    </div>
  );
}

// --- 6. Finish -------------------------------------------------------------

function FinishStep({ state, update, project, refresh, run, busy, goTo, w, panels, pages, openComposer, startNew }:
  StepProps & { openComposer: () => void; startNew: () => void }) {
  const tip = useTips().wizard;
  const exportScale = useExportScale();
  const [title, setTitle] = useState(project?.name || '');
  const [subtitle, setSubtitle] = useState('');
  const [numbers, setNumbers] = useState(true);
  const [links, setLinks] = useState<{ pdf?: string; zip?: string }>({});
  const hasCover = !!state.coverPageId && pages.some(p => p.id === state.coverPageId);

  const addCover = () => run('cover', async () => {
    if (!project) return;
    const art = panels.find(p => p.image);
    if (!art) return;
    const base = `/api/agent/projects/${encodeURIComponent(project.id)}`;
    if (hasCover) await api(`${base}/pages/${encodeURIComponent(state.coverPageId!)}`, { method: 'DELETE' });
    const res = await api<{ page: { id: string } }>(`${base}/cover`, {
      method: 'POST', json: { title: title.trim(), subtitle: subtitle.trim() || undefined, panel_id: art.id },
    });
    update({ coverPageId: res.page.id });
    await refresh(state.projectId);
  });

  const exportAs = (format: 'pdf' | 'zip') => run(format, async () => {
    if (!project) return;
    const res = await api<{ pdf?: { url: string }; zip?: { url: string } }>('/api/agent/export', {
      method: 'POST', json: { project_id: project.id, format, scale: exportScale, page_numbers: numbers },
    });
    const url = res[format]?.url;
    if (url) {
      setLinks(l => ({ ...l, [format]: url }));
      window.open(url, '_blank', 'noopener');
    }
  });

  return (
    <div className="wizard-body">
      <div className="wizard-row">
        <label className="wizard-field">
          <span>{w.finish.coverTitle}</span>
          <input className="input" value={title} onChange={e => setTitle(e.target.value)} data-tip={tip.finish.coverTitle} />
        </label>
        <label className="wizard-field">
          <span>{w.finish.coverSubtitle}</span>
          <input className="input" value={subtitle} placeholder={w.finish.optional} onChange={e => setSubtitle(e.target.value)} data-tip={tip.finish.subtitle} />
        </label>
      </div>
      <button type="button" className="btn btn-secondary" onClick={addCover} disabled={!!busy || !title.trim()} data-tip={tip.finish.cover}>
        {busy === 'cover' ? <span className="loading-spinner" /> : <FiImage size={16} />}
        {hasCover ? w.finish.replaceCover : w.finish.addCover}
      </button>

      <hr className="wizard-sep" />

      <label className="wizard-toggle">
        <input type="checkbox" checked={numbers} onChange={e => setNumbers(e.target.checked)} data-tip={tip.finish.pageNumbers} />
        <span>{w.finish.pageNumbers}</span>
      </label>
      <div className="wizard-choice">
        {(['pdf', 'zip'] as const).map(f => (
          <button key={f} type="button" className="btn btn-primary" onClick={() => exportAs(f)} disabled={!!busy} data-tip={f === 'pdf' ? tip.finish.pdf : tip.finish.zip}>
            {busy === f ? <span className="loading-spinner" /> : <FiDownload size={16} />}
            {f === 'pdf' ? w.finish.pdf : w.finish.zip}
          </button>
        ))}
      </div>
      {(links.pdf || links.zip) && (
        <p className="text-sm">
          {w.finish.ready}{' '}
          {links.pdf && <a href={links.pdf} target="_blank" rel="noreferrer">PDF</a>}
          {links.pdf && links.zip && ' · '}
          {links.zip && <a href={links.zip} target="_blank" rel="noreferrer">ZIP</a>}
        </p>
      )}

      <Tip>{w.finish.tip}</Tip>
      <Nav busy={busy} back={() => goTo('pages')}
        extra={<>
          <button type="button" className="btn btn-secondary" onClick={openComposer} disabled={!!busy} data-tip={tip.finish.composer}>
            <FiLayers size={16} /> {w.finish.composer}
          </button>
          <button type="button" className="btn btn-secondary" onClick={startNew} disabled={!!busy} data-tip={tip.finish.newComic}>
            <FiPlus size={16} /> {w.finish.newComic}
          </button>
        </>} />
    </div>
  );
}
