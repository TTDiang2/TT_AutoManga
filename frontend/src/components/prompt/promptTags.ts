import type { PromptData } from '../../types';

/** A panel's tag prompt as one comma-separated string. Tags are a list when
 *  the Prompt Lab wrote them, but one string in projects converted from
 *  Comics scripts; anything else counts as no tags. */
export function tagsText(tags: PromptData['tags'] | unknown): string {
  const list = Array.isArray(tags) ? tags : typeof tags === 'string' ? tags.split(',') : [];
  return list
    .filter((t): t is string => typeof t === 'string')
    .map(t => t.trim())
    .filter(Boolean)
    .join(', ');
}
