/**
 * Prueba de humo de la demo, contra sus propios interceptores.
 *
 * La demo sustituye la API por handlers de MSW, así que una pantalla puede
 * quedarse sin datos por dos motivos distintos: porque falle el render o porque
 * pida un endpoint que la demo no sirve. Lo segundo no rompe nada visible —el
 * catch-all responde 501— y sólo se nota abriendo cada pantalla a mano.
 *
 * Este test monta las rutas que la demo expone contra los handlers reales y
 * comprueba que ninguna acaba pidiendo algo no cubierto.
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

/** Peticiones que el catch-all de la demo ha tenido que rechazar. */
let unhandled: string[] = []

beforeAll(() => {
  // `bypass` en lugar de `error`: el catch-all de la demo ya devuelve 501, y lo
  // que interesa medir es precisamente cuántas veces se llega hasta él.
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

/** Rutas que expone DemoRoutes en App.tsx. */
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

describe('la demo cubre todo lo que sus pantallas piden', () => {
  it.each(DEMO_ROUTES)('%s', async (path, element) => {
    const { container } = renderDemoRoute(path, element)

    await waitFor(() => {
      expect(container.querySelector('.app-shell')).not.toBeNull()
    })
    // Margen para que se resuelvan las consultas que arrancan al montar.
    await new Promise(r => setTimeout(r, 250))

    expect(unhandled).toEqual([])
  })
})

describe('los datos de la demo llegan a la pantalla', () => {
  it('el Inicio muestra un patrimonio y no un guion', async () => {
    const { container } = renderDemoRoute('/', <Dashboard />)

    await waitFor(
      () => {
        const hero = container.querySelector('.dashboard-kpi-hero .inv-kpi-card__value')
        expect(hero?.textContent).toMatch(/\d/)
      },
      { timeout: 3000 },
    )
  })

  it('la tabla de cuentas se rellena', async () => {
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
