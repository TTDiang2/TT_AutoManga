/** Login gate client (backend/core/auth.py). The session is an HttpOnly,
    same-origin cookie, so plain fetch(), <img>, @font-face and download links
    all carry it without changes. */

export interface AuthStatus {
  configured: boolean;
  authenticated: boolean;
  local: boolean;
}

/** Fired on window when an /api request comes back 401 (session gone). */
export const AUTH_REQUIRED_EVENT = 'automanga:auth-required';

export async function fetchAuthStatus(): Promise<AuthStatus> {
  const res = await fetch('/api/auth/status', { cache: 'no-store' });
  if (!res.ok) throw new Error(`auth status ${res.status}`);
  return res.json();
}

function requestUrl(input: RequestInfo | URL): URL | null {
  try {
    const raw = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    return new URL(raw, window.location.href);
  } catch {
    return null;
  }
}

let installed = false;

/** Wrap window.fetch once: a 401 from a same-origin /api URL (other than the
    auth endpoints, which report their own errors) dispatches AUTH_REQUIRED_EVENT. */
export function installFetchGuard() {
  if (installed) return;
  installed = true;
  const original = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const res = await original(input, init);
    if (res.status === 401) {
      const url = requestUrl(input);
      if (url && url.origin === window.location.origin
          && url.pathname.startsWith('/api/') && !url.pathname.startsWith('/api/auth/')) {
        window.dispatchEvent(new CustomEvent(AUTH_REQUIRED_EVENT));
      }
    }
    return res;
  };
}

export type AuthResult =
  | { ok: true }
  | { ok: false; reason: 'wrong' | 'rate' | 'unconfigured' | 'invalid' | 'error'; retryAfter?: number; detail?: string };

async function postJson(path: string, body?: unknown): Promise<AuthResult> {
  let res: Response;
  try {
    res = await fetch(path, {
      method: 'POST',
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    return { ok: false, reason: 'error' };
  }
  if (res.ok) return { ok: true };
  let detail: string | undefined;
  try {
    const data = await res.json();
    detail = typeof data.detail === 'string' ? data.detail : undefined;
  } catch { /* not JSON */ }
  if (res.status === 429) {
    return { ok: false, reason: 'rate', retryAfter: Number(res.headers.get('Retry-After')) || 60, detail };
  }
  if (res.status === 401 || res.status === 403) return { ok: false, reason: 'wrong', detail };
  if (res.status === 503 || res.status === 409) return { ok: false, reason: 'unconfigured', detail };
  if (res.status === 400) return { ok: false, reason: 'invalid', detail };
  return { ok: false, reason: 'error', detail };
}

export const login = (password: string) => postJson('/api/auth/login', { password });
export const logout = () => postJson('/api/auth/logout');
export const logoutAll = () => postJson('/api/auth/logout-all');
export const changePassword = (current: string, next: string) =>
  postJson('/api/auth/password', { current, new: next });

/** Language for screens shown before /api/settings is readable: the last
    one the app used, else the browser's. */
const LANG_KEY = 'automanga-language';

export function rememberLanguage(lang: string) {
  try { localStorage.setItem(LANG_KEY, lang); } catch { /* private mode */ }
}

export function preferredLanguage(): 'en' | 'zh' {
  try {
    const v = localStorage.getItem(LANG_KEY);
    if (v === 'en' || v === 'zh') return v;
  } catch { /* private mode */ }
  return navigator.language?.toLowerCase().startsWith('zh') ? 'zh' : 'en';
}
