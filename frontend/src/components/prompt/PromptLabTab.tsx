import { useState, useEffect, useRef } from 'react';
import { FiRefreshCw, FiCopy, FiCheck, FiZap, FiTag, FiShuffle, FiUpload } from 'react-icons/fi';
import { useProjectStore } from '../../store/projectStore';
import { useTips } from '../../hooks/useTips';
import { useTranslation, fill } from '../../hooks/useTranslation';
import type { Panel } from '../../types';
import { tagsText } from './promptTags';

// response shapes of /api/prompt/enhance and /api/prompt/batch-enhance
interface EnhanceResponse {
  detail?: string;
  enhanced_prompt?: string;
  error?: string;
  results?: Array<{ enhanced_prompt?: string; error?: string }>;
}

// one entry of the JSON array accepted by the import modal
interface ImportedPrompt {
  positive?: string;
  negative?: string;
  seed?: number | string;
}

function toErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function PromptLabTab() {
  const { panels, updatePanelPrompt, settings, promptMode, setPromptMode, addPanel } = useProjectStore();
  const { t } = useTranslation();
  const tip = useTips().prompt;
  const [selectedPanelId, setSelectedPanelId] = useState<string>('');
  const [inputText, setInputText] = useState('');
  const [outputText, setOutputText] = useState('');
  const [negativePrompt, setNegativePrompt] = useState('');
  const [seed, setSeed] = useState('');
  const [removeBG, setRemoveBG] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generatingSeconds, setGeneratingSeconds] = useState(0);
  const [errorMessage, setErrorMessage] = useState('');
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<number | null>(null);
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [importJson, setImportJson] = useState('');
  const [importCopied, setImportCopied] = useState(false);

  const importExample = `[
  { "panel": 1, "positive": "1girl, masterpiece, best quality...", "negative": "low quality, blurry...", "seed": 12345 },
  { "panel": 2, "positive": "1boy, detailed face...", "negative": "blurry, distorted..." }
]`;

  const handleCopyExample = () => {
    navigator.clipboard.writeText(importExample);
    setImportCopied(true);
    setTimeout(() => setImportCopied(false), 2000);
  };
  const [importError, setImportError] = useState('');

  // Sync the editor fields when the user picks another panel (or switches
  // prompt mode) — not on every store update to that panel, which would wipe
  // unsaved negative prompt / seed / removeBG edits when e.g. the enhanced
  // prompt arrives. Read the panel from the store so the panel object isn't
  // a dependency.
  useEffect(() => {
    const panel = useProjectStore.getState().panels.find(p => p.id === selectedPanelId);
    if (panel) {
      setInputText(panel.scene);
      if (promptMode === 'turbo') {
        setOutputText(panel.prompt.turbo || '');
      } else {
        setOutputText(tagsText(panel.prompt.tags));
      }
      setNegativePrompt(panel.prompt.negativePrompt || '');
      setSeed(panel.prompt.seed != null ? String(panel.prompt.seed) : '');
      setRemoveBG(panel.prompt.removeBG || false);
    }
  }, [selectedPanelId, promptMode]);

  const handleImport = () => {
    setImportError('');
    let data: ImportedPrompt[];
    try {
      data = JSON.parse(importJson) as ImportedPrompt[];
      if (!Array.isArray(data)) throw new Error('Expected an array');
    } catch {
      setImportError('Invalid JSON. Please check format.');
      return;
    }
    let imported = 0;
    const startOrder = panels.length;
    data.forEach((item, idx) => {
      if (!item.positive) return;
      const id = `import-${Date.now()}-${idx}`;
      const panel: Panel = {
        id,
        order: startOrder + idx,
        scene: (item.positive || '').substring(0, 80),
        characters: [],
        dialogue: '',
        prompt: {
          turbo: item.positive || '',
          tags: (item.positive || '').split(',').map((t: string) => t.trim()),
          negativePrompt: item.negative || '',
          seed: item.seed != null ? Number(item.seed) : undefined,
        },
      };
      addPanel(panel);
      imported++;
    });
    setImportModalOpen(false);
    setImportJson('');
    alert(t.prompt.importSuccess?.replace('{n}', String(imported)) || `Imported ${imported} panel(s).`);
  };

  const stopTimer = () => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  const startTimer = () => {
    setGeneratingSeconds(0);
    stopTimer();
    timerRef.current = window.setInterval(() => {
      setGeneratingSeconds((s) => s + 1);
    }, 1000);
  };

  const handleGenerate = async () => {
    if (!inputText.trim()) return;

    setErrorMessage('');
    setIsGenerating(true);
    startTimer();
    try {
      const response = await fetch('/api/prompt/enhance', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scene_description: inputText,
          mode: promptMode,
          endpoint: settings.api.endpoint,
          api_key: settings.api.api_key,
          model: settings.api.model,
        }),
      });

      let data: EnhanceResponse | null = null;
      try {
        data = await response.json() as EnhanceResponse;
      } catch {
        data = null;
      }

      if (!response.ok) {
        const detail = data?.detail || `HTTP ${response.status}`;
        setErrorMessage(fill(t.prompt.backendError, { status: response.status, detail }));
        return;
      }

      if (data?.error) {
        setErrorMessage(fill(t.prompt.llmFailed, { error: data.error }));
        return;
      }

      if (data?.enhanced_prompt) {
        setOutputText(data.enhanced_prompt);

        if (promptMode === 'turbo') {
          updatePanelPrompt(selectedPanelId, { turbo: data.enhanced_prompt });
        } else {
          const tags = data.enhanced_prompt.split(',').map((t: string) => t.trim());
          updatePanelPrompt(selectedPanelId, { tags });
        }
      } else {
        setErrorMessage(t.prompt.emptyResult);
      }
    } catch (error) {
      console.error('Enhancement failed:', error);
      setErrorMessage(fill(t.prompt.networkError, { error: toErrorMessage(error) }));
    } finally {
      stopTimer();
      setIsGenerating(false);
    }
  };

  const handleBatchRefresh = async () => {
    if (panels.length === 0) return;

    setErrorMessage('');
    setIsGenerating(true);
    startTimer();
    try {
      const scenes = panels.map(p => p.scene);
      const response = await fetch('/api/prompt/batch-enhance', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scenes,
          mode: promptMode,
          endpoint: settings.api.endpoint,
          api_key: settings.api.api_key,
          model: settings.api.model,
        }),
      });

      let data: EnhanceResponse | null = null;
      try {
        data = await response.json() as EnhanceResponse;
      } catch {
        data = null;
      }

      if (!response.ok) {
        const detail = data?.detail || `HTTP ${response.status}`;
        setErrorMessage(fill(t.prompt.backendError, { status: response.status, detail }));
        return;
      }

      if (data?.results) {
        let success = 0;
        let failed = 0;
        data.results.forEach((result, idx: number) => {
          if (result.enhanced_prompt) {
            success++;
            const panelId = panels[idx].id;
            if (promptMode === 'turbo') {
              updatePanelPrompt(panelId, { turbo: result.enhanced_prompt });
            } else {
              const tags = result.enhanced_prompt.split(',').map((t: string) => t.trim());
              updatePanelPrompt(panelId, { tags });
            }
          } else if (result.error) {
            failed++;
          }
        });
        if (failed > 0 && success === 0) {
          setErrorMessage(fill(t.prompt.allFailed, { n: failed }));
        } else if (failed > 0) {
          setErrorMessage(fill(t.prompt.partlyFailed, { success, failed }));
        }
      } else {
        setErrorMessage(t.prompt.emptyResult);
      }
    } catch (error) {
      console.error('Batch enhancement failed:', error);
      setErrorMessage(fill(t.prompt.networkError, { error: toErrorMessage(error) }));
    } finally {
      stopTimer();
      setIsGenerating(false);
    }
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(outputText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  useEffect(() => {
    return () => {
      stopTimer();
    };
     
  }, []);

  return (
    <div className="prompt-lab-tab">
      <div className="prompt-controls">
        <div className="flex items-center gap-md">
          <div className="mode-toggle" data-tour="prompt-mode">
            <button
              className={`mode-btn ${promptMode === 'turbo' ? 'active' : ''}`}
              onClick={() => setPromptMode('turbo')}
              data-tip={tip.natural}
            >
              <FiZap size={16} /> {t.prompt.turbo}
            </button>
            <button
              className={`mode-btn ${promptMode === 'tags' ? 'active' : ''}`}
              onClick={() => setPromptMode('tags')}
              data-tip={tip.tags}
            >
              <FiTag size={16} /> {t.prompt.sdxl}
            </button>
          </div>
          <button
            className="btn btn-primary"
            onClick={handleBatchRefresh}
            data-tour="prompt-generate-all"
            data-tip={tip.generateAll}
            disabled={isGenerating || panels.length === 0}
          >
            <FiRefreshCw size={16} /> {t.prompt.generateAll}
            {isGenerating && (
              <span style={{ marginLeft: 8, fontSize: 12, opacity: 0.8 }}>
                {fill(t.prompt.generatingFor, { s: generatingSeconds })}
              </span>
            )}
          </button>
        </div>

        <div className="panel-selector flex items-center gap-md" data-tour="prompt-panel">
          <select
            className="input select"
            value={selectedPanelId}
            onChange={(e) => setSelectedPanelId(e.target.value)}
            data-tip={tip.panel}
          >
            <option value="">{t.prompt.selectPanel}</option>
            {panels.map((panel, idx) => (
              <option key={panel.id} value={panel.id}>
                Panel {idx + 1}: {panel.scene.substring(0, 30)}...
              </option>
            ))}
          </select>
          <button
            className="btn btn-secondary"
            onClick={() => { setImportModalOpen(true); setImportJson(importExample); setImportError(''); }}
            data-tip={tip.import}
            style={{ whiteSpace: 'nowrap' }}
          >
            <FiUpload size={14} /> {t.prompt.importPrompt || 'Import'}
          </button>
        </div>
      </div>

      <div className="prompt-workspace" data-tour="prompt-workspace">
        {errorMessage && (
          <div
            role="alert"
            data-testid="prompt-error"
            style={{
              gridColumn: '1 / -1',
              padding: '12px 16px',
              borderRadius: 8,
              background: 'rgba(244, 67, 54, 0.1)',
              border: '1px solid rgba(244, 67, 54, 0.4)',
              color: 'var(--accent-danger, #f44336)',
              fontSize: 13,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'flex-start',
              gap: 12,
            }}
          >
            <span style={{ flex: 1, wordBreak: 'break-word' }}>{errorMessage}</span>
            <button
              className="btn btn-ghost"
              onClick={() => setErrorMessage('')}
              style={{ fontSize: 12, padding: '2px 8px' }}
            >
              {t.prompt.close}
            </button>
          </div>
        )}
        <div className="prompt-input-section">
          <h3>{t.prompt.input}</h3>
          <textarea
            className="input textarea"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            data-tip={tip.input}
            placeholder={promptMode === 'turbo'
              ? 'Enter scene description for enhancement...'
              : 'Enter tags separated by commas...'}
            rows={10}
          />
          <button
            className="btn btn-primary mt-md"
            onClick={handleGenerate}
            disabled={isGenerating || !inputText.trim() || !selectedPanelId}
            data-tip={tip.generate}
          >
            {isGenerating ? <span className="loading-spinner" /> : t.prompt.generate}
            {isGenerating && (
              <span style={{ marginLeft: 8, fontSize: 12, opacity: 0.8 }}>
                {fill(t.prompt.generatingFor, { s: generatingSeconds })}
              </span>
            )}
          </button>
        </div>

        <div className="prompt-output-column">
          <div className="prompt-output-section">
            <h3>{t.prompt.output}</h3>
            <textarea
              className="input textarea output-textarea"
              value={outputText}
              onChange={(e) => setOutputText(e.target.value)}
              data-tip={tip.output}
              placeholder="Enhanced prompt will appear here..."
              rows={8}
            />
          </div>

          <div className="prompt-negative-section">
            <h3>{t.prompt.negativePrompt || 'Negative Prompt'}</h3>
            <textarea
              className="input textarea"
              value={negativePrompt}
              onChange={(e) => setNegativePrompt(e.target.value)}
              data-tip={tip.negative}
              placeholder={t.prompt.negativePromptPlaceholder || 'low quality, blurry, distorted...'}
              rows={4}
            />
          </div>

          <div className="prompt-seed-section">
            <h3>{t.prompt.seed || 'Seed'}</h3>
            <div className="seed-input-row">
              <input
                type="number"
                className="input"
                value={seed}
                onChange={(e) => setSeed(e.target.value)}
                data-tip={tip.seed}
                placeholder={t.prompt.seedPlaceholder || 'Random'}
              />
              <button
                className="btn btn-secondary"
                onClick={() => setSeed(String(Math.floor(Math.random() * 2147483647)))}
                data-tip={tip.randomSeed}
                aria-label={tip.randomSeed}
              >
                <FiShuffle size={16} />
              </button>
            </div>
            <div className="prompt-rembg-toggle">
              <label className="prompt-rembg-label">
                <input
                  type="checkbox"
                  checked={removeBG}
                  onChange={(e) => setRemoveBG(e.target.checked)}
                  data-tip={tip.removeBG}
                />
                <span>{t.prompt.removeBG || 'Remove Background'}</span>
              </label>
              <span className="text-xs text-muted">{t.prompt.removeBGHint || 'Generate image without background (transparent PNG)'}</span>
            </div>
            <div className="flex gap-sm mt-md">
              <button
                className="btn btn-secondary"
                onClick={handleCopy}
                disabled={!outputText}
                data-tip={tip.copy}
              >
                {copied ? <FiCheck size={16} /> : <FiCopy size={16} />}
                {copied ? t.prompt.copied : t.prompt.copy}
              </button>
              <button
                className="btn btn-primary"
                onClick={() => {
                  const parsedSeed = seed ? parseInt(seed, 10) : undefined;
                  if (promptMode === 'turbo') {
                    updatePanelPrompt(selectedPanelId, { turbo: outputText, negativePrompt, seed: parsedSeed, removeBG });
                  } else {
                    const tags = outputText.split(',').map((t: string) => t.trim());
                    updatePanelPrompt(selectedPanelId, { tags, negativePrompt, seed: parsedSeed, removeBG });
                  }
                }}
                disabled={!outputText}
                data-tip={tip.save}
              >
                Save
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="prompts-overview mt-lg" data-tour="prompt-overview">
        <h3>{t.prompt.allPrompts}</h3>
        <div className="prompts-grid">
          {panels.map((panel, idx) => (
            <div key={panel.id} className="prompt-card card">
              <div className="flex items-center justify-between mb-sm">
                <span className="badge">Panel {idx + 1}</span>
                <button
                  className="btn btn-ghost text-sm"
                  onClick={() => setSelectedPanelId(panel.id)}
                  data-tip={tip.edit}
                >
                  {t.prompt.edit}
                </button>
              </div>
                <p className="text-sm text-secondary">
                  {promptMode === 'turbo'
                  ? (panel.prompt.turbo || t.prompt.noPromptYet).substring(0, 100) + '...'
                  : (tagsText(panel.prompt.tags) || t.prompt.noTagsYet).substring(0, 100) + '...'
                }
              </p>
            </div>
          ))}
        </div>
      </div>

      <style>{`
        .prompt-controls {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: var(--space-lg);
          flex-wrap: wrap;
          gap: var(--space-md);
        }
        .mode-toggle {
          display: flex;
          background: var(--bg-tertiary);
          border-radius: var(--radius-md);
          padding: 4px;
        }
        .mode-btn {
          display: flex;
          align-items: center;
          gap: var(--space-xs);
          padding: var(--space-sm) var(--space-md);
          border: none;
          background: transparent;
          border-radius: var(--radius-sm);
          cursor: pointer;
          font-size: 14px;
          color: var(--text-secondary);
          transition: all var(--transition-default);
        }
        .mode-btn.active {
          background: var(--bg-primary);
          color: var(--text-primary);
          box-shadow: var(--shadow-subtle);
        }
        .panel-selector {
          display: flex;
          gap: var(--space-md);
        }
        .panel-selector .select {
          min-width: 300px;
        }
        .prompt-workspace {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: var(--space-lg);
          min-height: 400px;
        }
        .prompt-input-section,
        .prompt-output-section,
        .prompt-negative-section,
        .prompt-seed-section {
          display: flex;
          flex-direction: column;
        }
        .prompt-output-column {
          display: flex;
          flex-direction: column;
          gap: var(--space-md);
        }
        .prompt-input-section textarea {
          flex: 1;
          min-height: 250px;
          resize: vertical;
        }
        .prompt-output-section textarea {
          flex: 1;
          min-height: 200px;
          resize: vertical;
        }
        .prompt-negative-section textarea {
          resize: vertical;
        }
        .prompt-seed-section textarea {
          resize: vertical;
        }
        .seed-input-row {
          display: flex;
          gap: var(--space-sm);
          align-items: center;
        }
        .seed-input-row .input {
          flex: 1;
        }
        .prompt-rembg-toggle {
          margin-top: var(--space-sm);
          padding: var(--space-sm) 0;
        }
        .prompt-rembg-label {
          display: flex;
          align-items: center;
          gap: var(--space-sm);
          font-size: 14px;
          font-weight: 500;
          cursor: pointer;
        }
        .prompt-rembg-label input[type="checkbox"] {
          width: 16px;
          height: 16px;
          cursor: pointer;
        }
        .prompt-input-section h3,
        .prompt-output-section h3,
        .prompt-negative-section h3 {
          font-size: 14px;
          font-weight: 600;
          margin-bottom: var(--space-sm);
        }
        .output-textarea {
          font-family: 'JetBrains Mono', monospace;
          font-size: 13px;
        }
        .prompts-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
          gap: var(--space-md);
        }
        .prompt-card {
          padding: var(--space-md);
        }
      `}</style>

      {importModalOpen && (
        <div className="modal-overlay" style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.6)', zIndex: 1000,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }} onClick={() => setImportModalOpen(false)}>
          <div className="modal-content card" style={{
            width: '560px', maxHeight: '80vh', padding: '24px',
            background: 'var(--bg-primary)', borderRadius: '12px',
            display: 'flex', flexDirection: 'column', gap: '16px',
          }} onClick={e => e.stopPropagation()}>
            <h3 style={{ margin: 0, fontSize: '16px' }}>{t.prompt.importTitle || 'Paste Import Prompts'}</h3>
            <textarea
              className="input textarea"
              value={importJson}
              onChange={(e) => { setImportJson(e.target.value); setImportError(''); }}
              data-tip={tip.importJson}
              rows={12}
              style={{ fontFamily: 'monospace', fontSize: '12px', resize: 'vertical' }}
            />
            {importError && (
              <div style={{ color: 'var(--accent-danger, #ef4444)', fontSize: '12px' }}>
                {importError}
              </div>
            )}
            <div style={{ fontSize: '11px', color: 'var(--text-secondary)', lineHeight: 1.6, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <span>{t.prompt.importHint || 'JSON array. Fields: panel, positive (required), negative, seed'}</span>
              <button
                className="btn btn-ghost"
                onClick={handleCopyExample}
                data-tip={tip.copyExample}
                style={{ fontSize: '11px', padding: '2px 8px', whiteSpace: 'nowrap', marginLeft: '12px' }}
              >
                {importCopied ? <><FiCheck size={12} /> Copied</> : <><FiCopy size={12} /> Copy Example</>}
              </button>
            </div>
            <div className="flex gap-sm" style={{ justifyContent: 'flex-end' }}>
              <button className="btn btn-secondary" onClick={() => { setImportModalOpen(false); setImportJson(''); setImportError(''); }}>
                Cancel
              </button>
              <button className="btn btn-primary" onClick={handleImport} disabled={!importJson.trim()} data-tip={tip.importConfirm}>
                {t.prompt.importButton || 'Import Panels'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
