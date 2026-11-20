// Swapping the people in a pasted story for characters from the library
// (Story step of the Create wizard).

const CJK = /[぀-ヿ㐀-鿿豈-﫿가-힯]/;

/** Capitalised words that are not names (sentence starters, pronouns, ...). */
const NOT_NAMES = new Set([
  'a', 'an', 'the', 'and', 'but', 'or', 'so', 'yet', 'if', 'then', 'when', 'while', 'as', 'at', 'by',
  'for', 'from', 'in', 'into', 'of', 'on', 'to', 'with', 'without', 'after', 'before', 'until', 'because',
  'i', 'me', 'my', 'we', 'our', 'you', 'your', 'he', 'him', 'his', 'she', 'her', 'it', 'its', 'they',
  'them', 'their', 'this', 'that', 'these', 'those', 'there', 'here', 'what', 'who', 'why', 'how',
  'where', 'which', 'yes', 'no', 'not', 'oh', 'ok', 'okay', 'hey', 'well', 'now', 'just', 'all',
  'one', 'two', 'three', 'some', 'every', 'each', 'once', 'later', 'meanwhile', 'suddenly', 'finally',
  'chapter', 'part', 'page', 'panel', 'scene', 'episode', 'act', 'prologue', 'epilogue', 'end', 'note',
  'caption', 'narration', 'narrator', 'sfx', 'title', 'mr', 'mrs', 'ms', 'dr', 'sir', 'lady', 'lord',
  'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
  'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october',
  'november', 'december', 'god', 'ext', 'int',
]);

const SPEAKER = /^[\s>*_-]*([^\s:：*_"“”()[\]]{1,24})[*_]*\s*[:：]/;
const WORD = /\p{Lu}[\p{Ll}\p{M}'’-]*\p{Ll}/gu;

/**
 * The people a story seems to be about, most frequent first: speakers of
 * "Name: line" / "Name：台词" lines, plus capitalised words that recur and
 * appear at least once mid-sentence (so "The" or "Later" don't count).
 */
export function storyNames(text: string, max = 12): string[] {
  const counts = new Map<string, { name: string; n: number; score: number }>();
  const add = (name: string, score: number) => {
    const k = name.toLowerCase();
    if (NOT_NAMES.has(k) || /^\d/.test(name)) return;
    const e = counts.get(k) || { name, n: 0, score: 0 };
    e.n++;
    e.score += score;
    counts.set(k, e);
  };

  const midSentence = new Set<string>();
  for (const line of text.split(/\r?\n/)) {
    const sp = line.match(SPEAKER);
    if (sp) add(sp[1], 3);
    for (const m of line.matchAll(WORD)) {
      const before = line.slice(0, m.index).replace(/["“'‘(*_\s]+$/, '');
      if (before && !/[.!?…:：]$/.test(before)) midSentence.add(m[0].toLowerCase());
      if (!(sp && m.index! <= line.indexOf(sp[1]))) add(m[0], 1);
    }
  }

  return [...counts.values()]
    .filter(e => e.score >= 3 || (e.n >= 2 && midSentence.has(e.name.toLowerCase())))
    .sort((a, b) => b.score - a.score)
    .slice(0, max)
    .map(e => e.name);
}

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/**
 * Replaces every name in `swaps` (from → to) at once, so swapping two people
 * works. Whole words only (CJK names: anywhere), case-insensitive; a name
 * written in capitals ("ANNA:") gets its replacement in capitals.
 */
export function swapNames(text: string, swaps: Record<string, string>): string {
  const pairs = Object.entries(swaps)
    .map(([from, to]) => [from.trim(), to.trim()] as const)
    .filter(([from, to]) => from && to && from.toLowerCase() !== to.toLowerCase());
  if (!pairs.length) return text;
  const lookup = new Map(pairs.map(([from, to]) => [from.toLowerCase(), to]));
  const alts = pairs
    .map(([from]) => from)
    .sort((a, b) => b.length - a.length)
    .map(from => CJK.test(from) ? escape(from) : `(?<![\\p{L}\\p{N}_])${escape(from)}(?![\\p{L}\\p{N}_])`);
  return text.replace(new RegExp(alts.join('|'), 'giu'), match => {
    const to = lookup.get(match.toLowerCase()) ?? match;
    const upper = match.length > 1 && match === match.toUpperCase() && match !== match.toLowerCase();
    return upper ? to.toUpperCase() : to;
  });
}
