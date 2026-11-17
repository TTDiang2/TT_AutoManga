import { useState, useEffect } from 'react';
import { FiUser, FiPlus, FiEdit2, FiTrash2, FiImage, FiCopy, FiUpload } from 'react-icons/fi';
import { useProjectStore } from '../../store/projectStore';
import { useTranslation, fill } from '../../hooks/useTranslation';
import type { Character, CharacterLora } from '../../types';
import { TrainingPanel } from './TrainingPanel';

// shape returned by GET /api/character-templates
interface CharacterTemplateMeta {
  id: string;
  name: string;
  description: string;
  appearance?: string | null;
  image?: string | null;
  isBuiltIn?: boolean;
}

// shape returned by GET /api/assets/swarmui/loras
interface SwarmLora {
  name: string;
  trigger: string;
  architecture?: string;
}

const DEFAULT_LORA_WEIGHT = 0.8;

export function CharacterTab() {
  const { characters, setCharacters, addCharacter, updateCharacter, removeCharacter, extractCharactersFromPanels } = useProjectStore();
  const { t } = useTranslation();
  const [selectedCharId, setSelectedCharId] = useState<string | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editForm, setEditForm] = useState({ name: '', description: '', appearance: '' });
  // the LoRA form: name '' = none; trigger '' falls back to the LoRA's own
  const [loraForm, setLoraForm] = useState({ name: '', weight: DEFAULT_LORA_WEIGHT, trigger: '' });
  const [swarmLoras, setSwarmLoras] = useState<SwarmLora[]>([]);
  // the sheet as an IP-Adapter reference on solo panels: 0 = off;
  // ipadapter null = not probed yet (GET /api/assets/swarmui/features)
  const [refWeight, setRefWeight] = useState(0);
  const [ipadapter, setIpadapter] = useState<boolean | null>(null);
  const [generatingFor, setGeneratingFor] = useState<string | null>(null);
  const [showTemplates, setShowTemplates] = useState(false);
  const [templates, setTemplates] = useState<CharacterTemplateMeta[]>([]);
  // the server's library is empty: characters this browser has (or the storyboard names),
  // added only when the user asks (opening the tab writes nothing)
  const [seedCandidates, setSeedCandidates] = useState<Character[]>([]);

  // The library is shared (the Comics converter adds characters too), so
  // changes go through the per-item endpoints; posting the full list would
  // wipe whatever was added since this tab loaded it.
  const reportSyncError = (what: string) => (err: unknown) => {
    console.warn(`[characters] ${what} failed:`, err);
  };
  const checked = (res: Response) => {
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res;
  };

  const addChar = (char: Character) => {
    addCharacter(char);
    fetch('/api/characters/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(char),
    }).then(checked).catch(reportSyncError('add'));
  };

  const patchChar = (id: string, updates: Partial<Character>) => {
    updateCharacter(id, updates);
    fetch(`/api/characters/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    }).then(checked).catch(reportSyncError('update'));
  };

  const deleteChar = (id: string) => {
    removeCharacter(id);
    fetch(`/api/characters/${encodeURIComponent(id)}`, { method: 'DELETE' })
      .then(checked).catch(reportSyncError('delete'));
  };

  useEffect(() => {
    fetch('/api/characters/')
      .then(checked)
      .then(r => r.json())
      .then(data => {
        if (!Array.isArray(data)) return;
        if (data.length === 0) {
          // the library is empty: offer what's known locally ("Add characters from storyboard")
          const { characters: local } = useProjectStore.getState();
          setSeedCandidates(local.length > 0 ? local : extractCharactersFromPanels());
        }
        setCharacters(data);
      })
      .catch(() => {
        // offline: show what can be derived locally, but don't write anything
        if (useProjectStore.getState().characters.length === 0) {
          const extracted = extractCharactersFromPanels();
          if (extracted.length > 0) setCharacters(extracted);
        }
      });
  }, []);

  useEffect(() => {
    if (!isEditing) return;
    fetch('/api/assets/swarmui/loras')
      .then(checked)
      .then(r => r.json())
      .then(data => setSwarmLoras(Array.isArray(data?.loras) ? data.loras : []))
      .catch(() => setSwarmLoras([]));
    fetch('/api/assets/swarmui/features')
      .then(checked)
      .then(r => r.json())
      .then(data => setIpadapter(!!data?.ipadapter))
      .catch(() => setIpadapter(false));
  }, [isEditing]);

  // the explicit seed of an empty library (POST replaces the list: only done while it is empty)
  const addFromStoryboard = () => {
    const seed = seedCandidates;
    if (seed.length === 0) return;
    setSeedCandidates([]);
    setCharacters(seed);
    fetch('/api/characters/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(seed),
    }).then(checked).catch(reportSyncError('seed'));
  };

  const startEdit = (char: Character) => {
    setEditForm({ name: char.name, description: char.description, appearance: char.appearance || '' });
    setLoraForm({ name: char.lora?.name || '', weight: char.lora?.weight ?? DEFAULT_LORA_WEIGHT, trigger: char.lora?.trigger || '' });
    setRefWeight(char.refWeight || 0);
    setIsEditing(true);
  };

  const pickLora = (name: string) => {
    const found = swarmLoras.find(l => l.name === name);
    // a new pick brings its own trigger word; an edited one is kept
    const ownTrigger = swarmLoras.find(l => l.name === loraForm.name)?.trigger || '';
    const keepTrigger = loraForm.trigger && loraForm.trigger !== ownTrigger;
    setLoraForm({ ...loraForm, name, trigger: keepTrigger ? loraForm.trigger : (found?.trigger || '') });
  };

  useEffect(() => {
    if (showTemplates) {
      fetch('/api/characters/templates/')
        .then(r => r.json())
        .then(data => setTemplates(Array.isArray(data) ? data : []))
        .catch(() => setTemplates([]));
    }
  }, [showTemplates]);

  const selectedChar = characters.find(c => c.id === selectedCharId);

  const handleCreateNew = () => {
    const newChar = {
      id: `char_${Date.now()}`,
      name: 'New Character',
      description: '',
      sourcePanelIds: [],
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
    addChar(newChar);
    setSelectedCharId(newChar.id);
    startEdit(newChar);
  };

  const handleSave = () => {
    if (selectedCharId) {
      const lora: CharacterLora | null = loraForm.name
        ? { name: loraForm.name, weight: loraForm.weight, trigger: loraForm.trigger.trim() || null }
        : null;
      patchChar(selectedCharId, {
        ...editForm,
        lora,
        refWeight: refWeight > 0 ? refWeight : null,
        updatedAt: new Date().toISOString(),
      });
    }
    setIsEditing(false);
  };

  const handleDelete = (id: string) => {
    if (!confirm('Delete this character?')) return;
    deleteChar(id);
    if (selectedCharId === id) setSelectedCharId(null);
  };

  const handleGenerateImage = async (charId: string) => {
    const char = characters.find(c => c.id === charId);
    if (!char) return;
    // the appearance is the image prompt; a name alone paints a random person
    if (!char.appearance?.trim()) {
      alert(`${char.name} has no appearance yet. Click Edit and describe how they look (it is the image prompt).`);
      return;
    }

    setGeneratingFor(charId);

    try {
      const prompt = char.appearance;
      
      const response = await fetch('/api/characters/templates/generate-image', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt,
          negative_prompt: 'low quality, blurry, distorted, watermark, text',
          character_id: charId,
          project_id: 'default',
        }),
      });

      const data = await response.json();
      
      if (data.success && data.image) {
        patchChar(charId, { image: data.image, updatedAt: new Date().toISOString() });
      } else {
        // e.g. SwarmUI's "No model input given" when Settings has no model
        alert(`Image generation failed: ${data.error || data.detail || `HTTP ${response.status}`}`);
      }
    } catch (err) {
      console.error('Failed to generate character image:', err);
      alert(`Image generation failed: ${(err as Error).message}`);
    } finally {
      setGeneratingFor(null);
    }
  };

  const handleUseTemplate = (template: CharacterTemplateMeta) => {
    const newChar = {
      id: `char_${Date.now()}`,
      name: template.name,
      description: template.description,
      appearance: template.appearance ?? undefined,
      image: template.image ?? undefined,
      sourcePanelIds: [],
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
    addChar(newChar);
    setSelectedCharId(newChar.id);
    setShowTemplates(false);
  };

  const handleUploadImage = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !selectedCharId) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const result = ev.target?.result as string;
      patchChar(selectedCharId, { image: result, updatedAt: new Date().toISOString() });
    };
    reader.readAsDataURL(file);
  };

  const handleSaveAsTemplate = async () => {
    const template = {
      id: `template_${Date.now()}`,
      name: editForm.name,
      description: editForm.description,
      appearance: editForm.appearance,
      isBuiltIn: false,
      createdAt: new Date().toISOString(),
    };
    await fetch('/api/characters/templates/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(template),
    });
    alert('Saved as template!');
  };

  return (
    <div className="character-tab" style={{ display: 'flex', height: '100%', gap: '16px' }}>
      <div className="character-list" style={{ width: '300px', flexShrink: 0 }}>
        <div className="flex justify-between items-center mb-md">
          <h3>{t.characters.title} ({characters.length})</h3>
          <button className="btn btn-primary" onClick={handleCreateNew}>
            <FiPlus size={16} /> {t.characters.newChar}
          </button>
        </div>
        
        <button 
          className="btn btn-ghost mt-sm" 
          style={{ width: '100%', justifyContent: 'flex-start' }}
          onClick={() => setShowTemplates(!showTemplates)}
        >
          <FiCopy size={16} /> {showTemplates ? t.characters.hideTemplates : t.characters.showTemplates}
        </button>

        {showTemplates && templates.length > 0 && (
          <div className="template-list" style={{ marginTop: '12px', marginBottom: '12px' }}>
            <h4 style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px' }}>{t.characters.templates}</h4>
            {templates.map(tpl => (
              <div
                key={tpl.id}
                className="template-item"
                style={{ padding: '8px', borderRadius: '6px', background: 'var(--bg-tertiary)', marginBottom: '6px', cursor: 'pointer' }}
                onClick={() => handleUseTemplate(tpl)}
              >
                <div style={{ fontWeight: 500, fontSize: '13px' }}>{tpl.name}</div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{tpl.description}</div>
                {tpl.isBuiltIn && <span style={{ fontSize: '10px', background: 'var(--bg-primary)', padding: '2px 6px', borderRadius: '10px', marginTop: '4px', display: 'inline-block' }}>{t.characters.builtIn}</span>}
              </div>
            ))}
          </div>
        )}

        <div className="character-cards">
          {characters.map(char => (
            <div
              key={char.id}
              className={`character-card card ${selectedCharId === char.id ? 'selected' : ''}`}
              onClick={() => { setSelectedCharId(char.id); setIsEditing(false); }}
              style={{ cursor: 'pointer', padding: '12px', marginBottom: '8px', borderRadius: '8px', border: selectedCharId === char.id ? '2px solid var(--accent-primary)' : '1px solid var(--border-default)' }}
            >
              <div className="flex items-center gap-sm">
                {char.image ? (
                  <img src={char.image} alt={char.name} style={{ width: '40px', height: '40px', borderRadius: '50%', objectFit: 'cover' }} />
                ) : (
                  <div style={{ width: '40px', height: '40px', borderRadius: '50%', background: 'var(--bg-tertiary)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <FiUser size={20} />
                  </div>
                )}
                <div>
                  <div style={{ fontWeight: 500 }}>{char.name}</div>
                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                    {char.sourcePanelIds.length} {t.characters.panels}
                  </div>
                </div>
              </div>
            </div>
          ))}
          
          {characters.length === 0 && !showTemplates && (
            <div className="empty-state" style={{ textAlign: 'center', padding: '40px' }}>
              <FiUser size={48} style={{ opacity: 0.3 }} />
              <p style={{ marginTop: '12px', color: 'var(--text-secondary)' }}>{t.characters.noCharacters}</p>
              <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{t.characters.noCharactersDesc}</p>
              {seedCandidates.length > 0 && (
                <button className="btn btn-secondary" style={{ marginTop: '12px' }} onClick={addFromStoryboard}>
                  <FiPlus size={14} /> {fill(t.characters.addFromStoryboard, { n: seedCandidates.length })}
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="character-detail" style={{ flex: 1, display: 'flex', justifyContent: 'center' }}>
        {selectedChar ? (
          isEditing ? (
            <div className="card" style={{ padding: '20px', width: '100%', maxWidth: '600px' }}>
              <h3 style={{ marginBottom: '16px' }}>{t.characters.edit}</h3>
              <div style={{ marginBottom: '12px' }}>
                <label style={{ display: 'block', marginBottom: '4px', fontSize: '13px' }}>{t.characters.name}</label>
                <input
                  className="input"
                  style={{ width: '100%' }}
                  value={editForm.name}
                  onChange={e => setEditForm({ ...editForm, name: e.target.value })}
                />
              </div>
              <div style={{ marginBottom: '12px' }}>
                <label style={{ display: 'block', marginBottom: '4px', fontSize: '13px' }}>{t.characters.description}</label>
                <textarea
                  className="input"
                  style={{ width: '100%' }}
                  rows={3}
                  value={editForm.description}
                  onChange={e => setEditForm({ ...editForm, description: e.target.value })}
                />
              </div>
              <div style={{ marginBottom: '12px' }}>
                <label style={{ display: 'block', marginBottom: '4px', fontSize: '13px' }}>{t.characters.appearance}</label>
                <textarea
                  className="input"
                  style={{ width: '100%' }}
                  rows={2}
                  value={editForm.appearance}
                  onChange={e => setEditForm({ ...editForm, appearance: e.target.value })}
                  placeholder={t.characters.appearancePlaceholder}
                />
              </div>
              <div style={{ marginBottom: '12px' }}>
                <label style={{ display: 'block', marginBottom: '4px', fontSize: '13px' }} htmlFor="char-lora">{t.characters.lora}</label>
                <select
                  id="char-lora"
                  className="input"
                  style={{ width: '100%' }}
                  value={loraForm.name}
                  onChange={e => pickLora(e.target.value)}
                >
                  <option value="">{t.characters.loraNone}</option>
                  {loraForm.name && !swarmLoras.some(l => l.name === loraForm.name) && (
                    <option value={loraForm.name}>{loraForm.name}</option>
                  )}
                  {swarmLoras.map(l => (
                    <option key={l.name} value={l.name}>{l.name}</option>
                  ))}
                </select>
                {loraForm.name && (
                  <div className="flex gap-sm items-center" style={{ marginTop: '8px' }}>
                    <label style={{ fontSize: '12px', whiteSpace: 'nowrap' }} htmlFor="char-lora-weight">{t.characters.loraWeight}</label>
                    <input
                      id="char-lora-weight"
                      type="range"
                      min={0}
                      max={1.2}
                      step={0.05}
                      value={loraForm.weight}
                      onChange={e => setLoraForm({ ...loraForm, weight: Number(e.target.value) })}
                      style={{ flex: 1 }}
                    />
                    <span style={{ fontSize: '12px', width: '32px', textAlign: 'right' }}>{loraForm.weight.toFixed(2)}</span>
                    <input
                      className="input"
                      style={{ width: '140px' }}
                      value={loraForm.trigger}
                      onChange={e => setLoraForm({ ...loraForm, trigger: e.target.value })}
                      placeholder={t.characters.loraTrigger}
                      aria-label={t.characters.loraTrigger}
                    />
                  </div>
                )}
                <p style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>{t.characters.loraHint}</p>
              </div>
              <div style={{ marginBottom: '12px' }}>
                <label style={{ display: 'block', marginBottom: '4px', fontSize: '13px' }} htmlFor="char-ref-weight">{t.characters.refWeight}</label>
                <div className="flex gap-sm items-center">
                  <input
                    id="char-ref-weight"
                    type="range"
                    min={0}
                    max={1}
                    step={0.05}
                    value={refWeight}
                    onChange={e => setRefWeight(Number(e.target.value))}
                    disabled={!ipadapter || !selectedChar?.image}
                    style={{ flex: 1 }}
                  />
                  <span style={{ fontSize: '12px', width: '32px', textAlign: 'right' }}>
                    {refWeight > 0 ? refWeight.toFixed(2) : t.characters.refOff}
                  </span>
                </div>
                <p style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
                  {ipadapter === false ? t.characters.refUnavailable
                    : !selectedChar?.image ? t.characters.refNoSheet
                    : t.characters.refHint}
                </p>
              </div>
              <div className="flex gap-sm">
                <button className="btn btn-primary" onClick={handleSave}>{t.characters.save}</button>
                <button className="btn btn-secondary" onClick={handleSaveAsTemplate}>
                  <FiCopy size={16} /> {t.characters.saveAsTemplate}
                </button>
                <button className="btn btn-ghost" onClick={() => setIsEditing(false)}>{t.characters.cancel}</button>
              </div>
            </div>
          ) : (
            <div className="card" style={{ padding: '20px', width: '100%', maxWidth: '680px' }}>
              <div className="flex justify-between items-start">
                <div>
                  <h2>{selectedChar.name}</h2>
                  <p style={{ color: 'var(--text-secondary)', marginTop: '4px', fontSize: '13px' }}>
                    {selectedChar.sourcePanelIds.length} {t.characters.panels}
                  </p>
                </div>
                <div className="flex gap-sm">
                  <button className="btn btn-secondary" onClick={() => startEdit(selectedChar)}>
                    <FiEdit2 size={16} /> {t.characters.edit}
                  </button>
                  <button className="btn btn-ghost" onClick={() => handleDelete(selectedChar.id)} style={{ color: 'var(--error)' }}>
                    <FiTrash2 size={16} />
                  </button>
                </div>
              </div>

              <div style={{ marginTop: '20px', display: 'flex', gap: '20px', alignItems: 'flex-start' }}>
                <div style={{ flexShrink: 0 }}>
                  {selectedChar.image ? (
                    <img
                      src={selectedChar.image}
                      alt={selectedChar.name}
                      style={{ width: '220px', height: '352px', objectFit: 'cover', borderRadius: '8px', display: 'block' }}
                    />
                  ) : (
                    <div style={{ width: '220px', height: '352px', background: 'var(--bg-tertiary)', borderRadius: '8px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
                      <FiUser size={40} style={{ opacity: 0.4 }} />
                      <button
                        className="btn btn-secondary"
                        onClick={() => handleGenerateImage(selectedChar.id)}
                        disabled={generatingFor === selectedChar.id}
                        style={{ fontSize: '12px', padding: '6px 12px' }}
                      >
                        {generatingFor === selectedChar.id ? <span className="loading-spinner" /> : <FiImage size={14} />}
                        {generatingFor === selectedChar.id ? t.characters.generating : t.characters.generateImage}
                      </button>
                      <label className="btn btn-secondary" style={{ fontSize: '12px', padding: '6px 12px', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '4px' }}>
                        <FiUpload size={14} />
                        {t.assets.upload}
                        <input type="file" accept="image/*" onChange={handleUploadImage} hidden />
                      </label>
                    </div>
                  )}
                  {selectedChar.image && (
                    <div style={{ display: 'flex', gap: '6px', marginTop: '10px' }}>
                      <button
                        className="btn btn-secondary"
                        onClick={() => handleGenerateImage(selectedChar.id)}
                        disabled={generatingFor === selectedChar.id}
                        style={{ flex: 1, fontSize: '12px', padding: '6px 12px' }}
                      >
                        {generatingFor === selectedChar.id ? <span className="loading-spinner" /> : <FiImage size={14} />}
                        {generatingFor === selectedChar.id ? t.characters.generating : t.characters.generateImage}
                      </button>
                      <label className="btn btn-secondary" style={{ flex: 1, fontSize: '12px', padding: '6px 12px', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '4px' }}>
                        <FiUpload size={14} />
                        {t.assets.upload}
                        <input type="file" accept="image/*" onChange={handleUploadImage} hidden />
                      </label>
                    </div>
                  )}
                </div>


                <div style={{ flex: 1, minWidth: 0 }}>
                  {selectedChar.description && (
                    <div style={{ marginBottom: '16px' }}>
                      <h4 style={{ marginBottom: '6px', fontSize: '13px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{t.characters.desc}</h4>
                      <p style={{ fontSize: '14px', lineHeight: '1.5', wordBreak: 'break-word' }}>{selectedChar.description}</p>
                    </div>
                  )}

                  {selectedChar.appearance && (
                    <div>
                      <h4 style={{ marginBottom: '6px', fontSize: '13px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{t.characters.appearance}</h4>
                      <p style={{ fontSize: '14px', lineHeight: '1.6', wordBreak: 'break-word', whiteSpace: 'pre-wrap' }}>{selectedChar.appearance}</p>
                    </div>
                  )}

                  {selectedChar.lora?.name && (
                    <div style={{ marginTop: '16px' }}>
                      <h4 style={{ marginBottom: '6px', fontSize: '13px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{t.characters.lora}</h4>
                      <p style={{ fontSize: '14px', wordBreak: 'break-word' }}>
                        {selectedChar.lora.name} · {selectedChar.lora.weight}{selectedChar.lora.trigger ? ` · ${selectedChar.lora.trigger}` : ''}
                      </p>
                    </div>
                  )}

                  {!!selectedChar.refWeight && selectedChar.image && (
                    <div style={{ marginTop: '16px' }}>
                      <h4 style={{ marginBottom: '6px', fontSize: '13px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{t.characters.refWeight}</h4>
                      <p style={{ fontSize: '14px' }}>{selectedChar.refWeight}</p>
                    </div>
                  )}

                  {!selectedChar.description && !selectedChar.appearance && (
                    <p style={{ color: 'var(--text-muted)', fontSize: '13px', fontStyle: 'italic' }}>No description or appearance details yet.</p>
                  )}
                  <TrainingPanel key={selectedChar.id} character={selectedChar} />
                </div>
              </div>
            </div>
          )
        ) : (
          <div className="empty-state" style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ textAlign: 'center' }}>
              <FiUser size={64} style={{ opacity: 0.2 }} />
              <p style={{ marginTop: '16px' }}>Select a character to view details</p>
            </div>
          </div>
        )}
      </div>

      <style>{`
        .character-card:hover { background: var(--bg-secondary); }
        .character-card.selected { background: var(--bg-secondary); }
      `}</style>
    </div>
  );
}