import { describe, it, expect, beforeEach } from 'vitest';
import { openedDraft, useComicsDrafts, dirtyScripts, isDirty } from './scriptDrafts';

describe('openedDraft', () => {
  it('takes the file text for a new or clean draft', () => {
    expect(openedDraft(undefined, 'A')).toEqual({ text: 'A', savedText: 'A' });
    expect(openedDraft({ text: 'old', savedText: 'old' }, 'new')).toEqual({ text: 'new', savedText: 'new' });
  });
  it('keeps unsaved edits, rebased on the file text', () => {
    expect(openedDraft({ text: 'edited', savedText: 'old' }, 'disk')).toEqual({ text: 'edited', savedText: 'disk' });
  });
});

describe('useComicsDrafts', () => {
  beforeEach(() => useComicsDrafts.setState({ selected: null, drafts: {} }));

  it('keeps each script\'s draft and reports the dirty ones', () => {
    const { setDraft } = useComicsDrafts.getState();
    setDraft('a', { text: 'x', savedText: 'x' });
    setDraft('b', { text: 'y', savedText: 'y' });
    setDraft('b', { text: 'y2' });
    expect(useComicsDrafts.getState().drafts.b).toEqual({ text: 'y2', savedText: 'y' });
    expect(dirtyScripts()).toEqual(['b']);
    setDraft('b', { savedText: 'y2' });
    expect(dirtyScripts()).toEqual([]);
    expect(isDirty(undefined)).toBe(false);
  });
});
