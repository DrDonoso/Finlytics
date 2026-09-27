import { defineConfig, devices } from '@playwright/test'

const PORT = 4173

/** Smoke tests against the demo build: the same bundle that ships, served
 *  statically, with MSW answering /api/* from the synthetic dataset. It needs
 *  no API and no database, so it runs anywhere Chromium does. */
export default defineConfig({
  testDir: './e2e',
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: `http://localhost:${PORT}`,
    locale: 'en-US',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: `npm run build:demo && npm run preview:demo -- --port ${PORT} --strictPort`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
})
