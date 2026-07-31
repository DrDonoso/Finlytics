/**
 * Demo smoke test, run against the demo's own MSW interceptors.
 *
 * The demo replaces the API with MSW handlers, so a screen can fail to show
 * data for two independent reasons: a render error, or a request to an endpoint
 * the demo doesn't serve. The second case doesn't throw — the catch-all returns
 * 501 — and is invisible unless you open each screen by hand.
 *
 * This test mounts every demo-exposed route against the real handlers and
 * asserts that none of them issues an uncovered request.
 */
import { QueryClientProvider } from '@tanstack/react-query'
import { render, waitFor } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import { createQueryClient } from '../api/queryClient'
import Layout from '../components/Layout'
import SettingsLayout from '../components/SettingsLayout'
import { ThemeProvider } from '../contexts/ThemeContext'
import { handlers } from '../demo/handlers'
import { LanguageProvider } from '../i18n'

import AboutPage from '../pages/AboutPage'
import AnalyticsPage from '../pages/AnalyticsPage'
import AppearancePage from '../pages/AppearancePage'
import Dashboard from '../pages/Dashboard'
import FinancesOverviewPage from '../pages/FinancesOverviewPage'
import InvestmentsLandingPage from '../pages/InvestmentsLandingPage'
import TransactionsPage from '../pages/TransactionsPage'

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    loading: false, initialized: true, authenticated: true, username: 'demo',
    onSetupSuccess: vi.fn(), onLoginSuccess: vi.fn(), onLogout: vi.fn(),
  }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}))

const server = setupServer(...handlers)

/** Requests the demo's catch-all has had to reject (HTTP 501). */
let unhandled: string[] = []

beforeAll(() => {
  // 'bypass' rather than 'error': the demo catch-all already returns 501, and we want to measure exactly how often it is reached.
  server.listen({ onUnhandledRequest: 'bypass' })
})

afterAll(() => server.close())

beforeEach(() => {
  unhandled = []
  server.events.on('response:mocked', ({ response, request }) => {
    if (response.status === 501) unhandled.push(new URL(request.url).pathname)
  })
})

afterEach(() => {
  server.resetHandlers()
  server.events.removeAllListeners()
})

/** Routes exposed by DemoRoutes in App.tsx. */
const DEMO_ROUTES: [string, React.ReactNode][] = [
  ['/', <Dashboard key="d" />],
  ['/finances', <FinancesOverviewPage key="f" />],
  ['/transactions', <TransactionsPage key="t" />],
  ['/analytics', <AnalyticsPage key="a" />],
  ['/investments', <InvestmentsLandingPage key="i" />],
  ['/settings/appearance', <AppearancePage key="sa" />],
  ['/settings/about', <AboutPage key="sab" />],
]

function renderDemoRoute(path: string, element: React.ReactNode) {
  const client = createQueryClient()
  return render(
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <LanguageProvider>
          <MemoryRouter initialEntries={[path]}>
            <Routes>
              <Route path="/" element={<Layout />}>
                <Route path={path === '/' ? '/' : path.slice(1)} element={element} />
                {path.startsWith('/settings') && (
                  <Route path="settings" element={<SettingsLayout />} />
                )}
              </Route>
            </Routes>
          </MemoryRouter>
        </LanguageProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  )
}

describe('the demo covers everything its screens request', () => {
  it.each(DEMO_ROUTES)('%s', async (path, element) => {
    const { container } = renderDemoRoute(path, element)

    await waitFor(() => {
      expect(container.querySelector('.app-shell')).not.toBeNull()
    })
    // Allow time for queries triggered on mount to settle.
    await new Promise(r => setTimeout(r, 250))

    expect(unhandled).toEqual([])
  })
})

describe('demo data reaches the screen', () => {
  it('the dashboard shows a net worth value, not a dash', async () => {
    const { container } = renderDemoRoute('/', <Dashboard />)

    await waitFor(
      () => {
        const hero = container.querySelector('.dashboard-kpi-hero .inv-kpi-card__value')
        expect(hero?.textContent).toMatch(/\d/)
      },
      { timeout: 3000 },
    )
  })

  it('the accounts table populates', async () => {
    const { container } = renderDemoRoute('/', <Dashboard />)

    await waitFor(
      () => {
        const rows = container.querySelectorAll('.dashboard-accounts-table tbody tr')
        expect(rows.length).toBeGreaterThan(0)
      },
      { timeout: 3000 },
    )
  })
})
