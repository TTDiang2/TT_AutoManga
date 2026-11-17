import { useState, useEffect } from 'react';
import { FiSave, FiRefreshCw, FiCheck, FiEye, FiEyeOff, FiX } from 'react-icons/fi';
import { useProjectStore } from '../../store/projectStore';
import { useTranslation, fill } from '../../hooks/useTranslation';
import type { AppSettings, ContentRating } from '../../types';
import { changePassword, fetchAuthStatus, fetchGoogleConfig, logout, logoutAll, setAllowedEmails, setPasswordLogin } from '../../auth';
import type { AuthStatus, GoogleConfig } from '../../auth';
import { SET_PASSWORD_CMD } from '../auth/LoginScreen';
import { IpAdapterSection, TrainingSection } from './ReferenceTrainingSettings';
import type { IpAdapterSettings, TrainingSettings } from './ReferenceTrainingSettings';

const DEFAULT_IPADAPTER: IpAdapterSettings = {
  ipadapterPreset: 'PLUS (high strength)',
  ipadapterWeightType: 'prompt is more important',
  ipadapterEnd: 0.7,
};
const DEFAULT_TRAINING: Omit<TrainingSettings, 'host' | 'baseModel'> = {
  toolkitDir: '~/ai-toolkit', python: 'venv/bin/python',
  loraFolder: 'Comics', sampling: false, resolution: [512, 768], cacheTextEmbeddings: false,
};

/** A FastAPI error body as one line: {detail: "..."} or a 422's [{loc, msg}]. */
function errorText(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((d: { loc?: unknown[]; msg?: string }) =>
      `${(d.loc || []).slice(1).join('.')}: ${String(d.msg || '').replace(/^Value error, /, '')}`).join('; ');
  }
  return `HTTP ${status}`;
}

