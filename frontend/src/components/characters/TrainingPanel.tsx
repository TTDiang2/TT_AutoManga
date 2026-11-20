import { useCallback, useEffect, useRef, useState } from 'react';
import { FiCopy, FiPlay, FiSquare, FiTrash2, FiUpload, FiImage, FiDownload } from 'react-icons/fi';
import { useProjectStore } from '../../store/projectStore';
import { useTranslation, fill } from '../../hooks/useTranslation';
import { useTips } from '../../hooks/useTips';
import type { Character } from '../../types';
import { clampInt } from './clampInt';

// Train LoRA (Phase 7): a dataset per character in data/training/<slug>/,
// trained on the Razer by backend/api/training.py. One job at a time.

interface DatasetImage { file: string; url: string; mtime: number }
interface Generation { running: boolean; total: number; done: number; failed: number; errors: string[] }
interface Dataset {
  slug: string;
  trigger: string;
  characterId?: string | null;
  count: number;
  minImages: number;
  images: DatasetImage[];
  generation?: Generation | null;
}
interface Job {
  id: string;
  name: string;
  slug: string;
  trigger: string;
  characterId?: string | null;   // the character the server sets the LoRA on when the job is done
  phase: 'pushing' | 'launching' | 'running' | 'finishing' | 'done' | 'failed' | 'stopped';
  step: number;
  steps: number;
  error?: string | null;
  pollError?: string;
  events: string[];
  lines: string[];
  partial: string;
  next: number;
  running: boolean;
  lora?: { name: string; weight: number; trigger: string };
}

const MIN_IMAGES = 15;
const GEN_RANGE = [1, 64, 24] as const;          // min, max, default
const STEPS_RANGE = [10, 10000, 1500] as const;

function slugFor(name: string) {
  return 'am_' + (name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'char');
}
function triggerFor(name: string) {
  return 'am' + (name.toLowerCase().replace(/[^a-z0-9]/g, '').slice(0, 20) || 'char');
}
async function jsonOrThrow(res: Response) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `HTTP ${res.status}`);
  return data;
}

