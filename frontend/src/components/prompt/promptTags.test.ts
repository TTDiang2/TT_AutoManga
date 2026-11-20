import { describe, expect, it } from 'vitest';
import { tagsText } from './promptTags';

describe('tagsText', () => {
  it('joins a tag list', () => {
    expect(tagsText([' 1girl', 'rain ', '', 'street'])).toBe('1girl, rain, street');
  });
  it('accepts one comma-separated string (Comics conversions)', () => {
    expect(tagsText('masterpiece,  1boy , ,solo')).toBe('masterpiece, 1boy, solo');
  });
  it('treats anything else as no tags', () => {
    expect(tagsText(undefined)).toBe('');
    expect(tagsText(null)).toBe('');
    expect(tagsText(42)).toBe('');
    expect(tagsText([1, 'a'])).toBe('a');
  });
});
