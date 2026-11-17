import { useCallback, useEffect, useState } from 'react'
import App from '../../App.tsx'
import { LoginScreen } from './LoginScreen'
import { AUTH_REQUIRED_EVENT, fetchAuthStatus } from '../../auth'

type Phase = 'checking' | 'login' | 'unconfigured' | 'app'

/** Checks /api/auth/status before rendering the app; shows the login screen
    for remote visitors without a session (local visitors never see it). */
export function AuthGate() {
  const [phase, setPhase] = useState<Phase>('checking')
  // a session that ends while the app runs: sign in over it, keeping unsaved state
  const [expired, setExpired] = useState(false)

  const check = useCallback(() => {
    fetchAuthStatus()
      .then((s) => setPhase(s.local || s.authenticated ? 'app' : s.configured ? 'login' : 'unconfigured'))
      .catch(() => setPhase('app'))   // status unreadable (server down/older backend): the app shows its own errors
  }, [])

  useEffect(() => { check() }, [check])

  useEffect(() => {
    const onAuthRequired = () => setExpired(true)
    window.addEventListener(AUTH_REQUIRED_EVENT, onAuthRequired)
    return () => window.removeEventListener(AUTH_REQUIRED_EVENT, onAuthRequired)
  }, [])

  if (phase === 'checking') return null
  if (phase !== 'app') {
    return <LoginScreen unconfigured={phase === 'unconfigured'}
                        onSuccess={() => { setExpired(false); setPhase('app') }} />
  }
  return (
    <>
      <App />
      {expired && <LoginScreen overlay onSuccess={() => setExpired(false)} />}
    </>
  )
}
