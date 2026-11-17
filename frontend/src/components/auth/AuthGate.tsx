import { useCallback, useEffect, useState } from 'react'
import App from '../../App.tsx'
import { LoginScreen } from './LoginScreen'
import { AUTH_REQUIRED_EVENT, AUTH_RESTORED_EVENT, fetchAuthStatus, takeLoginError } from '../../auth'
import type { AuthStatus } from '../../auth'

type Phase = 'checking' | 'login' | 'unconfigured' | 'app'

/** Checks /api/auth/status before rendering the app; shows the login screen
    for remote visitors without a session (local visitors never see it). */
export function AuthGate() {
  const [phase, setPhase] = useState<Phase>('checking')
  const [status, setStatus] = useState<AuthStatus | null>(null)
  // ?login_error=… from a failed Google sign-in (read once, removed from the URL)
  const [loginError] = useState(takeLoginError)
  // a session that ends while the app runs: sign in over it, keeping unsaved state
  const [expired, setExpired] = useState(false)

  const check = useCallback(() => {
    fetchAuthStatus()
      .then((s) => {
        setStatus(s)
        setPhase(s.local || s.authenticated ? 'app' : s.configured ? 'login' : 'unconfigured')
      })
      .catch(() => setPhase('app'))   // status unreadable (server down/older backend): the app shows its own errors
  }, [])

  useEffect(() => { check() }, [check])

  useEffect(() => {
    const onAuthRequired = () => {
      setExpired(true)
      // refresh which sign-in methods the overlay offers
      fetchAuthStatus().then(setStatus).catch(() => {})
    }
    window.addEventListener(AUTH_REQUIRED_EVENT, onAuthRequired)
    return () => window.removeEventListener(AUTH_REQUIRED_EVENT, onAuthRequired)
  }, [])

  if (phase === 'checking') return null
  if (phase !== 'app') {
    return <LoginScreen unconfigured={phase === 'unconfigured'} status={status} loginError={loginError}
                        onSuccess={() => { setExpired(false); setPhase('app') }} />
  }
  return (
    <>
      {/* inert while the sign-in overlay is up: no focus or clicks reach the app behind it */}
      <div className="app-root" inert={expired}>
        <App />
      </div>
      {expired && (
        <LoginScreen overlay status={status} onSuccess={() => {
          setExpired(false)
          window.dispatchEvent(new CustomEvent(AUTH_RESTORED_EVENT))
        }} />
      )}
    </>
  )
}
