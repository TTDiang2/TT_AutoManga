import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Panel, Project, AppSettings, TabId, Character } from '../types';

interface ProjectStore {
  currentProject: Project | null;
  panels: Panel[];
  characters: Character[];
  activeTab: TabId;
  settings: AppSettings;
  isLoading: boolean;
  promptMode: 'turbo' | 'tags';
  composerProjectId: string | null;
  generatingPanels: string[];

  setCurrentProject: (project: Project | null) => void;
  setComposerProjectId: (id: string | null) => void;
  setPanels: (panels: Panel[]) => void;
  addPanel: (panel: Panel) => void;
  updatePanel: (id: string, updates: Partial<Panel>) => void;
  removePanel: (id: string) => void;
  reorderPanels: (panels: Panel[]) => void;
  setActiveTab: (tab: TabId) => void;
  setSettings: (settings: AppSettings) => void;
  setLoading: (loading: boolean) => void;
  updatePanelImage: (id: string, image: string) => void;
  updatePanelPrompt: (id: string, prompt: Partial<Panel['prompt']>) => void;
  setCharacters: (characters: Character[]) => void;
  addCharacter: (character: Character) => void;
  updateCharacter: (id: string, updates: Partial<Character>) => void;
  removeCharacter: (id: string) => void;
  extractCharactersFromPanels: () => Character[];
  setPromptMode: (mode: 'turbo' | 'tags') => void;
  startGenerating: (panelId: string) => void;
  stopGenerating: (panelId: string) => void;
  loadProjectWithImages: (projectId: string) => Promise<void>;
}

const defaultSettings: AppSettings = {
  api: {
    endpoint: 'https://api.openai.com/v1',
    api_key: '',
    model: 'gpt-4o-mini',
    temperature: 0.7,
    max_tokens: 4096,
    thinking: true,
    storyboard_system_prompt: '',
    prompt_system_prompt: '',
    storyboardPresets: [],
    promptPresets: [],
  },
  swarmui: {
    address: 'http://127.0.0.1:7801',
    activePresetId: '',
    presets: [],
    currentModel: '',
    currentLoras: [],
    currentSteps: 20,
    currentCfgScale: 7,
    currentWidth: 512,
    currentHeight: 768,
    currentSamplerName: 'Euler',
    promptSuffix: '',
  },
  defaults: {
    detailLevel: 3,
    autoSaveInterval: 60,
    exportQuality: 'high',
  },
  language: 'en',
};

export const useProjectStore = create<ProjectStore>()(
  persist(
    (set, get) => ({
      currentProject: null,
      panels: [],
      characters: [],
      activeTab: 'storyboard',
      settings: defaultSettings,
      isLoading: false,
      promptMode: 'turbo',
      composerProjectId: null,

      setCurrentProject: (project) => {
        const storedPanels: Panel[] = get().panels || [];
        const apiPanels: Panel[] = project?.panels || [];
        const mergedPanels = apiPanels.map(apiPanel => {
          const storedPanel = storedPanels.find(p => p.id === apiPanel.id);
          if (!apiPanel.image && storedPanel?.image) {
            return { ...apiPanel, image: storedPanel.image };
          }
          return apiPanel;
        });
        set({ currentProject: project, panels: mergedPanels });
      },

      loadProjectWithImages: async (projectId: string) => {
        try {
          const res = await fetch(`/api/projects/load/${projectId}`);
          const data = await res.json();
          if (data.project) {
            const apiPanels: Panel[] = (data.project.panels || []) as Panel[];
            const storedPanels: Panel[] = get().panels || [];
            const mergedPanels = apiPanels.map(apiPanel => {
              const storedPanel = storedPanels.find(p => p.id === apiPanel.id);
              if (!apiPanel.image && storedPanel?.image) {
                return { ...apiPanel, image: storedPanel.image };
              }
              return apiPanel;
            });
            const needsSave = mergedPanels.some((p, i) => p.image !== apiPanels[i]?.image);
            set({ currentProject: data.project, panels: mergedPanels });
            if (needsSave) {
              const updatedProject = { ...data.project, panels: mergedPanels };
              fetch('/api/projects/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updatedProject),
              });
            }
          }
        } catch {
          // offline load failed: keep whatever is already in the store
        }
      },

      generatingPanels: [],

      startGenerating: (panelId) => set((state) => ({
        generatingPanels: state.generatingPanels.includes(panelId)
          ? state.generatingPanels
          : [...state.generatingPanels, panelId],
      })),

      stopGenerating: (panelId) => set((state) => ({
        generatingPanels: state.generatingPanels.filter((id) => id !== panelId),
      })),
      
      setPanels: (panels) => set({ panels }),
      
      addPanel: (panel) => set((state) => ({ panels: [...state.panels, panel] })),
      
      updatePanel: (id, updates) => set((state) => ({
        panels: state.panels.map((p) => (p.id === id ? { ...p, ...updates } : p)),
      })),
      
      removePanel: (id) => set((state) => ({
        panels: state.panels.filter((p) => p.id !== id),
      })),
      
      reorderPanels: (panels) => set({ panels }),
      
      setActiveTab: (activeTab) => set({ activeTab }),
      
      setSettings: (settings) => set({ settings }),
      
      setLoading: (isLoading) => set({ isLoading }),
      
      updatePanelImage: (id, image) => set((state) => ({
        panels: state.panels.map((p) => (p.id === id ? { ...p, image } : p)),
      })),
      
      updatePanelPrompt: (id, prompt) => set((state) => ({
        panels: state.panels.map((p) => (p.id === id ? { ...p, prompt: { ...p.prompt, ...prompt } } : p)),
      })),
      
      setCharacters: (characters) => set({ characters }),
      
      addCharacter: (character) => set((state) => ({ characters: [...state.characters, character] })),
      
      updateCharacter: (id, updates) => set((state) => ({
        characters: state.characters.map((c) => (c.id === id ? { ...c, ...updates } : c)),
      })),
      
      removeCharacter: (id) => set((state) => ({
        characters: state.characters.filter((c) => c.id !== id),
      })),
      
      extractCharactersFromPanels: () => {
        const panels = get().panels;
        const charMap = new Map<string, Character>();
        
        panels.forEach((panel) => {
          panel.characters?.forEach((charName) => {
            if (!charMap.has(charName)) {
              charMap.set(charName, {
                id: `char_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
                name: charName,
                description: panel.dialogue || '',
                sourcePanelIds: [panel.id],
                createdAt: new Date().toISOString(),
                updatedAt: new Date().toISOString(),
              });
            } else {
              const existing = charMap.get(charName)!;
              if (!existing.sourcePanelIds.includes(panel.id)) {
                existing.sourcePanelIds.push(panel.id);
              }
            }
          });
        });
        
        return Array.from(charMap.values());
      },

      setPromptMode: (promptMode) => set({ promptMode }),

      setComposerProjectId: (id) => set({ composerProjectId: id }),
    }),
    {
      name: 'automanga-storage',
      partialize: (state) => ({
        settings: state.settings,
        activeTab: state.activeTab,
        characters: state.characters?.map((c) => {
          const { image: _image, ...charData } = c;
          return charData;
        }),
        promptMode: state.promptMode,
        panels: state.panels?.map((p) => {
          const { image: _image, ...panelData } = p;
          return panelData;
        }),
      }),
    }
  )
);
