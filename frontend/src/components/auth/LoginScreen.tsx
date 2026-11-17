import { useEffect, useRef, useState } from 'react';
import { FiLock } from 'react-icons/fi';
import { translations } from '../../i18n';
import type { TranslationKeys } from '../../i18n';
import { fill } from '../../hooks/useTranslation';
import { login, preferredLanguage } from '../../auth';
import './login.css';

export const SET_PASSWORD_CMD = '.venv/bin/python -m backend.core.auth set-password';

interface Props {
  /** Called after a successful sign-in. */
  onSuccess: () => void;
  /** The server has no password yet: show the CLI hint instead of the form. */
  unconfigured?: boolean;
  /** Shown over a running app whose session ended. */
  overlay?: boolean;
}

export function LoginScreen({ onSuccess, unconfigured = false, overlay = false }: Props) {
  // shown before /api/settings is readable, so the language comes from the browser
  const t = (translations[preferredLanguage()] as TranslationKeys).auth;
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(overlay ? t.sessionExpired : null);
  const [retryUntil, setRetryUntil] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  const [noPassword, setNoPassword] = useState(unconfigured);
  const inputRef = useRef<HTMLInputElement>(null);

  const waiting = Math.max(0, Math.ceil((retryUntil - now) / 1000));

  useEffect(() => {
    if (!retryUntil) return;
    const id = window.setInterval(() => {
      const n = Date.now();
      setNow(n);
      if (n >= retryUntil) {
        setRetryUntil(0);
        setError(null);
        window.clearInterval(id);
      }
    }, 500);
    return () => window.clearInterval(id);
  }, [retryUntil]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password || busy || waiting) return;
    setBusy(true);
    setError(null);
    const r = await login(password);
    setBusy(false);
    if (r.ok) {
      setPassword('');
      onSuccess();
      return;
    }
    if (r.reason === 'rate') {
      setRetryUntil(Date.now() + (r.retryAfter ?? 60) * 1000);
      setNow(Date.now());
    } else if (r.reason === 'unconfigured') {
      setNoPassword(true);
    } else {
      setError(r.reason === 'wrong' ? t.wrong : t.error);
    }
    setPassword('');
    window.setTimeout(() => inputRef.current?.focus(), 0);
  };

  const message = waiting ? fill(t.rateLimited, { s: waiting }) : error;
  const isNotice = !waiting && error === t.sessionExpired;

  return (
    <div className={`login-screen${overlay ? ' login-screen--overlay' : ''}`}
         {...(overlay ? { role: 'dialog', 'aria-modal': true, 'aria-labelledby': 'login-title' } : {})}>
      <form className="login-card" onSubmit={submit} aria-labelledby="login-title">
        <div className="login-icon" aria-hidden="true"><FiLock size={20} /></div>
        <h1 id="login-title" className="login-title">AutoManga</h1>
        <p className="login-subtitle">{t.subtitle}</p>

        {noPassword ? (
          <div className="login-unconfigured">
            <p>{t.unconfigured}</p>
            <code>{SET_PASSWORD_CMD}</code>
          </div>
        ) : (
          <>
            <label className="login-label" htmlFor="login-password">{t.password}</label>
            <input
              id="login-password"
              ref={inputRef}
              className="input"
              type="password"
              name="password"
              autoComplete="current-password"
              autoFocus
              required
              value={password}
              disabled={busy}
              aria-invalid={!!message && !isNotice}
              aria-describedby={message ? 'login-message' : undefined}
              onChange={(e) => setPassword(e.target.value)}
            />
            <div id="login-message" className={`login-message${isNotice ? ' login-message--notice' : ''}`} role="alert" aria-live="polite">
              {message}
            </div>
            <button
              type="submit"
              className="btn btn-primary login-submit"
              disabled={busy || !password || waiting > 0}
            >
              {busy ? t.signingIn : t.signIn}
            </button>
          </>
        )}
      </form>
    </div>
  );
}
