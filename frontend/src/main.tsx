import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'
import { LanguageProvider } from './i18n'
import { ThemeProvider } from './contexts/ThemeContext'

function render() {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <ThemeProvider>
        <LanguageProvider>
          <App />
        </LanguageProvider>
      </ThemeProvider>
    </StrictMode>,
  )
}

// In demo builds the mock worker must be intercepting before React mounts:
// AuthProvider requests /api/auth/status from its very first effect.
// The literal `import.meta.env` check (rather than the IS_DEMO re-export) is
// what lets the bundler drop this branch — and all of MSW — from prod builds.
if (import.meta.env.VITE_DEMO === '1') {
  void import('./demo/browser')
    .then(({ startDemoWorker }) => startDemoWorker())
    .then(render)
} else {
  render()
}
