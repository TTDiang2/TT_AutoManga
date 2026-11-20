import { useEffect, useState } from 'react';
import { useTranslation, fill } from '../../hooks/useTranslation';
import { useTips } from '../../hooks/useTips';

/** settings.swarmui's IP-Adapter fields (character-sheet references). */
export interface IpAdapterSettings {
  ipadapterPreset: string;
  ipadapterWeightType: string;
  ipadapterEnd: number;
}

/** settings.training (the ai-toolkit trainer, GET /api/training/settings). */
export interface TrainingSettings {
  host: string;
  toolkitDir: string;
  python: string;
  baseModel: string;
  loraFolder: string;
  sampling: boolean;
  resolution: number[];
  cacheTextEmbeddings: boolean;
}

const WEIGHT_TYPES = ['standard', 'prompt is more important', 'style transfer'] as const;
const RESOLUTIONS = [512, 768, 1024];

export function IpAdapterSection({ value, onChange }: {
  value: IpAdapterSettings;
  onChange: (v: IpAdapterSettings) => void;
}) {
  const { t } = useTranslation();
  const s = t.settings;
  const tip = useTips().settings;
  const [presets, setPresets] = useState<string[] | null>(null);

  useEffect(() => {
    let alive = true;
    fetch('/api/assets/swarmui/features')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (alive) setPresets(Array.isArray(d?.presets) ? d.presets : []); })
      .catch(() => { if (alive) setPresets([]); });
    return () => { alive = false; };
  }, []);

  // the saved preset stays selectable even when SwarmUI doesn't list it right now
  const options = presets && presets.includes(value.ipadapterPreset)
    ? presets : [value.ipadapterPreset, ...(presets || [])].filter(Boolean);
  const weightLabel: Record<string, string> = {
    standard: s.weightStandard,
    'prompt is more important': s.weightPrompt,
    'style transfer': s.weightStyle,
  };

  return (
    <div className="settings-section card">
      <h4>{s.ipadapter}</h4>
      <p className="text-sm text-secondary mb-md">{s.ipadapterDesc}</p>
      <div className="form-row">
        <div className="form-group">
          <label htmlFor="ipa-preset">{s.ipadapterPreset}</label>
          <select
            id="ipa-preset"
            className="input select"
            data-tip={tip.ipadapterPreset}
            value={value.ipadapterPreset}
            onChange={(e) => onChange({ ...value, ipadapterPreset: e.target.value })}
          >
            {options.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
          {presets !== null && presets.length === 0 && (
            <span className="text-xs text-muted">{s.ipadapterNoBackend}</span>
          )}
        </div>
        <div className="form-group">
          <label htmlFor="ipa-weight-type">{s.ipadapterWeightType}</label>
          <select
            id="ipa-weight-type"
            className="input select"
            data-tip={tip.ipadapterWeightType}
            value={value.ipadapterWeightType}
            onChange={(e) => onChange({ ...value, ipadapterWeightType: e.target.value })}
          >
            {WEIGHT_TYPES.map((w) => <option key={w} value={w}>{weightLabel[w]}</option>)}
          </select>
        </div>
      </div>
      <div className="form-group">
        <label htmlFor="ipa-end">{fill(s.ipadapterEnd, { pct: Math.round(value.ipadapterEnd * 100) })}</label>
        <input
          id="ipa-end"
          type="range"
          data-tip={tip.ipadapterEnd}
          className="slider"
          min={0.3}
          max={1}
          step={0.05}
          value={value.ipadapterEnd}
          onChange={(e) => onChange({ ...value, ipadapterEnd: parseFloat(e.target.value) })}
        />
        <span className="text-xs text-muted">{s.ipadapterEndHint}</span>
      </div>
    </div>
  );
}

export function TrainingSection({ value, onChange }: {
  value: TrainingSettings;
  onChange: (v: TrainingSettings) => void;
}) {
  const { t } = useTranslation();
  const s = t.settings;
  const tip = useTips().settings;
  const tipKey = {
    host: tip.trainingHost, toolkitDir: tip.trainingToolkitDir, python: tip.trainingPython,
    baseModel: tip.trainingBaseModel, loraFolder: tip.trainingLoraFolder,
  };
  const text = (key: 'host' | 'toolkitDir' | 'python' | 'baseModel' | 'loraFolder',
                label: string, placeholder: string) => (
    <div className="form-group">
      <label htmlFor={`training-${key}`}>{label}</label>
      <input
        id={`training-${key}`}
        className="input"
        data-tip={tipKey[key]}
        type="text"
        spellCheck={false}
        value={value[key]}
        placeholder={placeholder}
        onChange={(e) => onChange({ ...value, [key]: e.target.value })}
      />
    </div>
  );
  // the offered sizes, plus any other size saved through the API
  const sizes = [...new Set([...RESOLUTIONS, ...value.resolution])].sort((a, b) => a - b);
  const toggleSize = (r: number, on: boolean) => {
    const next = on ? [...value.resolution, r] : value.resolution.filter((x) => x !== r);
    onChange({ ...value, resolution: [...new Set(next)].sort((a, b) => a - b) });
  };

  return (
    <div className="settings-section card">
      <h4>{s.trainingTitle}</h4>
      <p className="text-sm text-secondary mb-md">{s.trainingDesc}</p>
      <div className="form-row">
        {text('host', s.trainingHost, 'user@192.168.1.31')}
        {text('toolkitDir', s.trainingToolkitDir, '~/ai-toolkit')}
      </div>
      <div className="form-row">
        {text('python', s.trainingPython, 'venv/bin/python')}
        {text('loraFolder', s.trainingLoraFolder, 'Comics')}
      </div>
      {text('baseModel', s.trainingBaseModel, '/home/user/models/model.safetensors')}
      <div className="form-group">
        <label>{s.trainingResolution}</label>
        <div className="training-resolutions">
          {sizes.map((r) => (
            <label key={r} className="training-check" data-tip={tip.trainingResolution}>
              <input
                type="checkbox"
                checked={value.resolution.includes(r)}
                disabled={value.resolution.length === 1 && value.resolution.includes(r)}
                onChange={(e) => toggleSize(r, e.target.checked)}
              />
              {r}
            </label>
          ))}
        </div>
        <span className="text-xs text-muted">{s.trainingResolutionHint}</span>
      </div>
      <div className="form-group">
        <label className="training-check" data-tip={tip.trainingSampling}>
          <input
            type="checkbox"
            checked={value.sampling}
            onChange={(e) => onChange({ ...value, sampling: e.target.checked })}
          />
          {s.trainingSampling}
        </label>
        <span className="text-xs text-muted">{s.trainingSamplingHint}</span>
      </div>
      <div className="form-group">
        <label className="training-check" data-tip={tip.trainingCacheText}>
          <input
            type="checkbox"
            checked={value.cacheTextEmbeddings}
            onChange={(e) => onChange({ ...value, cacheTextEmbeddings: e.target.checked })}
          />
          {s.trainingCacheText}
        </label>
        <span className="text-xs text-muted">{s.trainingCacheTextHint}</span>
      </div>
      <style>{`
        .training-resolutions { display: flex; gap: var(--space-md); flex-wrap: wrap; }
        .training-check {
          display: inline-flex; align-items: center; gap: var(--space-sm);
          color: var(--text-primary); cursor: pointer;
        }
        .training-check input { accent-color: var(--accent-primary); }
      `}</style>
    </div>
  );
}
