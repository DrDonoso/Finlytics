import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import App from './App'
import { LanguageProvider } from './i18n'
import { ThemeProvider } from './contexts/ThemeContext'
import { queryClient } from './api/queryClient'

function render() {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <LanguageProvider>
            <App />
          </LanguageProvider>
        </ThemeProvider>
      </QueryClientProvider>
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
    .catch((err: unknown) => {
      // Mounting React here would just render an app whose every request fails.
      // Say what is actually wrong instead — this is almost always a demo
      // served over plain HTTP, where Service Workers are not allowed.
      console.error('[demo] Failed to start the mock service worker:', err)
      const root = document.getElementById('root')
      if (root) {
        root.textContent = ''
        const box = document.createElement('div')
        box.style.cssText =
          'max-width:34rem;margin:15vh auto;padding:1.5rem;font:14px/1.55 system-ui,sans-serif;' +
          'border:1px solid #e2e8f0;border-radius:12px;color:#1e293b;background:#fff'
        const title = document.createElement('strong')
        title.textContent = 'No se pudo iniciar la demo / Could not start the demo'
        const body = document.createElement('p')
        body.style.marginBottom = '0'
        body.textContent =
          'La demo necesita un Service Worker, que los navegadores solo permiten ' +
          'sobre HTTPS (o en localhost). Sírvela detrás de TLS. — The demo needs a ' +
          'Service Worker, which browsers only allow over HTTPS (or on localhost).'
        box.append(title, body)
        root.append(box)
      }
    })
} else {
  render()
}
