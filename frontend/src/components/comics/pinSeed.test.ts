import { describe, it, expect } from 'vitest';
import { pinSeed } from './pinSeed';

const SCRIPT = ['PAGE', 'PANEL w=2', 'shot: wide', 'A rooftop.', '', 'PANEL h=1.5 seed=77', 'MARA: Hi.'].join('\n');

describe('pinSeed', () => {
  it('appends seed=N to a PANEL line without one', () => {
    expect(pinSeed(SCRIPT, { line: 2, seedLine: null }, 4301).split('\n')[1]).toBe('PANEL w=2 seed=4301');
  });

  it('replaces an existing seed= on the PANEL line, keeping the other args', () => {
    expect(pinSeed(SCRIPT, { line: 6, seedLine: null }, 12).split('\n')[5]).toBe('PANEL h=1.5 seed=12');
    expect(pinSeed('PANEL seed=5 w=2', { line: 1, seedLine: null }, 9)).toBe('PANEL seed=9 w=2');
  });

  it('handles a bare PANEL line and trailing spaces', () => {
    expect(pinSeed('PAGE\nPANEL   \nx', { line: 2, seedLine: null }, 3)).toBe('PAGE\nPANEL seed=3\nx');
  });

  it('rewrites the seed: key line when the panel has one', () => {
    const text = 'PANEL w=2\n  seed: 100\nA rooftop.';
    expect(pinSeed(text, { line: 1, seedLine: 2 }, 4301)).toBe('PANEL w=2\n  seed: 4301\nA rooftop.');
    expect(pinSeed('PANEL\nSeed:100', { line: 1, seedLine: 2 }, 7)).toBe('PANEL\nSeed:7');
  });

  it('keeps CRLF line endings', () => {
    expect(pinSeed('PANEL\r\nseed: 1\r\nx', { line: 1, seedLine: 2 }, 2)).toBe('PANEL\r\nseed: 2\r\nx');
    expect(pinSeed('PANEL w=1\r\nx', { line: 1, seedLine: null }, 2)).toBe('PANEL w=1 seed=2\r\nx');
  });

  it('falls back to the PANEL line when the seed line moved', () => {
    expect(pinSeed('PANEL\nshot: wide', { line: 1, seedLine: 2 }, 5)).toBe('PANEL seed=5\nshot: wide');
  });

  it('throws when the PANEL line is gone', () => {
    expect(() => pinSeed('PAGE\nA rooftop.', { line: 2, seedLine: null }, 5)).toThrow(/not a PANEL line/);
  });

  it('does not touch a seed= in the description', () => {
    expect(pinSeed('PANEL w=2\nreseed=3', { line: 1, seedLine: null }, 4)).toBe('PANEL w=2 seed=4\nreseed=3');
  });
});
