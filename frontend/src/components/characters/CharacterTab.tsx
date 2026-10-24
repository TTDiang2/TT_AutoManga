import { useState, useEffect } from 'react';
import { FiUser, FiPlus, FiEdit2, FiTrash2, FiImage, FiCopy, FiUpload } from 'react-icons/fi';
import { useProjectStore } from '../../store/projectStore';
import { useTranslation } from '../../hooks/useTranslation';

// shape returned by GET /api/character-templates
interface CharacterTemplateMeta {
  id: string;
  name: string;
  description: string;
  appearance?: string | null;
  image?: string | null;
  isBuiltIn?: boolean;
}

export function CharacterTab() {
  const { characters, setCharacters, addCharacter, updateCharacter, removeCharacter, extractCharactersFromPanels } = useProjectStore();
  const { t } = useTranslation();
  const [selectedCharId, setSelectedCharId] = useState<string | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editForm, setEditForm] = useState({ name: '', description: '', appearance: '' });
  const [generatingFor, setGeneratingFor] = useState<string | null>(null);
  const [showTemplates, setShowTemplates] = useState(false);
  const [templates, setTemplates] = useState<CharacterTemplateMeta[]>([]);
  const [backendLoaded, setBackendLoaded] = useState(false);

  const syncCharactersToBackend = async (chars: typeof characters) => {
    try {
      await fetch('/api/characters/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(chars),
      });
    } catch {
      // best-effort sync; the backend library is optional
    }
  };

  useEffect(() => {
    fetch('/api/characters/')
      .then(r => r.json())
      .then(data => {
        if (Array.isArray(data) && data.length > 0) {
          setCharacters(data);
        } else if (characters.length === 0) {
          const extracted = extractCharactersFromPanels();
          if (extracted.length > 0) setCharacters(extracted);
        }
        setBackendLoaded(true);
      })
      .catch(() => {
        if (characters.length === 0) {
          const extracted = extractCharactersFromPanels();
          if (extracted.length > 0) setCharacters(extracted);
        }
        setBackendLoaded(true);
      });
  }, []);

  useEffect(() => {
    if (backendLoaded && characters.length >= 0) {
      syncCharactersToBackend(characters);
    }
  }, [characters, backendLoaded]);

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
    addCharacter(newChar);
    setSelectedCharId(newChar.id);
    setEditForm({ name: newChar.name, description: '', appearance: '' });
    setIsEditing(true);
  };

  const handleSave = () => {
    if (selectedCharId) {
      updateCharacter(selectedCharId, {
        ...editForm,
        updatedAt: new Date().toISOString(),
      });
    }
    setIsEditing(false);
  };

  const handleDelete = (id: string) => {
    if (!confirm('Delete this character?')) return;
    removeCharacter(id);
    if (selectedCharId === id) setSelectedCharId(null);
  };

  const handleGenerateImage = async (charId: string) => {
    const char = characters.find(c => c.id === charId);
    if (!char) return;

    setGeneratingFor(charId);

    try {
      const prompt = char.appearance || `${char.name}, ${char.description}`;
      
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
        updateCharacter(charId, { image: data.image, updatedAt: new Date().toISOString() });
      }
    } catch (err) {
      console.error('Failed to generate character image:', err);
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
    addCharacter(newChar);
    setSelectedCharId(newChar.id);
    setShowTemplates(false);
  };

  const handleUploadImage = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !selectedCharId) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const result = ev.target?.result as string;
      updateCharacter(selectedCharId, { image: result, updatedAt: new Date().toISOString() });
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
                  <button className="btn btn-secondary" onClick={() => { setEditForm({ name: selectedChar.name, description: selectedChar.description, appearance: selectedChar.appearance || '' }); setIsEditing(true); }}>
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
                      <h4 style={{ marginBottom: '6px', fontSize: '13px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{t.characters.description}</h4>
                      <p style={{ fontSize: '14px', lineHeight: '1.5', wordBreak: 'break-word' }}>{selectedChar.description}</p>
                    </div>
                  )}

                  {selectedChar.appearance && (
                    <div>
                      <h4 style={{ marginBottom: '6px', fontSize: '13px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{t.characters.appearance}</h4>
                      <p style={{ fontSize: '14px', lineHeight: '1.6', wordBreak: 'break-word', whiteSpace: 'pre-wrap' }}>{selectedChar.appearance}</p>
                    </div>
                  )}

                  {!selectedChar.description && !selectedChar.appearance && (
                    <p style={{ color: 'var(--text-muted)', fontSize: '13px', fontStyle: 'italic' }}>No description or appearance details yet.</p>
                  )}
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