export function SettingsTab() {
  const { settings, setSettings } = useProjectStore();
  const { t } = useTranslation();
  const [localSettings, setLocalSettings] = useState<AppSettings>(settings);
  const [showApiKey, setShowApiKey] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isTestingSwarmUI, setIsTestingSwarmUI] = useState(false);
  const [swarmUIStatus, setSwarmUIStatus] = useState<boolean | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [ipadapter, setIpadapter] = useState<IpAdapterSettings>(DEFAULT_IPADAPTER);
  // null until the server sent it: never save placeholder trainer settings
  const [training, setTraining] = useState<TrainingSettings | null>(null);
  // settings.content.defaultRating; null until loaded (never saved unloaded)
  const [defaultRating, setDefaultRating] = useState<ContentRating | null>(null);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      const response = await fetch('/api/settings/');
      const data = await response.json();
      const loadedSwarmui = data.swarmui || {};
      const loadedSettings: AppSettings = {
        api: {
          ...data.api,
          thinking: data.api?.thinking !== false,
        },
        swarmui: {
          address: loadedSwarmui.address || 'http://127.0.0.1:7801',
          activePresetId: loadedSwarmui.activePresetId || '',
          presets: loadedSwarmui.presets || [],
          currentModel: loadedSwarmui.currentModel || loadedSwarmui.model || '',
          currentLoras: loadedSwarmui.currentLoras || loadedSwarmui.loras || [],
          currentSteps: loadedSwarmui.currentSteps || loadedSwarmui.steps || 20,
          currentCfgScale: loadedSwarmui.currentCfgScale || loadedSwarmui.cfgScale || 7,
          currentWidth: loadedSwarmui.currentWidth || loadedSwarmui.width || 512,
          currentHeight: loadedSwarmui.currentHeight || loadedSwarmui.height || 768,
          currentSamplerName: loadedSwarmui.currentSamplerName || loadedSwarmui.samplerName || 'Euler',
          promptSuffix: loadedSwarmui.promptSuffix || loadedSwarmui.promptSuffix || '',
        },
        defaults: data.defaults,
        language: data.language || 'en',
      };
      setLocalSettings(loadedSettings);
      setSettings(loadedSettings);
      setIpadapter({
        ipadapterPreset: loadedSwarmui.ipadapterPreset || DEFAULT_IPADAPTER.ipadapterPreset,
        ipadapterWeightType: loadedSwarmui.ipadapterWeightType || DEFAULT_IPADAPTER.ipadapterWeightType,
        ipadapterEnd: typeof loadedSwarmui.ipadapterEnd === 'number'
          ? loadedSwarmui.ipadapterEnd : DEFAULT_IPADAPTER.ipadapterEnd,
      });
      setDefaultRating(data.content?.defaultRating === 'mature' ? 'mature' : 'sfw');
      setTraining(data.training ? { host: '', baseModel: '', ...DEFAULT_TRAINING, ...data.training } : null);
    } catch (error) {
      console.error('Failed to load settings:', error);
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    setSaveError('');
    try {
      const response = await fetch('/api/settings/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          api: localSettings.api,
          swarmui: { ...localSettings.swarmui, ...ipadapter },
          defaults: localSettings.defaults,
          ...(training ? { training } : {}),
          ...(defaultRating ? { content: { defaultRating } } : {}),
          language: localSettings.language,
        }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        setSaveError(fill(t.settings.saveFailed, { detail: errorText(body, response.status) }));
        return;
      }

      setSettings(localSettings);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2000);
    } catch (error) {
      console.error('Failed to save settings:', error);
    } finally {
      setIsSaving(false);
    }
  };

  const handleReset = async () => {
    if (!confirm('Reset all settings to defaults?')) return;
    
    try {
      await fetch('/api/settings/reset', { method: 'POST' });
      loadSettings();
    } catch (error) {
      console.error('Failed to reset settings:', error);
    }
  };

  const testSwarmUIConnection = async () => {
    setIsTestingSwarmUI(true);
    setSwarmUIStatus(null);
    
    try {
      const response = await fetch('/api/assets/swarmui/test');
      const data = await response.json();
      setSwarmUIStatus(data.connected);
    } catch {
      setSwarmUIStatus(false);
    } finally {
      setIsTestingSwarmUI(false);
    }
  };

  return (
    <div className="settings-tab">
      <div className="settings-header flex items-center justify-between mb-lg">
        <div>
          <h3>Settings</h3>
          <p className="text-sm text-secondary mt-sm">
            Configure API endpoints and application preferences
          </p>
        </div>
        <div className="flex gap-sm">
          <button className="btn btn-secondary" onClick={handleReset}>
            <FiRefreshCw size={14} /> Reset to Defaults
          </button>
          <button className="btn btn-primary" onClick={handleSave} disabled={isSaving}>
            {saveSuccess ? <FiCheck size={14} /> : <FiSave size={14} />}
            {saveSuccess ? 'Saved!' : 'Save Settings'}
          </button>
        </div>
      </div>
      {saveError && <p className="settings-save-error mb-md" role="alert">{saveError}</p>}

      <div className="settings-sections">
        <div className="settings-section card">
          <h4>OpenAI Compatible API</h4>
          <p className="text-sm text-secondary mb-md">
            Configure your AI API endpoint for storyboard and prompt generation
          </p>
          
          <div className="form-group">
            <label>API Endpoint</label>
            <input
              className="input"
              type="text"
              value={localSettings.api.endpoint}
              onChange={(e) => setLocalSettings({
                ...localSettings,
                api: { ...localSettings.api, endpoint: e.target.value }
              })}
              placeholder="https://api.openai.com/v1"
            />
          </div>

          <div className="form-group">
            <label>API Key</label>
            <div className="input-with-icon">
              <input
                className="input"
                type={showApiKey ? 'text' : 'password'}
                value={localSettings.api.api_key}
                onChange={(e) => setLocalSettings({
                  ...localSettings,
                  api: { ...localSettings.api, api_key: e.target.value }
                })}
                placeholder="sk-..."
              />
              <button 
                className="icon-btn"
                onClick={() => setShowApiKey(!showApiKey)}
              >
                {showApiKey ? <FiEyeOff size={16} /> : <FiEye size={16} />}
              </button>
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>{t.settings.model}</label>
              <input
                className="input"
                type="text"
                value={localSettings.api.model}
                onChange={(e) => setLocalSettings({
                  ...localSettings,
                  api: { ...localSettings.api, model: e.target.value }
                })}
                placeholder={t.settings.modelPlaceholder}
              />
              <span className="text-xs text-muted">{t.settings.modelHint}</span>
            </div>

            <div className="form-group">
              <label>{t.settings.thinking}</label>
              <label className="toggle-switch">
                <input
                  type="checkbox"
                  checked={localSettings.api.thinking}
                  onChange={(e) => setLocalSettings({
                    ...localSettings,
                    api: { ...localSettings.api, thinking: e.target.checked }
                  })}
                />
                <span className="toggle-slider"></span>
              </label>
              <span className="text-xs text-muted">{t.settings.thinkingHint}</span>
            </div>

            <div className="form-group">
              <label>Temperature</label>
              <input
                className="input"
                type="number"
                min={0}
                max={2}
                step={0.1}
                value={localSettings.api.temperature}
                onChange={(e) => setLocalSettings({
                  ...localSettings,
                  api: { ...localSettings.api, temperature: parseFloat(e.target.value) }
                })}
              />
              <input 
                type="range" 
                className="slider mt-sm"
                min={0}
                max={2}
                step={0.1}
                value={localSettings.api.temperature}
                onChange={(e) => setLocalSettings({
                  ...localSettings,
                  api: { ...localSettings.api, temperature: parseFloat(e.target.value) }
                })}
              />
            </div>

            <div className="form-group">
              <label>Max Tokens</label>
              <input
                className="input"
                type="number"
                min={100}
                max={10000}
                step={100}
                value={localSettings.api.max_tokens}
                onChange={(e) => setLocalSettings({
                  ...localSettings,
                  api: { ...localSettings.api, max_tokens: parseInt(e.target.value) }
                })}
              />
            </div>
          </div>

          <div className="form-group mt-md">
            <label>{t.settings.storyboardSystemPrompt}</label>
            <div className="flex gap-sm items-start">
              <select
                className="input select"
                style={{ minWidth: '160px' }}
                value={localSettings.api.storyboardPresets?.find(p => p.content === localSettings.api.storyboard_system_prompt)?.id || ''}
                onChange={(e) => {
                  const presetId = e.target.value;
                  if (presetId) {
                    const preset = localSettings.api.storyboardPresets?.find(p => p.id === presetId);
                    if (preset) {
                      setLocalSettings({ ...localSettings, api: { ...localSettings.api, storyboard_system_prompt: preset.content } });
                    }
                  }
                }}
              >
                <option value="">— Select preset —</option>
                {(localSettings.api.storyboardPresets || []).map(p => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
              <button
                className="btn btn-secondary"
                style={{ flexShrink: 0, padding: '6px 12px' }}
                onClick={() => {
                  const name = prompt('Preset name:');
                  if (!name || !localSettings.api.storyboard_system_prompt.trim()) return;
                  const newPreset = { id: Date.now().toString(), name, content: localSettings.api.storyboard_system_prompt };
                  setLocalSettings({
                    ...localSettings,
                    api: { ...localSettings.api, storyboardPresets: [...(localSettings.api.storyboardPresets || []), newPreset] }
                  });
                }}
              >
                Save Current as Preset
              </button>
              {(localSettings.api.storyboardPresets || []).length > 0 && (
                <button
                  className="btn btn-ghost"
                  style={{ color: '#ef4444', flexShrink: 0 }}
                  onClick={() => {
                    const idToDelete = localSettings.api.storyboardPresets?.find(p => p.content === localSettings.api.storyboard_system_prompt)?.id;
                    if (idToDelete) {
                      setLocalSettings({ ...localSettings, api: { ...localSettings.api, storyboardPresets: (localSettings.api.storyboardPresets || []).filter(p => p.id !== idToDelete) } });
                    }
                  }}
                >
                  Delete
                </button>
              )}
            </div>
            <textarea
              className="input textarea"
              value={localSettings.api.storyboard_system_prompt || ''}
              onChange={(e) => setLocalSettings({
                ...localSettings,
                api: { ...localSettings.api, storyboard_system_prompt: e.target.value }
              })}
              placeholder="System prompt for storyboard generation..."
              rows={3}
            />
          </div>

          <div className="form-group">
            <label>{t.settings.enhanceSystemPrompt}</label>
            <div className="flex gap-sm items-start">
              <select
                className="input select"
                style={{ minWidth: '160px' }}
                value={localSettings.api.promptPresets?.find(p => p.content === localSettings.api.prompt_system_prompt)?.id || ''}
                onChange={(e) => {
                  const presetId = e.target.value;
                  if (presetId) {
                    const preset = localSettings.api.promptPresets?.find(p => p.id === presetId);
                    if (preset) {
                      setLocalSettings({ ...localSettings, api: { ...localSettings.api, prompt_system_prompt: preset.content } });
                    }
                  }
                }}
              >
                <option value="">— Select preset —</option>
                {(localSettings.api.promptPresets || []).map(p => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
              <button
                className="btn btn-secondary"
                style={{ flexShrink: 0, padding: '6px 12px' }}
                onClick={() => {
                  const name = prompt('Preset name:');
                  if (!name || !localSettings.api.prompt_system_prompt.trim()) return;
                  const newPreset = { id: Date.now().toString(), name, content: localSettings.api.prompt_system_prompt };
                  setLocalSettings({
                    ...localSettings,
                    api: { ...localSettings.api, promptPresets: [...(localSettings.api.promptPresets || []), newPreset] }
                  });
                }}
              >
                Save Current as Preset
              </button>
              {(localSettings.api.promptPresets || []).length > 0 && (
                <button
                  className="btn btn-ghost"
                  style={{ color: '#ef4444', flexShrink: 0 }}
                  onClick={() => {
                    const idToDelete = localSettings.api.promptPresets?.find(p => p.content === localSettings.api.prompt_system_prompt)?.id;
                    if (idToDelete) {
                      setLocalSettings({ ...localSettings, api: { ...localSettings.api, promptPresets: (localSettings.api.promptPresets || []).filter(p => p.id !== idToDelete) } });
                    }
                  }}
                >
                  Delete
                </button>
              )}
            </div>
            <textarea
              className="input textarea"
              value={localSettings.api.prompt_system_prompt || ''}
              onChange={(e) => setLocalSettings({
                ...localSettings,
                api: { ...localSettings.api, prompt_system_prompt: e.target.value }
              })}
              placeholder="System prompt for prompt enhancement..."
              rows={3}
            />
          </div>
        </div>

        <div className="settings-section card">
          <h4>{t.settings.swarmui}</h4>
          <p className="text-sm text-secondary mb-md">
            {t.settings.swarmuiDesc}
          </p>
          
          <div className="form-group">
            <label>{t.settings.address}</label>
            <div className="flex gap-sm">
              <input
                className="input"
                type="text"
                value={localSettings.swarmui.address}
                onChange={(e) => setLocalSettings({
                  ...localSettings,
                  swarmui: { ...localSettings.swarmui, address: e.target.value }
                })}
                placeholder="http://127.0.0.1:7801"
              />
              <button 
                className="btn btn-secondary"
                onClick={testSwarmUIConnection}
                disabled={isTestingSwarmUI}
              >
                {isTestingSwarmUI ? (
                  <span className="loading-spinner" />
                ) : swarmUIStatus === true ? (
                  <><FiCheck size={14} /> {t.settings.connected || 'Connected'}</>
                ) : swarmUIStatus === false ? (
                  <><FiX size={14} /> {t.settings.failed || 'Failed'}</>
                ) : (
                  t.settings.testConnection
                )}
              </button>
            </div>
          </div>

          <div className="form-group">
            <label>Preset</label>
            <div className="flex gap-sm items-center">
              <select
                className="input select"
                style={{ minWidth: '200px' }}
                value={localSettings.swarmui.activePresetId}
                onChange={(e) => {
                  const presetId = e.target.value;
                  if (presetId === '__custom__') {
                    setLocalSettings({
                      ...localSettings,
                      swarmui: { ...localSettings.swarmui, activePresetId: '' }
                    });
                  } else {
                    const preset = localSettings.swarmui.presets.find(p => p.id === presetId);
                    if (preset) {
                      setLocalSettings({
                        ...localSettings,
                        swarmui: {
                          ...localSettings.swarmui,
                          activePresetId: presetId,
                          currentModel: preset.model,
                          currentLoras: preset.loras,
                          currentSteps: preset.steps,
                          currentCfgScale: preset.cfgScale,
                          currentWidth: preset.width,
                          currentHeight: preset.height,
                          currentSamplerName: preset.samplerName,
                          promptSuffix: preset.promptSuffix ?? '',
                        }
                      });
                    }
                  }
                }}
              >
                <option value="">Custom (no preset)</option>
                {(localSettings.swarmui.presets || []).map(preset => (
                  <option key={preset.id} value={preset.id}>{preset.name}</option>
                ))}
              </select>
              <button
                className="btn btn-secondary"
                onClick={() => {
                  const name = prompt('Preset name:');
                  if (!name) return;
                  const newPreset = {
                    id: Date.now().toString(),
                    name,
                    model: localSettings.swarmui.currentModel,
                    loras: localSettings.swarmui.currentLoras,
                    steps: localSettings.swarmui.currentSteps,
                    cfgScale: localSettings.swarmui.currentCfgScale,
                    width: localSettings.swarmui.currentWidth,
                    height: localSettings.swarmui.currentHeight,
                    samplerName: localSettings.swarmui.currentSamplerName,
                    promptSuffix: localSettings.swarmui.promptSuffix,
                  };
                  setLocalSettings({
                    ...localSettings,
                    swarmui: {
                      ...localSettings.swarmui,
                      presets: [...(localSettings.swarmui.presets || []), newPreset],
                      activePresetId: newPreset.id,
                    }
                  });
                }}
              >
                Save Current as Preset
              </button>
              {localSettings.swarmui.activePresetId && (
                <button
                  className="btn btn-ghost"
                  onClick={() => {
                    setLocalSettings({
                      ...localSettings,
                      swarmui: {
                        ...localSettings.swarmui,
                        presets: (localSettings.swarmui.presets || []).filter(p => p.id !== localSettings.swarmui.activePresetId),
                        activePresetId: '',
                      }
                    });
                  }}
                >
                  <FiX size={14} /> Delete
                </button>
              )}
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Model (SD Model)</label>
              <input
                className="input"
                type="text"
                value={localSettings.swarmui.currentModel}
                onChange={(e) => setLocalSettings({
                  ...localSettings,
                  swarmui: { ...localSettings.swarmui, currentModel: e.target.value, activePresetId: '' }
                })}
                placeholder="e.g., amanatsuIllustrious_v2"
              />
            </div>
            <div className="form-group">
              <label>Sampler</label>
              <select
                className="input select"
                value={localSettings.swarmui.currentSamplerName}
                onChange={(e) => setLocalSettings({
                  ...localSettings,
                  swarmui: { ...localSettings.swarmui, currentSamplerName: e.target.value, activePresetId: '' }
                })}
              >
                <option value="Euler">Euler</option>
                <option value="Euler a">Euler a</option>
                <option value="DPM++ 2M">DPM++ 2M</option>
                <option value="DPM++ SDE">DPM++ SDE</option>
                <option value="DDIM">DDIM</option>
                <option value="UniPC">UniPC</option>
              </select>
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Steps</label>
              <input
                className="input"
                type="number"
                min={1}
                max={100}
                value={localSettings.swarmui.currentSteps}
                onChange={(e) => setLocalSettings({
                  ...localSettings,
                  swarmui: { ...localSettings.swarmui, currentSteps: parseInt(e.target.value) || 20, activePresetId: '' }
                })}
              />
            </div>
            <div className="form-group">
              <label>CFG Scale</label>
              <input
                className="input"
                type="number"
                min={1}
                max={30}
                step={0.5}
                value={localSettings.swarmui.currentCfgScale}
                onChange={(e) => setLocalSettings({
                  ...localSettings,
                  swarmui: { ...localSettings.swarmui, currentCfgScale: parseFloat(e.target.value) || 7, activePresetId: '' }
                })}
              />
            </div>
          </div>

          <div className="form-group">
            <label>Aspect Ratio</label>
            <div className="flex gap-sm flex-wrap">
              {[
                { label: '1:1 (512)', w: 512, h: 512 },
                { label: '1:1 (1024)', w: 1024, h: 1024 },
                { label: '3:4 (768x1024)', w: 768, h: 1024 },
                { label: '5:8 (768x1216)', w: 768, h: 1216 },
                { label: '9:16 (768x1344)', w: 768, h: 1344 },
                { label: '9:16 (1024)', w: 1024, h: 1820 },
                { label: '2:3 (512x768)', w: 512, h: 768 },
                { label: '16:9 (1920x1080)', w: 1920, h: 1080 },
              ].map(ratio => (
                <button
                  key={ratio.label}
                  className={`btn btn-sm ${localSettings.swarmui.currentWidth === ratio.w && localSettings.swarmui.currentHeight === ratio.h ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setLocalSettings({
                    ...localSettings,
                    swarmui: { ...localSettings.swarmui, currentWidth: ratio.w, currentHeight: ratio.h, activePresetId: '' }
                  })}
                >
                  {ratio.label}
                </button>
              ))}
            </div>
          </div>

          <div className="form-group">
            <label>LoRA Models</label>
            <div className="lora-list">
              {(localSettings.swarmui.currentLoras || []).map((lora, idx) => (
                <div key={idx} className="lora-item flex items-center gap-sm mb-sm">
                  <input
                    className="input"
                    type="text"
                    value={lora.name}
                    onChange={(e) => {
                      const newLoras = [...(localSettings.swarmui.currentLoras || [])];
                      newLoras[idx] = { ...newLoras[idx], name: e.target.value };
                      setLocalSettings({
                        ...localSettings,
                        swarmui: { ...localSettings.swarmui, currentLoras: newLoras, activePresetId: '' }
                      });
                    }}
                    placeholder="lora_name.safetensors"
                  />
                  <input
                    className="input"
                    type="number"
                    min={-2}
                    max={2}
                    step={0.1}
                    value={lora.weight}
                    onChange={(e) => {
                      const newLoras = [...(localSettings.swarmui.currentLoras || [])];
                      newLoras[idx] = { ...newLoras[idx], weight: parseFloat(e.target.value) || 1 };
                      setLocalSettings({
                        ...localSettings,
                        swarmui: { ...localSettings.swarmui, currentLoras: newLoras, activePresetId: '' }
                      });
                    }}
                    style={{ width: '80px' }}
                  />
                  <button
                    className="btn btn-ghost"
                    onClick={() => {
                      const newLoras = (localSettings.swarmui.currentLoras || []).filter((_, i) => i !== idx);
                      setLocalSettings({
                        ...localSettings,
                        swarmui: { ...localSettings.swarmui, currentLoras: newLoras, activePresetId: '' }
                      });
                    }}
                  >
                    <FiX size={14} />
                  </button>
                </div>
              ))}
              <button
                className="btn btn-secondary"
                onClick={() => {
                  setLocalSettings({
                    ...localSettings,
                    swarmui: {
                      ...localSettings.swarmui,
                      currentLoras: [...(localSettings.swarmui.currentLoras || []), { name: '', weight: 1 }],
                      activePresetId: ''
                    }
                  });
                }}
              >
                + Add LoRA
              </button>
            </div>
            <span className="text-xs text-muted">Format: lora_name.safetensors, weight typically -2 to 2</span>
          </div>

          <div className="form-group mt-md">
            <label>Prompt Suffix</label>
            <textarea
              className="input textarea"
              rows={3}
              value={localSettings.swarmui.promptSuffix}
              onChange={(e) => setLocalSettings({
                ...localSettings,
                swarmui: { ...localSettings.swarmui, promptSuffix: e.target.value, activePresetId: '' }
              })}
              placeholder="score_9, score_8_up, <lora:Anime_in_real:0.17>..."
            />
            <span className="text-xs text-muted">
              {t.settings.promptSuffixHint || 'Automatically appended to all generation prompts. Good for quality tags, LoRA activations, and style keywords.'}
            </span>
          </div>
        </div>

        <IpAdapterSection value={ipadapter} onChange={setIpadapter} />

        {training && <TrainingSection value={training} onChange={setTraining} />}

        <div className="settings-section card">
          <h4>Default Settings</h4>
          <p className="text-sm text-secondary mb-md">
            Configure default values for new projects
          </p>
          
          <div className="form-row">
            <div className="form-group">
              <label>Language / 语言</label>
              <select
                className="input select"
                value={localSettings.language}
                onChange={(e) => setLocalSettings({
                  ...localSettings,
                  language: e.target.value
                })}
              >
                <option value="en">English</option>
                <option value="zh">中文</option>
              </select>
            </div>

            <div className="form-group">
              <label>Default Detail Level</label>
              <input
                className="input"
                type="number"
                min={1}
                max={5}
                value={localSettings.defaults.detailLevel}
                onChange={(e) => setLocalSettings({
                  ...localSettings,
                  defaults: { ...localSettings.defaults, detailLevel: parseInt(e.target.value) }
                })}
              />
              <input 
                type="range" 
                className="slider mt-sm"
                min={1}
                max={5}
                value={localSettings.defaults.detailLevel}
                onChange={(e) => setLocalSettings({
                  ...localSettings,
                  defaults: { ...localSettings.defaults, detailLevel: parseInt(e.target.value) }
                })}
              />
              <div className="range-labels">
                <span>Abstract</span>
                <span>Detailed</span>
              </div>
            </div>

            <div className="form-group">
              <label>Export Quality</label>
              <select
                className="input select"
                value={localSettings.defaults.exportQuality}
                onChange={(e) => setLocalSettings({
                  ...localSettings,
                  defaults: { ...localSettings.defaults, exportQuality: e.target.value }
                })}
              >
                <option value="standard">Standard</option>
                <option value="high">High</option>
              </select>
            </div>

            <div className="form-group">
              <label>Auto-save Interval (seconds)</label>
              <input
                className="input"
                type="number"
                min={30}
                max={600}
                step={30}
                value={localSettings.defaults.autoSaveInterval}
                onChange={(e) => setLocalSettings({
                  ...localSettings,
                  defaults: { ...localSettings.defaults, autoSaveInterval: parseInt(e.target.value) }
                })}
              />
            </div>
          </div>
        </div>

        {defaultRating && (
          <div className="settings-section card">
            <h4>{t.settings.contentTitle}</h4>
            <p className="text-sm text-secondary mb-md">{t.settings.contentHint}</p>
            <div className="form-row">
              <div className="form-group">
                <label htmlFor="content-default-rating">{t.settings.defaultRating}</label>
                <select
                  id="content-default-rating"
                  className="input select"
                  value={defaultRating}
                  onChange={(e) => {
                    const v = e.target.value === 'mature' ? 'mature' : 'sfw';
                    if (v === 'mature' && !confirm(t.settings.matureConfirm)) return;
                    setDefaultRating(v);
                  }}
                >
                  <option value="sfw">{t.settings.ratingSfw}</option>
                  <option value="mature">{t.settings.ratingMature}</option>
                </select>
              </div>
            </div>
            <p className="text-sm text-secondary mt-sm">{t.settings.contentRules}</p>
          </div>
        )}

        <AccessSection />
      </div>

      <style>{`
        .settings-sections {
          display: flex;
          flex-direction: column;
          gap: var(--space-lg);
          max-width: 800px;
        }
        .settings-section {
          padding: var(--space-lg);
        }
        .settings-save-error {
          color: var(--error, #ef4444);
          font-size: 13px;
        }
        .settings-section h4 {
          font-size: 16px;
          font-weight: 600;
          margin-bottom: var(--space-xs);
        }
        .form-group {
          margin-bottom: var(--space-md);
        }
        .form-group label {
          display: block;
          font-size: 13px;
          font-weight: 500;
          color: var(--text-secondary);
          margin-bottom: var(--space-xs);
        }
        .form-group .input {
          width: 100%;
        }
        .form-row {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
          gap: var(--space-md);
        }
        .input-with-icon {
          position: relative;
        }
        .input-with-icon .input {
          padding-right: 40px;
        }
        .input-with-icon .icon-btn {
          position: absolute;
          right: 8px;
          top: 50%;
          transform: translateY(-50%);
          background: none;
          border: none;
          cursor: pointer;
          color: var(--text-muted);
          padding: var(--space-xs);
        }
        .input-with-icon .icon-btn:hover {
          color: var(--text-primary);
        }
        .range-labels {
          display: flex;
          justify-content: space-between;
          font-size: 11px;
          color: var(--text-muted);
          margin-top: var(--space-xs);
        }
        .slider {
          width: 100%;
        }
        .toggle-switch {
          position: relative;
          display: inline-block;
          width: 48px;
          height: 24px;
        }
        .toggle-switch input {
          opacity: 0;
          width: 0;
          height: 0;
        }
        .toggle-slider {
          position: absolute;
          cursor: pointer;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background-color: var(--border-default);
          transition: 0.3s;
          border-radius: 24px;
        }
        .toggle-slider:before {
          position: absolute;
          content: "";
          height: 18px;
          width: 18px;
          left: 3px;
          bottom: 3px;
          background-color: white;
          transition: 0.3s;
          border-radius: 50%;
        }
        .toggle-switch input:checked + .toggle-slider {
          background-color: var(--accent-primary);
        }
        .toggle-switch input:checked + .toggle-slider:before {
          transform: translateX(24px);
        }
      `}</style>
    </div>
  );
}

/** Settings → Access: the login gate (backend/core/auth.py). */
function AccessSection() {
  const { t } = useTranslation();
  const a = t.auth;
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirmNext, setConfirmNext] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const refresh = () => { fetchAuthStatus().then(setStatus).catch(() => setStatus(null)); };
  useEffect(refresh, []);

  if (!status) return null;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (next !== confirmNext) { setMsg({ ok: false, text: a.mismatch }); return; }
    if (next.length < 8) { setMsg({ ok: false, text: a.tooShort }); return; }
    setBusy(true);
    const r = await changePassword(current, next);
    setBusy(false);
    if (r.ok) {
      setCurrent(''); setNext(''); setConfirmNext('');
      setMsg({ ok: true, text: a.passwordChanged });
    } else {
      setMsg({ ok: false, text: r.reason === 'wrong' ? a.wrongCurrent
        : r.reason === 'rate' ? a.rateLimited.replace('{s}', String(r.retryAfter ?? 60))
        : r.detail || a.error });
    }
  };

  const signOutAll = async () => {
    if (!confirm(a.signOutAllConfirm)) return;
    const r = await logoutAll();
    if (r.ok) {
      setMsg({ ok: true, text: a.signedOutAll });
      if (!status.local) window.location.reload();
    } else setMsg({ ok: false, text: r.detail || a.error });
  };

  const signOut = async () => {
    await logout();
    window.location.reload();
  };

  return (
    <div className="settings-section card">
      <h4>{a.accessTitle}</h4>
      <p className="text-sm text-secondary mb-md">{a.accessDesc}</p>

      {status.local && <p className="access-note">{a.localNote}</p>}
      {!status.local && status.authenticated && (
        <p className="access-note">{status.email ? fill(a.signedInAs, { email: status.email }) : a.remoteNote}</p>
      )}

      <GoogleAccess onChange={refresh} />

      {!status.configured ? (
        <div className="form-group">
          <p className="text-sm text-secondary mb-sm">{a.notConfigured}</p>
          <code className="access-code">{SET_PASSWORD_CMD}</code>
        </div>
      ) : (
        <>
          <form onSubmit={submit} className="access-form">
            <input type="text" name="username" autoComplete="username" value="automanga"
                   readOnly hidden />
            <div className="form-row">
              <div className="form-group">
                <label htmlFor="access-current">{a.currentPassword}</label>
                <input id="access-current" className="input" type="password"
                       autoComplete="current-password" value={current} required
                       onChange={(e) => setCurrent(e.target.value)} />
              </div>
              <div className="form-group">
                <label htmlFor="access-new">{a.newPassword}</label>
                <input id="access-new" className="input" type="password"
                       autoComplete="new-password" minLength={8} value={next} required
                       onChange={(e) => setNext(e.target.value)} />
              </div>
              <div className="form-group">
                <label htmlFor="access-confirm">{a.confirmPassword}</label>
                <input id="access-confirm" className="input" type="password"
                       autoComplete="new-password" minLength={8} value={confirmNext} required
                       onChange={(e) => setConfirmNext(e.target.value)} />
              </div>
            </div>
            <div className="access-actions">
              <button type="submit" className="btn btn-primary"
                      disabled={busy || !current || !next || !confirmNext}>
                {a.changePassword}
              </button>
              {!status.local && status.authenticated && (
                <button type="button" className="btn btn-secondary" onClick={signOut}>
                  {a.signOut}
                </button>
              )}
              <button type="button" className="btn btn-secondary" onClick={signOutAll}>
                {a.signOutAll}
              </button>
            </div>
          </form>
        </>
      )}
      {msg && (
        <p className={`access-msg ${msg.ok ? 'access-msg--ok' : 'access-msg--err'}`} role="status">
          {msg.text}
        </p>
      )}
      <style>{`
        .access-note {
          font-size: 13px;
          color: var(--text-primary);
          background: var(--bg-tertiary);
          border: 1px solid var(--border-default);
          border-radius: var(--radius-sm);
          padding: var(--space-sm) var(--space-md);
          margin-bottom: var(--space-md);
        }
        .access-code {
          display: block;
          padding: var(--space-sm) var(--space-md);
          border-radius: var(--radius-sm);
          background: var(--bg-tertiary);
          border: 1px solid var(--border-default);
          color: var(--text-primary);
          font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
          font-size: 12px;
          word-break: break-all;
          user-select: all;
        }
        .access-form .input { width: 100%; }
        .access-actions { display: flex; flex-wrap: wrap; gap: var(--space-sm); }
        .access-msg { font-size: 13px; margin-top: var(--space-md); }
        .access-msg--ok { color: var(--success); }
        .access-msg--err { color: var(--error); }
        .access-google { border-top: 1px solid var(--border-default); padding-top: var(--space-md); margin-bottom: var(--space-md); }
        .access-google h5 { font-size: 14px; font-weight: 600; margin: 0 0 var(--space-xs); }
        .access-emails { list-style: none; padding: 0; margin: 0 0 var(--space-sm); display: flex; flex-direction: column; gap: var(--space-xs); }
        .access-emails li { display: flex; align-items: center; justify-content: space-between; gap: var(--space-sm);
          font-size: 13px; padding: var(--space-xs) var(--space-sm); border: 1px solid var(--border-default);
          border-radius: var(--radius-sm); background: var(--bg-tertiary); overflow-wrap: anywhere; }
        .access-email-add { display: flex; gap: var(--space-sm); }
        .access-email-add .input { flex: 1; min-width: 0; }
        .access-toggle-row { display: flex; align-items: center; gap: var(--space-sm); margin-top: var(--space-md); }
      `}</style>
    </div>
  );
}

const SET_GOOGLE_CMD = '.venv/bin/python -m backend.core.auth set-google';
const SET_PUBLIC_URL_CMD = '.venv/bin/python -m backend.core.auth set-public-url https://<public host>';
const EMAIL_RE = /^[^@\s<>()[\],;:"]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$/;

/** Settings → Access → Sign in with Google: allowed accounts and the
    password-login switch (backend/api/auth_google.py; docs/GOOGLE_LOGIN.md). */
function GoogleAccess({ onChange }: { onChange: () => void }) {
  const { t } = useTranslation();
  const a = t.auth;
  const [cfg, setCfg] = useState<GoogleConfig | null>(null);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const load = () => { fetchGoogleConfig().then(setCfg).catch(() => setCfg(null)); };
  useEffect(load, []);

  if (!cfg) return null;

  const saveEmails = async (emails: string[]) => {
    setBusy(true);
    const r = await setAllowedEmails(emails);
    setBusy(false);
    if (r.ok) {
      setMsg({ ok: true, text: a.saved });
      setDraft('');
      load();
      onChange();
    } else setMsg({ ok: false, text: r.detail || a.error });
  };

  const add = (e: React.FormEvent) => {
    e.preventDefault();
    const email = draft.trim().toLowerCase();
    if (!EMAIL_RE.test(email)) { setMsg({ ok: false, text: a.invalidEmail }); return; }
    if (cfg.allowedEmails.includes(email)) { setDraft(''); return; }
    saveEmails([...cfg.allowedEmails, email]);
  };

  const togglePassword = async (enabled: boolean) => {
    setBusy(true);
    const r = await setPasswordLogin(enabled);
    setBusy(false);
    if (r.ok) { setMsg({ ok: true, text: a.saved }); load(); onChange(); }
    else setMsg({ ok: false, text: r.detail || a.error });
  };

  return (
    <div className="access-google">
      <h5>{a.googleTitle}</h5>
      {!cfg.configured ? (
        <div className="form-group">
          <p className="text-sm text-secondary mb-sm">{a.googleNotConfigured}</p>
          <code className="access-code">{SET_GOOGLE_CMD}</code>
        </div>
      ) : !cfg.publicUrl ? (
        <div className="form-group">
          <p className="text-sm text-secondary mb-sm">{a.googleNoPublicUrl}</p>
          <code className="access-code">{SET_PUBLIC_URL_CMD}</code>
        </div>
      ) : (
        <>
          <p className="text-sm text-secondary mb-sm">{fill(a.googleDesc, { url: cfg.publicUrl })}</p>
          <div className="form-group">
            <label>{a.redirectUri}</label>
            <code className="access-code">{cfg.redirectUri}</code>
          </div>
        </>
      )}

      {(cfg.configured || cfg.allowedEmails.length > 0) && (
        <div className="form-group">
          <label htmlFor="access-email">{a.allowedEmails}</label>
          {cfg.allowedEmails.length === 0
            ? <p className="text-sm text-secondary mb-sm">{a.noEmails}</p>
            : (
              <ul className="access-emails">
                {cfg.allowedEmails.map((email) => (
                  <li key={email}>
                    <span>{email}</span>
                    <button type="button" className="btn btn-ghost btn-icon" disabled={busy}
                            title={fill(a.removeEmail, { email })} aria-label={fill(a.removeEmail, { email })}
                            onClick={() => saveEmails(cfg.allowedEmails.filter((x) => x !== email))}>
                      <FiX size={14} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          <form className="access-email-add" onSubmit={add}>
            <input id="access-email" className="input" type="email" autoComplete="off"
                   placeholder={a.emailPlaceholder} value={draft}
                   onChange={(e) => setDraft(e.target.value)} />
            <button type="submit" className="btn btn-secondary" disabled={busy || !draft.trim()}>
              {a.addEmail}
            </button>
          </form>
        </div>
      )}

      {cfg.password && (
        <div className="access-toggle-row">
          <label className="toggle-switch">
            <input type="checkbox" checked={cfg.passwordLogin} disabled={busy}
                   aria-label={a.passwordLoginToggle}
                   onChange={(e) => togglePassword(e.target.checked)} />
            <span className="toggle-slider"></span>
          </label>
          <span className="text-sm">{a.passwordLoginToggle}</span>
        </div>
      )}
      {cfg.password && <p className="text-sm text-secondary">{a.passwordLoginHint}</p>}

      {msg && (
        <p className={`access-msg ${msg.ok ? 'access-msg--ok' : 'access-msg--err'}`} role="status">
          {msg.text}
        </p>
      )}
    </div>
  );
}
