import { useState } from 'react';
import { FiPlus, FiTrash2, FiMove, FiEdit2, FiCheck, FiX, FiFileText } from 'react-icons/fi';
import { 
  DndContext, 
  closestCenter, 
  KeyboardSensor, 
  PointerSensor, 
  useSensor, 
  useSensors,
} from '@dnd-kit/core';
import type { DragEndEvent } from '@dnd-kit/core';
import { 
  arrayMove, 
  SortableContext, 
  sortableKeyboardCoordinates, 
  useSortable,
  verticalListSortingStrategy 
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { useProjectStore } from '../../store/projectStore';
import { useTranslation } from '../../hooks/useTranslation';
import type { Panel } from '../../types';

function SortablePanel({ panel, index, onUpdate, onDelete }: { 
  panel: Panel; 
  index: number;
  onUpdate: (id: string, updates: Partial<Panel>) => void;
  onDelete: (id: string) => void;
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [editScene, setEditScene] = useState(panel.scene);
  const [editDialogue, setEditDialogue] = useState(panel.dialogue);
  
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging
  } = useSortable({ id: panel.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  const handleSave = () => {
    onUpdate(panel.id, { scene: editScene, dialogue: editDialogue });
    setIsEditing(false);
  };

  return (
    <div ref={setNodeRef} style={style} className="card panel-card">
      <div className="panel-header">
        <div className="panel-number">
          <span {...attributes} {...listeners} className="drag-handle">
            <FiMove size={14} />
          </span>
          <span className="badge">Panel {index + 1}</span>
        </div>
        <button className="btn btn-ghost" onClick={() => onDelete(panel.id)}>
          <FiTrash2 size={16} />
        </button>
      </div>
      
      {isEditing ? (
        <div className="panel-edit">
          <textarea
            className="input textarea"
            value={editScene}
            onChange={(e) => setEditScene(e.target.value)}
            placeholder="Scene description..."
            rows={3}
          />
          <textarea
            className="input textarea"
            value={editDialogue}
            onChange={(e) => setEditDialogue(e.target.value)}
            placeholder="Dialogue..."
            rows={2}
          />
          <div className="flex gap-sm mt-sm">
            <button className="btn btn-primary" onClick={handleSave}>
              <FiCheck size={14} /> Save
            </button>
            <button className="btn btn-secondary" onClick={() => setIsEditing(false)}>
              <FiX size={14} /> Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="panel-content">
          <div className="scene-text">
            <strong>Scene:</strong> {panel.scene || 'No description'}
          </div>
          {panel.dialogue && (
            <div className="dialogue-text">
              <strong>Dialogue:</strong> {panel.dialogue}
            </div>
          )}
          {panel.characters.length > 0 && (
            <div className="characters-list">
              {panel.characters.map((char, i) => (
                <span key={i} className="badge">{char}</span>
              ))}
            </div>
          )}
          <button className="btn btn-ghost mt-sm" onClick={() => setIsEditing(true)}>
            <FiEdit2 size={14} /> Edit
          </button>
        </div>
      )}
    </div>
  );
}

export function StoryboardTab() {
  const { panels, setPanels, updatePanel, removePanel, settings } = useProjectStore();
  const { t } = useTranslation();
  const [novelText, setNovelText] = useState('');
  const [detailLevel, setDetailLevel] = useState(settings.defaults.detailLevel);
  const [isGenerating, setIsGenerating] = useState(false);

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  const handleGenerate = async () => {
    if (!novelText.trim()) return;
    
    setIsGenerating(true);
    try {
      const response = await fetch('/api/storyboard/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: novelText,
          detail_level: detailLevel,
          endpoint: settings.api.endpoint,
          api_key: settings.api.api_key,
          model: settings.api.model,
          temperature: settings.api.temperature,
          thinking: settings.api.thinking,
        }),
      });
      
      const data = await response.json();
      console.log('API Response:', data);
      
      if (data.error) {
        alert('Error: ' + data.error);
      }
      
      if (data.panels && data.panels.length > 0) {
        const llmPanels = (data.panels ?? []) as Array<{ scene?: string; characters?: string[]; dialogue?: string }>;
        const newPanels = llmPanels.map((p, idx: number) => ({
          id: `panel_${Date.now()}_${idx}`,
          order: idx,
          scene: p.scene || '',
          characters: p.characters || [],
          dialogue: p.dialogue || '',
          prompt: {},
        }));
        setPanels(newPanels);
      } else {
        alert('No panels returned. Check console for details.');
      }
    } catch (error) {
      console.error('Generation failed:', error);
      alert('Request failed: ' + error);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (over && active.id !== over.id) {
      const oldIndex = panels.findIndex((p) => p.id === active.id);
      const newIndex = panels.findIndex((p) => p.id === over.id);
      setPanels(arrayMove(panels, oldIndex, newIndex).map((p, i) => ({ ...p, order: i })));
    }
  };

  const handleAddPanel = () => {
    const newPanel: Panel = {
      id: `panel_${Date.now()}`,
      order: panels.length,
      scene: '',
      characters: [],
      dialogue: '',
      prompt: {},
    };
    setPanels([...panels, newPanel]);
  };

  const handleUpdatePanel = (id: string, updates: Partial<Panel>) => {
    updatePanel(id, updates);
  };

  return (
    <div className="storyboard-tab">
      <div className="input-section">
        <textarea
          className="input textarea novel-input"
          value={novelText}
          onChange={(e) => setNovelText(e.target.value)}
          placeholder={t.storyboard.inputPlaceholder}
          rows={8}
        />
        <div className="flex items-center justify-between mt-md">
          <div className="precision-control">
            <div className="flex items-center gap-md">
              <span className="text-sm text-secondary">{t.storyboard.detailLevel}:</span>
              <input
                type="range"
                className="slider"
                min={1}
                max={5}
                value={detailLevel}
                onChange={(e) => setDetailLevel(Number(e.target.value))}
              />
              <div className="precision-labels">
                <span>{t.storyboard.abstract}</span>
                <span>{t.storyboard.detailed}</span>
              </div>
            </div>
            <div className="panel-count-hint text-sm text-muted">
              {detailLevel === 1 ? '~1-2' : detailLevel === 2 ? '~3-4' : detailLevel === 3 ? '~5-6' : detailLevel === 4 ? '~7-8' : '~10+'} panels
            </div>
          </div>
          <button 
            className="btn btn-primary" 
            onClick={handleGenerate}
            disabled={isGenerating || !novelText.trim()}
          >
            {isGenerating ? <span className="loading-spinner" /> : t.storyboard.generate}
          </button>
        </div>
      </div>

      <div className="panels-section mt-lg">
        <div className="flex items-center justify-between mb-md">
          <h3>Storyboard Panels ({panels.length})</h3>
          <button className="btn btn-secondary" onClick={handleAddPanel}>
            <FiPlus size={16} /> {t.storyboard.addPanel}
          </button>
        </div>

        {panels.length === 0 ? (
          <div className="empty-state">
            <FiFileText size={48} />
            <h3>{t.storyboard.noPanels}</h3>
            <p>{t.storyboard.noPanelsDesc}</p>
          </div>
        ) : (
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={handleDragEnd}
          >
            <SortableContext items={panels.map(p => p.id)} strategy={verticalListSortingStrategy}>
              <div className="panels-grid">
                {panels.map((panel, index) => (
                  <SortablePanel
                    key={panel.id}
                    panel={panel}
                    index={index}
                    onUpdate={handleUpdatePanel}
                    onDelete={removePanel}
                  />
                ))}
              </div>
            </SortableContext>
          </DndContext>
        )}
      </div>

      <style>{`
        .novel-input {
          width: 100%;
          min-height: 200px;
        }
        .precision-control {
          display: flex;
          align-items: center;
          gap: var(--space-md);
        }
        .precision-control .slider {
          width: 200px;
        }
        .precision-labels {
          display: flex;
          justify-content: space-between;
          width: 200px;
          font-size: 11px;
          color: var(--text-muted);
        }
        .panel-card {
          margin-bottom: var(--space-md);
        }
        .panel-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: var(--space-md);
        }
        .panel-number {
          display: flex;
          align-items: center;
          gap: var(--space-sm);
        }
        .drag-handle {
          cursor: grab;
          color: var(--text-muted);
          padding: var(--space-xs);
        }
        .drag-handle:active {
          cursor: grabbing;
        }
        .scene-text {
          margin-bottom: var(--space-sm);
          color: var(--text-primary);
        }
        .dialogue-text {
          font-style: italic;
          color: var(--text-secondary);
          margin-bottom: var(--space-sm);
        }
        .characters-list {
          display: flex;
          flex-wrap: wrap;
          gap: var(--space-xs);
          margin-bottom: var(--space-sm);
        }
        .panel-edit textarea {
          margin-bottom: var(--space-sm);
          width: 100%;
        }
        .panels-grid {
          display: flex;
          flex-direction: column;
          gap: var(--space-md);
        }
      `}</style>
    </div>
  );
}
