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

/** Thrown when the browser refuses to register a Service Worker. In practice
 *  this always means the demo is being served over plain HTTP from something
 *  other than localhost — browsers only allow Service Workers in a secure
 *  context, and without one the demo has no API layer at all. */
export class InsecureContextError extends Error {
  constructor() {
    super(
      'The demo needs a Service Worker, which browsers only allow over HTTPS ' +
      '(or on localhost). Serve this build behind TLS.',
    )
    this.name = 'InsecureContextError'
  }
}

export async function startDemoWorker(): Promise<void> {
  if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) {
    throw new InsecureContextError()
  }

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
