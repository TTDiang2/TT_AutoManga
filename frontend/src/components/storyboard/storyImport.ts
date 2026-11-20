/** Loading a story from a .md/.txt file (Storyboard tab and the Create wizard). */

export const MAX_IMPORT_BYTES = 5 * 1024 * 1024;
export const IMPORT_ACCEPT = '.md,.markdown,.txt,text/markdown,text/plain';

export function isImportableName(name: string): boolean {
  return /\.(md|markdown|txt)$/i.test(name);
}

/**
 * Text from a file's bytes, whatever common encoding it was saved in:
 * a UTF-8 or UTF-16 byte-order mark wins; otherwise strict UTF-8; otherwise
 * GB18030 (a superset of GBK/GB2312, which many Chinese .txt novels use).
 * Line endings become \n.
 */
export function decodeStoryText(bytes: Uint8Array): string {
  let text: string;
  if (bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) {
    text = new TextDecoder('utf-8').decode(bytes);            // strips the BOM
  } else if (bytes[0] === 0xff && bytes[1] === 0xfe) {
    text = new TextDecoder('utf-16le').decode(bytes);
  } else if (bytes[0] === 0xfe && bytes[1] === 0xff) {
    text = new TextDecoder('utf-16be').decode(bytes);
  } else {
    try {
      text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
    } catch {
      text = new TextDecoder('gb18030').decode(bytes);
    }
  }
  return text.replace(/^\uFEFF/, '').replace(/\r\n?/g, '\n');
}

export type StoryFileResult =
  | { ok: true; text: string }
  | { ok: false; reason: 'type' | 'size' | 'empty' };

export async function readStoryFile(file: File): Promise<StoryFileResult> {
  if (!isImportableName(file.name)) return { ok: false, reason: 'type' };
  if (file.size > MAX_IMPORT_BYTES) return { ok: false, reason: 'size' };
  const text = decodeStoryText(new Uint8Array(await file.arrayBuffer()));
  if (!text.trim()) return { ok: false, reason: 'empty' };
  return { ok: true, text };
}
