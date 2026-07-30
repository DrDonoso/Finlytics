import { rm } from 'node:fs/promises'
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

export default defineConfig(({ mode }) => {
  const isDemo = mode === 'demo'
  // Keeping outDir here (rather than --outDir on the CLI) means the demo build
  // can never overwrite the production bundle.
  const outDir = isDemo ? 'dist-demo' : 'dist'

  return {
    plugins: [
      react(),
      ...(isDemo ? [] : [excludeMswWorker(outDir)]),
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
  }
})
