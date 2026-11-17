import { describe, it, expect, vi, afterEach } from 'vitest';
import { dataUrlToBlob, uploadSheet, isInlineImage } from './sheetAsset';

describe('dataUrlToBlob', () => {
  it('decodes a base64 data URL with its type', async () => {
    const blob = dataUrlToBlob('data:image/png;base64,aGVsbG8=');
    expect(blob?.type).toBe('image/png');
    expect(new TextDecoder().decode(await blob!.arrayBuffer())).toBe('hello');
  });
  it('rejects anything else', () => {
    expect(dataUrlToBlob('/api/assets/file/abc')).toBeNull();
    expect(dataUrlToBlob('data:image/png,plain')).toBeNull();
  });
});

describe('uploadSheet', () => {
  afterEach(() => vi.unstubAllGlobals());
  it('posts the image as a character asset and returns its URL', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ url: '/api/assets/file/x1' }) });
    vi.stubGlobal('fetch', fetchMock);
    expect(await uploadSheet('data:image/png;base64,aGVsbG8=')).toBe('/api/assets/file/x1');
    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/assets/file');
    expect((opts.body as FormData).get('kind')).toBe('character');
  });
  it('throws on a failed upload', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500 }));
    await expect(uploadSheet(new Blob(['x'], { type: 'image/png' }))).rejects.toThrow('HTTP 500');
  });
});

describe('isInlineImage', () => {
  it('spots data URLs only', () => {
    expect(isInlineImage('data:image/png;base64,xx')).toBe(true);
    expect(isInlineImage('/api/assets/file/x')).toBe(false);
    expect(isInlineImage(null)).toBe(false);
  });
});
