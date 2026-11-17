import { create } from 'zustand';

/** The editor's text of one .comic script and the text last read from / written to disk. */
export interface Draft { text: string; savedText: string }

interface ComicsDrafts {
  /** The script open in the Comics tab (kept while the tab is unmounted). */
  selected: string | null;
  drafts: Record<string, Draft>;
  setSelected: (name: string | null) => void;
  setDraft: (name: string, patch: Partial<Draft>) => void;
}

/** Opening a script: an unsaved draft keeps its text (its base becomes what's on disk now);
    a clean one takes the file's text. */
export function openedDraft(draft: Draft | undefined, fileText: string): Draft {
  return draft && draft.text !== draft.savedText
    ? { text: draft.text, savedText: fileText }
    : { text: fileText, savedText: fileText };
}

export const isDirty = (d: Draft | undefined) => !!d && d.text !== d.savedText;

/** The Comics editor's state lives here, not in ComicsTab: App unmounts inactive tabs,
    and script edits must survive switching tabs and scripts. */
export const useComicsDrafts = create<ComicsDrafts>()((set) => ({
  selected: null,
  drafts: {},
  setSelected: (name) => set({ selected: name }),
  setDraft: (name, patch) => set((s) => {
    const prev = s.drafts[name] ?? { text: '', savedText: '' };
    return { drafts: { ...s.drafts, [name]: { ...prev, ...patch } } };
  }),
}));

export const dirtyScripts = () =>
  Object.entries(useComicsDrafts.getState().drafts).filter(([, d]) => isDirty(d)).map(([name]) => name);

if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', (e) => {
    if (dirtyScripts().length === 0) return;
    e.preventDefault();
    e.returnValue = '';   // older browsers want it set to show the prompt
  });
}
