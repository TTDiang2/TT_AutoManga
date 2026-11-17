import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { AuthGate } from './components/auth/AuthGate'
import { installFetchGuard, rememberLanguage } from './auth'
import { useProjectStore } from './store/projectStore'
import './styles/globals.css'

// before anything fetches: a 401 from /api shows the login screen
installFetchGuard()

// the login screen renders before /api/settings is readable: keep the app's language for it
useProjectStore.subscribe((s) => { if (s.settings.language) rememberLanguage(s.settings.language) })

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuthGate />
  </StrictMode>,
)
