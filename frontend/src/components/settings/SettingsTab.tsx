import { useState, useEffect } from 'react';
import { FiSave, FiRefreshCw, FiCheck, FiEye, FiEyeOff, FiX } from 'react-icons/fi';
import { useProjectStore } from '../../store/projectStore';
import { useTranslation } from '../../hooks/useTranslation';
import type { AppSettings } from '../../types';

export function SettingsTab() {
  const { settings, setSettings } = useProjectStore();
  const { t } = useTranslation();
  const [localSettings, setLocalSettings] = useState<AppSettings>(settings);
  const [showApiKey, setShowApiKey] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isTestingSwarmUI, setIsTestingSwarmUI] = useState(false);
  const [swarmUIStatus, setSwarmUIStatus] = useState<boolean | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

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
    } catch (error) {
      console.error('Failed to load settings:', error);
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await fetch('/api/settings/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          api: localSettings.api,
          swarmui: localSettings.swarmui,
          defaults: localSettings.defaults,
          language: localSettings.language,
        }),
      });
      
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
            <label>Storyboard System Prompt (分镜生成)</label>
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
            <label>Prompt Enhancement System Prompt (提示词优化)</label>
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
