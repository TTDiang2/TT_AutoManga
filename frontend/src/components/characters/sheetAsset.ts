/** Character sheets live in the asset store (POST /api/assets/file, kind
    "character"); the character keeps only the /api/assets/file/<id> URL, so
    data/characters.json never carries multi-MB base64. */

/** A base64 data URL as a Blob (null when it is not one). */
export function dataUrlToBlob(dataUrl: string): Blob | null {
  const m = /^data:([\w/+.-]+);base64,(.*)$/s.exec(dataUrl);
  if (!m) return null;
  try {
    const bin = atob(m[2].replace(/\s+/g, ''));
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new Blob([bytes], { type: m[1] });
  } catch {
    return null;
  }
}

/** Upload an image (a File, Blob or data URL) as a character asset; its URL. */
export async function uploadSheet(image: Blob | string, filename = 'sheet.png'): Promise<string> {
  const blob = typeof image === 'string' ? dataUrlToBlob(image) : image;
  if (!blob) throw new Error('not an image');
  const form = new FormData();
  form.append('file', blob, image instanceof File ? image.name : filename);
  form.append('kind', 'character');
  const res = await fetch('/api/assets/file', { method: 'POST', body: form });
  const data = res.ok ? await res.json().catch(() => null) : null;
  if (!data?.url) throw new Error(res.ok ? 'no url in response' : `HTTP ${res.status}`);
  return data.url as string;
}

/** True when a sheet is still stored inline (needs POST /api/characters/migrate-images). */
export const isInlineImage = (image?: string | null) => !!image && image.startsWith('data:');
