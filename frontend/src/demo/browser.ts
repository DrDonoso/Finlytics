/** Mock Service Worker bootstrap for the demo build.
 *
 * The worker MUST be running before React mounts: `AuthProvider` fires
 * `/api/auth/status` from its first effect, and a request that escapes the
 * worker would hit the static host and come back as `index.html`.
 * See `main.tsx`, which awaits `startDemoWorker()` before `createRoot().render()`.
 */

import { setupWorker } from 'msw/browser'
import { handlers } from './handlers'

export const worker = setupWorker(...handlers)

export async function startDemoWorker(): Promise<void> {
  await worker.start({
    serviceWorker: { url: '/mockServiceWorker.js' },
    quiet: true,
    onUnhandledRequest(request, print) {
      // Static assets (JS chunks, images, fonts) must pass through untouched.
      // Any /api call reaching this point escaped the catch-all in handlers.ts,
      // which would be a bug — make it loud.
      if (new URL(request.url).pathname.startsWith('/api/')) print.error()
    },
  })
}
