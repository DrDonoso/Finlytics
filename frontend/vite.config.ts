import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// npm sets npm_package_version when running via `npm run ...`
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const appVersion: string = (globalThis as any).process?.env?.npm_package_version ?? '0.1.0'

export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(appVersion),
  },
  build: {
    outDir: 'dist',
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:7777',
        changeOrigin: true,
      },
    },
  },
})