export function TrainingPanel({ character }: { character: Character }) {
  const { t } = useTranslation();
  const tt = t.training;
  const tip = useTips().characters;
  const currentProject = useProjectStore(s => s.currentProject);
  const updateCharacter = useProjectStore(s => s.updateCharacter);
  const setCharacters = useProjectStore(s => s.setCharacters);
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [form, setForm] = useState({ slug: slugFor(character.name), trigger: triggerFor(character.name) });
  // number boxes keep their text while typing; clampInt applies on blur and on submit
  const [genCount, setGenCount] = useState(String(GEN_RANGE[2]));
  const [steps, setSteps] = useState(String(STEPS_RANGE[2]));
  const [job, setJob] = useState<Job | null>(null);
  const [lines, setLines] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const nextRef = useRef(0);
  const jobIdRef = useRef<string | null>(null);
  const phaseRef = useRef<string | null>(null);
  const pollingRef = useRef(false);                 // a job poll is in flight
  const againRef = useRef(false);                   // poll again once it lands
  const slugRef = useRef<string | null>(null);      // this panel's dataset, for pollJob
  useEffect(() => { slugRef.current = dataset?.slug ?? null; }, [dataset?.slug]);

  const report = (e: unknown) => setError(e instanceof Error ? e.message : String(e));

  const loadDataset = useCallback(async (slug?: string) => {
    try {
      let s = slug;
      if (!s) {
        const list = await jsonOrThrow(await fetch(`/api/training/datasets?character_id=${encodeURIComponent(character.id)}`));
        s = list.datasets?.[0]?.slug;
      }
      setDataset(s ? await jsonOrThrow(await fetch(`/api/training/datasets/${s}`)) : null);
    } catch (e) { report(e); }
    setLoaded(true);
  }, [character.id]);

  // CharacterTab mounts this panel with key={character.id}, so a new character starts from fresh state
  // started from a promise callback: the loaders only set state after their fetches resolve
  useEffect(() => { void Promise.resolve().then(() => loadDataset()); }, [loadDataset]);

  // the server's character list (the trainer set a LoRA on some other character)
  const refreshCharacters = useCallback(async () => {
    try {
      const data = await jsonOrThrow(await fetch('/api/characters/'));
      if (Array.isArray(data)) setCharacters(data);
    } catch (e) { report(e); }
  }, [setCharacters]);

  // poll the job; one request at a time, so `since` never repeats (no duplicate log lines).
  // A call while one is in flight runs once more after it (start/stop want a fresh read).
  const pollOnce = useCallback(async () => {
    try {
      const since = nextRef.current;
      const data = await jsonOrThrow(await fetch(`/api/training/jobs/current?since=${since}`));
      const j: Job | null = data.job;
      if (!j) { setJob(null); return; }
      if (j.id !== jobIdRef.current) {
        jobIdRef.current = j.id;
        nextRef.current = 0;
        // a new job read from an older job's offset: read its log again from the start
        if (since !== 0) { setLines([]); againRef.current = true; return; }
        setLines(j.lines);
      } else setLines(prev => [...prev, ...j.lines].slice(-300));
      nextRef.current = j.next;
      if (phaseRef.current && phaseRef.current !== 'done' && j.phase === 'done' && j.lora) {
        // the server set it already, on the job's character (older jobs: the dataset's)
        const mine = j.characterId ? j.characterId === character.id : j.slug === slugRef.current;
        if (mine) updateCharacter(character.id, { lora: j.lora });
        else void refreshCharacters();
      }
      phaseRef.current = j.phase;
      setJob(j);
    } catch (e) { report(e); }
  }, [character.id, updateCharacter, refreshCharacters]);

  const pollJob = useCallback(async () => {
    if (pollingRef.current) { againRef.current = true; return; }
    pollingRef.current = true;
    try {
      do {
        againRef.current = false;
        await pollOnce();
      } while (againRef.current);
    } finally { pollingRef.current = false; }
  }, [pollOnce]);

  useEffect(() => { void Promise.resolve().then(pollJob); }, [pollJob]);
  const generating = !!dataset?.generation?.running;
  const jobRunning = !!job?.running;
  const slug = dataset?.slug;
  // while something runs: a setTimeout chain, so a slow response never overlaps the next poll
  useEffect(() => {
    if (!jobRunning && !generating) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const tick = async () => {
      await Promise.all([
        jobRunning ? pollJob() : null,
        generating && slug ? loadDataset(slug) : null,
      ]);
      if (!cancelled) timer = setTimeout(tick, 3000);
    };
    timer = setTimeout(tick, 3000);
    return () => { cancelled = true; if (timer) clearTimeout(timer); };
  }, [jobRunning, generating, pollJob, loadDataset, slug]);

  const create = async () => {
    setError(null);
    try {
      setDataset(await jsonOrThrow(await fetch('/api/training/datasets', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, characterId: character.id }),
      })));
    } catch (e) { report(e); }
  };

  const upload = async (files: FileList | null) => {
    if (!files?.length || !dataset) return;
    const body = new FormData();
    Array.from(files).forEach(f => body.append('files', f));
    try {
      setDataset(await jsonOrThrow(await fetch(`/api/training/datasets/${dataset.slug}/upload`, { method: 'POST', body })));
    } catch (e) { report(e); }
  };

  const post = async (path: string, payload?: unknown, method = 'POST') => {
    setError(null);
    try {
      return await jsonOrThrow(await fetch(path, {
        method, headers: { 'Content-Type': 'application/json' },
        body: payload === undefined ? undefined : JSON.stringify(payload),
      }));
    } catch (e) { report(e); return null; }
  };

  const importPanels = async () => {
    if (!dataset || !currentProject?.id) return;
    const d = await post(`/api/training/datasets/${dataset.slug}/import`, { projectId: currentProject.id });
    if (d) setDataset(d);
  };
  const generate = async () => {
    if (!dataset) return;
    setGenCount(String(clampInt(genCount, ...GEN_RANGE)));
    const d = await post(`/api/training/datasets/${dataset.slug}/generate`, { count: clampInt(genCount, ...GEN_RANGE), characterId: character.id });
    if (d) setDataset(d);
  };
  const stopGenerate = async () => {
    if (!dataset) return;
    await post(`/api/training/datasets/${dataset.slug}/generate/stop`);
    loadDataset(dataset.slug);
  };
  const removeImage = async (file: string) => {
    if (!dataset) return;
    const d = await post(`/api/training/datasets/${dataset.slug}/image/${file}`, undefined, 'DELETE');
    if (d) setDataset(d);
  };
  const start = async () => {
    if (!dataset) return;
    const n = clampInt(steps, ...STEPS_RANGE);
    setSteps(String(n));
    const d = await post('/api/training/jobs', { slug: dataset.slug, characterId: character.id, steps: n });
    if (d?.job) { jobIdRef.current = null; nextRef.current = 0; pollJob(); }
  };
  const stop = async () => { if (await post('/api/training/jobs/current/stop')) pollJob(); };

  const ownJob = job && dataset && job.slug === dataset.slug ? job : null;
  const lora = ownJob?.lora || character.lora;
  const scriptName = character.name.toUpperCase().replace(/[^A-Z0-9_]+/g, '_').replace(/^_+|_+$/g, '') || 'NAME';
  const scriptLine = lora?.name ? `lora ${scriptName}: ${lora.name} ${lora.weight} ${lora.trigger ?? ''}`.trim() : null;
  const copyLine = () => {
    if (!scriptLine) return;
    navigator.clipboard?.writeText(scriptLine).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); })
      .catch(() => setError('Could not copy'));
  };

  const count = dataset?.count ?? 0;
  const busyElsewhere = job?.running && (!dataset || job.slug !== dataset.slug);

  return (
    <div className="training-panel" style={{ marginTop: '24px', borderTop: '1px solid var(--border-default)', paddingTop: '16px' }}>
      <h4 style={{ marginBottom: '6px', fontSize: '13px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{tt.title}</h4>
      <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '12px' }}>{fill(tt.hint, { n: MIN_IMAGES })}</p>
      {error && <p style={{ color: 'var(--error)', fontSize: '13px', marginBottom: '8px' }}>{error}</p>}

      {loaded && !dataset && (
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <p style={{ width: '100%', fontSize: '13px' }}>{tt.noDataset}</p>
          <label style={{ fontSize: '12px' }}>{tt.datasetName}<br />
            <input className="input" value={form.slug} onChange={e => setForm({ ...form, slug: e.target.value })} data-tip={tip.datasetName} />
          </label>
          <label style={{ fontSize: '12px' }}>{tt.trigger}<br />
            <input className="input" value={form.trigger} onChange={e => setForm({ ...form, trigger: e.target.value })} data-tip={tip.trigger} />
          </label>
          <button className="btn btn-primary" onClick={create} data-tip={tip.createDataset}>{tt.create}</button>
        </div>
      )}

      {dataset && (
        <>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center', marginBottom: '8px' }}>
            <strong style={{ fontSize: '13px' }}>{dataset.slug}</strong>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{dataset.trigger} · {fill(tt.images, { n: count })}</span>
            <label className="btn btn-secondary" style={{ cursor: 'pointer' }} data-tip={tip.uploadImages}>
              <FiUpload size={14} /> {tt.upload}
              <input type="file" accept="image/*" multiple hidden onChange={e => { upload(e.target.files); e.target.value = ''; }} />
            </label>
            {currentProject?.id && (
              <button className="btn btn-secondary" onClick={importPanels} data-tip={tip.importPanels}><FiDownload size={14} /> {tt.importPanels}</button>
            )}
            {generating ? (
              <>
                <span style={{ fontSize: '12px' }}>{fill(tt.generating, { done: dataset.generation!.done, total: dataset.generation!.total })}</span>
                <button className="btn btn-ghost" onClick={stopGenerate} data-tip={tip.stopGenerating}>{tt.stopGenerating}</button>
              </>
            ) : (
              <span style={{ display: 'inline-flex', gap: '4px' }}>
                <input className="input" type="number" min={GEN_RANGE[0]} max={GEN_RANGE[1]} value={genCount} style={{ width: '64px' }}
                  aria-label={tt.generate}
                  data-tip={tip.genCount}
                  onChange={e => setGenCount(e.target.value)}
                  onBlur={() => setGenCount(String(clampInt(genCount, ...GEN_RANGE)))} />
                <button className="btn btn-secondary" onClick={generate} data-tip={tip.generateImages}><FiImage size={14} /> {tt.generate}</button>
              </span>
            )}
          </div>
          {dataset.generation && !generating && dataset.generation.errors.length > 0 && (
            <p style={{ fontSize: '12px', color: 'var(--error)' }}>{dataset.generation.errors.at(-1)}</p>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(72px, 1fr))', gap: '6px', maxHeight: '260px', overflowY: 'auto', marginBottom: '12px' }}>
            {dataset.images.map(img => (
              <div key={img.file} style={{ position: 'relative' }}>
                <img src={`${img.url}?v=${img.mtime}`} alt={img.file} loading="lazy"
                  style={{ width: '100%', aspectRatio: '2 / 3', objectFit: 'cover', borderRadius: '4px', display: 'block' }} />
                <button className="btn btn-ghost" data-tip={tip.deleteImage} aria-label={tt.deleteImage} onClick={() => removeImage(img.file)}
                  style={{ position: 'absolute', top: 2, right: 2, padding: '2px', background: 'rgba(0,0,0,0.55)', color: '#fff' }}>
                  <FiTrash2 size={12} />
                </button>
              </div>
            ))}
          </div>

          <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
            <label style={{ fontSize: '12px' }}>{tt.steps}{' '}
              <input className="input" type="number" min={STEPS_RANGE[0]} max={STEPS_RANGE[1]} step={100} value={steps} style={{ width: '80px' }}
                onChange={e => setSteps(e.target.value)}
                data-tip={tip.steps}
                onBlur={() => setSteps(String(clampInt(steps, ...STEPS_RANGE)))} />
            </label>
            {ownJob?.running ? (
              <button className="btn btn-secondary" onClick={stop} style={{ color: 'var(--error)' }} data-tip={tip.stop}><FiSquare size={14} /> {tt.stop}</button>
            ) : (
              <button className="btn btn-primary" onClick={start} disabled={count < MIN_IMAGES || generating || !!busyElsewhere} data-tip={tip.start}>
                <FiPlay size={14} /> {tt.start}
              </button>
            )}
            {count < MIN_IMAGES && <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{fill(tt.needImages, { n: MIN_IMAGES })}</span>}
            {busyElsewhere && job && <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{fill(tt.otherJob, { name: job.name })}</span>}
          </div>
        </>
      )}

      {ownJob && (
        <div style={{ marginTop: '12px' }}>
          <div style={{ fontSize: '13px', marginBottom: '4px' }}>
            {tt.phase}: <strong>{tt.phases[ownJob.phase] ?? ownJob.phase}</strong>
            {' · '}{ownJob.name} · {fill(tt.step, { step: ownJob.step, total: ownJob.steps })}
          </div>
          <div style={{ height: '6px', background: 'var(--bg-secondary)', borderRadius: '3px', overflow: 'hidden', marginBottom: '6px' }}>
            <div style={{ width: `${Math.min(100, (100 * ownJob.step) / Math.max(1, ownJob.steps))}%`, height: '100%', background: 'var(--accent-primary)' }} />
          </div>
          {ownJob.error && <p style={{ color: 'var(--error)', fontSize: '12px' }}>{ownJob.error}</p>}
          {ownJob.pollError && <p style={{ color: 'var(--warning, orange)', fontSize: '12px' }}>{ownJob.pollError}</p>}
          {ownJob.phase === 'done' && ownJob.lora && <p style={{ fontSize: '12px' }}>{fill(tt.done, { name: ownJob.lora.name })}</p>}
          <details>
            <summary style={{ fontSize: '12px', cursor: 'pointer' }}>{tt.log}</summary>
            <pre style={{ fontSize: '11px', maxHeight: '200px', overflow: 'auto', background: 'var(--bg-secondary)', padding: '6px', borderRadius: '4px', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
              {[...ownJob.events, '', ...lines.slice(-40), ownJob.partial].join('\n')}
            </pre>
          </details>
        </div>
      )}

      {scriptLine && (
        <div style={{ marginTop: '12px', display: 'flex', gap: '8px', alignItems: 'center' }}>
          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{tt.scriptLine}</span>
          <code style={{ fontSize: '12px', background: 'var(--bg-secondary)', padding: '2px 6px', borderRadius: '4px', userSelect: 'all' }}>{scriptLine}</code>
          <button className="btn btn-ghost" onClick={copyLine} data-tip={tip.copy}><FiCopy size={14} /> {copied ? tt.copied : tt.copy}</button>
        </div>
      )}
    </div>
  );
}
