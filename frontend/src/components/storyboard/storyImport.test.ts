import { describe, expect, it } from 'vitest';
import { decodeStoryText, isImportableName, readStoryFile, MAX_IMPORT_BYTES } from './storyImport';

const bytes = (...b: number[]) => new Uint8Array(b);
const utf8 = (s: string) => new TextEncoder().encode(s);
const utf16le = (s: string, bom = true) => {
  const out: number[] = bom ? [0xff, 0xfe] : [];
  for (const ch of s) { const c = ch.charCodeAt(0); out.push(c & 0xff, c >> 8); }
  return new Uint8Array(out);
};

describe('decodeStoryText', () => {
  it('reads plain UTF-8 and strips a UTF-8 BOM', () => {
    expect(decodeStoryText(utf8('雪桥 rain'))).toBe('雪桥 rain');
    expect(decodeStoryText(new Uint8Array([0xef, 0xbb, 0xbf, ...utf8('Hi')]))).toBe('Hi');
  });
  it('reads UTF-16 with a byte-order mark (Notepad "Unicode")', () => {
    expect(decodeStoryText(utf16le('你好 Yuki'))).toBe('你好 Yuki');
    expect(decodeStoryText(bytes(0xfe, 0xff, 0x4f, 0x60, 0x59, 0x7d))).toBe('你好');
  });
  it('falls back to GBK/GB18030 when the bytes are not UTF-8', () => {
    // 你好，世界 in GBK
    expect(decodeStoryText(bytes(0xc4, 0xe3, 0xba, 0xc3, 0xa3, 0xac, 0xca, 0xc0, 0xbd, 0xe7))).toBe('你好，世界');
  });
  it('normalises line endings', () => {
    expect(decodeStoryText(utf8('a\r\nb\rc\n'))).toBe('a\nb\nc\n');
  });
});

describe('readStoryFile', () => {
  it('accepts .md/.markdown/.txt only', () => {
    expect(isImportableName('story.MD')).toBe(true);
    expect(isImportableName('a.markdown')).toBe(true);
    expect(isImportableName('notes.txt')).toBe(true);
    expect(isImportableName('cover.png')).toBe(false);
    expect(isImportableName('txt')).toBe(false);
  });
  it('rejects other types, empty files and files over the limit', async () => {
    expect(await readStoryFile(new File(['x'], 'a.png'))).toEqual({ ok: false, reason: 'type' });
    expect(await readStoryFile(new File([' \n\t '], 'a.txt'))).toEqual({ ok: false, reason: 'empty' });
    const big = new File([new Uint8Array(MAX_IMPORT_BYTES + 1)], 'big.txt');
    expect(await readStoryFile(big)).toEqual({ ok: false, reason: 'size' });
  });
  it('returns the decoded text', async () => {
    const gbk = new File([bytes(0xc4, 0xe3, 0xba, 0xc3)], '小说.txt');
    expect(await readStoryFile(gbk)).toEqual({ ok: true, text: '你好' });
  });
});
