import { useEffect, useRef, useState } from 'react';
import { FiLock } from 'react-icons/fi';
import { translations } from '../../i18n';
import type { TranslationKeys } from '../../i18n';
import { fill } from '../../hooks/useTranslation';
import { googleStartUrl, login, preferredLanguage } from '../../auth';
import type { AuthStatus, LoginErrorCode } from '../../auth';
import './login.css';

export const SET_PASSWORD_CMD = '.venv/bin/python -m backend.core.auth set-password';

/** Google's "G" mark (its colours are part of the brand; the button around it uses the theme). */
export function GoogleMark({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden="true" focusable="false">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
    </svg>
  );
}

interface Props {
  /** Called after a successful sign-in. */
  onSuccess: () => void;
  /** The server has no password yet: show the CLI hint instead of the form. */
  unconfigured?: boolean;
  /** Shown over a running app whose session ended. */
  overlay?: boolean;
  /** /api/auth/status: which sign-in methods this page offers. */
  status?: AuthStatus | null;
  /** ?login_error from a failed Google sign-in. */
  loginError?: LoginErrorCode | null;
}

export function LoginScreen({ onSuccess, unconfigured = false, overlay = false, status = null, loginError = null }: Props) {
  // shown before /api/settings is readable, so the language comes from the browser
  const t = (translations[preferredLanguage()] as TranslationKeys).auth;
  const loginErrorText: Record<LoginErrorCode, string> = {
    denied: t.loginErrorDenied,
    not_allowed: t.loginErrorNotAllowed,
    invalid: t.loginErrorInvalid,
    misconfigured: t.loginErrorMisconfigured,
    rate: t.loginErrorRate,
  };
  // an older backend has no passwordLogin field: the password form, as before
  const showPassword = status?.passwordLogin ?? true;
  const showGoogle = !!status?.google;
  const googleElsewhere = !showGoogle && status?.googleUrl ? status.googleUrl : null;
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(
    loginError ? loginErrorText[loginError] : overlay ? t.sessionExpired : null);
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
    } else if (r.reason === 'disabled') {
      setError(t.passwordDisabled);
    } else {
      setError(r.reason === 'wrong' ? t.wrong : t.error);
    }
    setPassword('');
    window.setTimeout(() => inputRef.current?.focus(), 0);
  };

  const passwordForm = showPassword && !noPassword;
  const [elsewhereBefore, elsewhereAfter = ''] = t.googleElsewhere.split('{url}');
  const message = waiting ? fill(t.rateLimited, { s: waiting }) : error;
  const isNotice = !waiting && error === t.sessionExpired;

  return (
    <div className={`login-screen${overlay ? ' login-screen--overlay' : ''}`}
         {...(overlay ? { role: 'dialog', 'aria-modal': true, 'aria-labelledby': 'login-title' } : {})}>
      <form className="login-card" onSubmit={submit} aria-labelledby="login-title">
        <div className="login-icon" aria-hidden="true"><FiLock size={20} /></div>
        <h1 id="login-title" className="login-title">AutoManga</h1>
        <p className="login-subtitle">{t.subtitle}</p>

        {noPassword && !showGoogle ? (
          <div className="login-unconfigured">
            <p>{t.unconfigured}</p>
            <code>{SET_PASSWORD_CMD}</code>
          </div>
        ) : (
          <>
            {showGoogle && (
              <a className="login-google" href={googleStartUrl()}>
                <GoogleMark />
                <span>{t.google}</span>
              </a>
            )}
            {showGoogle && passwordForm && (
              <div className="login-divider" aria-hidden="true"><span>{t.or}</span></div>
            )}
            {passwordForm && (
              <>
                <label className="login-label" htmlFor="login-password">{t.password}</label>
                <input
                  id="login-password"
                  ref={inputRef}
                  className="input"
                  type="password"
                  name="password"
                  autoComplete="current-password"
                  autoFocus={!showGoogle}
                  required
                  value={password}
                  disabled={busy}
                  aria-invalid={!!message && !isNotice}
                  aria-describedby={message ? 'login-message' : undefined}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </>
            )}
            <div id="login-message" className={`login-message${isNotice ? ' login-message--notice' : ''}`} role="alert" aria-live="polite">
              {message}
            </div>
            {passwordForm && (
              <button
                type="submit"
                className="btn btn-primary login-submit"
                disabled={busy || !password || waiting > 0}
              >
                {busy ? t.signingIn : t.signIn}
              </button>
            )}
            {googleElsewhere && (
              <p className="login-hint">
                {elsewhereBefore}<a href={googleElsewhere}>{googleElsewhere}</a>{elsewhereAfter}
              </p>
            )}
            {!passwordForm && !showGoogle && !googleElsewhere && (
              <p className="login-hint">{t.noMethod}</p>
            )}
          </>
        )}
      </form>
    </div>
  );
}
