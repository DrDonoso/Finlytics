/// <reference types="vitest/config" />
import { rm, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

// npm sets npm_package_version when running via `npm run ...`
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const appVersion: string = (globalThis as any).process?.env?.npm_package_version ?? '0.1.0'

/** `public/mockServiceWorker.js` is MSW's worker script. Vite copies everything
 *  in public/ verbatim, so without this it also lands in the PRODUCTION bundle,
 *  publishing an unused service worker at the app's root. Nothing registers it
 *  there, but a request interceptor is not something a finance app should ship
 *  by accident — drop it from every build except the demo. */
function excludeMswWorker(outDir: string): Plugin {
  return {
    name: 'finlytics:exclude-msw-worker',
    apply: 'build',
    async closeBundle() {
      await rm(resolve(outDir, 'mockServiceWorker.js'), { force: true })
    },
  }
}

/** Static-host config for the demo build, in the `_redirects` / `_headers`
 *  format Cloudflare Pages and Netlify read. These do for a CDN what
 *  `nginx.demo.conf` does for the self-hosted image; both deployment paths ship
 *  from the same `dist-demo/`, so they have to agree.
 *
 *  Emitted from here rather than committed under `public/` because everything in
 *  `public/` is copied into the PRODUCTION bundle too, where FastAPI serves the
 *  SPA and these files would be dead weight. */
/** Static-host config for the demo build, in the `_headers` format Cloudflare
 *  reads. This does for a CDN what `nginx.demo.conf` does for the self-hosted
 *  image; both deployment paths ship from the same `dist-demo/`, so they have to
 *  agree.
 *
 *  There is deliberately NO `_redirects` file. The obvious SPA rule
 *  (`/*  /index.html  200`) is *rejected* by Cloudflare at deploy time:
 *
 *      Invalid _redirects configuration:
 *      Line 1: Infinite loop detected in this rule. This would cause a redirect
 *      to strip `.html` or `/index` and end up triggering this rule again.
 *
 *  Cloudflare normalises `/index.html` to `/`, which matches `/*` again. The
 *  fallback belongs in `wrangler.jsonc` instead, as
 *  `assets.not_found_handling: "single-page-application"` — which is also
 *  stricter, since a missing ASSET still returns a real 404 rather than HTML.
 *
 *  Emitted from here rather than committed under `public/` because everything in
 *  `public/` is copied into the PRODUCTION bundle too, where FastAPI serves the
 *  SPA and this file would be dead weight. */
function emitStaticHostConfig(outDir: string): Plugin {
  // mockServiceWorker.js IS the demo's API layer; a stale copy breaks every
  // screen. Browsers already revalidate service-worker scripts on their own
  // (updateViaCache defaults to 'imports'), so this is belt-and-braces.
  // /assets/* is content-hashed by Vite and therefore safe to cache forever.
  const headers = [
    '/mockServiceWorker.js',
    '  Cache-Control: no-cache',
    '  Service-Worker-Allowed: /',
    '',
    '/assets/*',
    '  Cache-Control: public, max-age=31536000, immutable',
    '',
    '/*',
    '  X-Content-Type-Options: nosniff',
    '  X-Frame-Options: SAMEORIGIN',
    '  Referrer-Policy: strict-origin-when-cross-origin',
    '',
  ].join('\n')

  return {
    name: 'finlytics:emit-static-host-config',
    apply: 'build',
    async closeBundle() {
      await writeFile(resolve(outDir, '_headers'), headers, 'utf8')
    },
  }
}

export default defineConfig(({ mode }) => {
  const isDemo = mode === 'demo'
  // Keeping outDir here (rather than --outDir on the CLI) means the demo build
  // can never overwrite the production bundle.
  const outDir = isDemo ? 'dist-demo' : 'dist'

  return {
    plugins: [
      react(),
      ...(isDemo ? [emitStaticHostConfig(outDir)] : [excludeMswWorker(outDir)]),
    ],
    define: {
      __APP_VERSION__: JSON.stringify(appVersion),
    },
    build: {
      outDir,
    },
    server: {
      proxy: {
        '/api': {
          target: 'http://localhost:7777',
          changeOrigin: true,
        },
      },
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.ts'],
      include: ['src/**/*.{test,spec}.{ts,tsx}'],
      coverage: {
        provider: 'v8',
        include: ['src/**/*.{ts,tsx}'],
        exclude: [
          'src/**/*.{test,spec}.{ts,tsx}',
          'src/test/**',
          'src/api/mock.ts',
          // The demo is an API double: measuring its coverage adds no signal.
          'src/demo/**',
        ],
      },
    },
  }
})
