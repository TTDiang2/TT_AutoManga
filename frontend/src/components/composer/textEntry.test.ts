import { describe, it, expect } from 'vitest';
import { isTextEntry } from './textEntry';

const input = (type?: string) => {
  const el = document.createElement('input');
  if (type !== undefined) el.setAttribute('type', type);
  return el;
};

describe('isTextEntry', () => {
  it('treats text-like inputs, textarea and contentEditable as text entry', () => {
    for (const type of [undefined, 'text', 'number', 'search', 'email', 'url', 'tel', 'password', 'TEXT']) {
      expect(isTextEntry(input(type))).toBe(true);
    }
    expect(isTextEntry(document.createElement('textarea'))).toBe(true);
    const div = document.createElement('div');
    div.contentEditable = 'true';
    // jsdom doesn't compute isContentEditable; a browser does
    Object.defineProperty(div, 'isContentEditable', { value: true });
    expect(isTextEntry(div)).toBe(true);
  });

  it('does not treat sliders, checkboxes, colour pickers or selects as text entry', () => {
    for (const type of ['range', 'checkbox', 'radio', 'color', 'file', 'button']) {
      expect(isTextEntry(input(type))).toBe(false);
    }
    expect(isTextEntry(document.createElement('select'))).toBe(false);
    expect(isTextEntry(document.createElement('button'))).toBe(false);
    expect(isTextEntry(null)).toBe(false);
  });
});
