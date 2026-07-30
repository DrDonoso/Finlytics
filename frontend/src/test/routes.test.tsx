/**
 * Prueba de humo de las rutas.
 *
 * Comprueba que cada pantalla monta y pinta algo sin lanzar. Cubre lo que hasta
 * ahora se verificaba a mano abriendo la aplicación en el navegador, que es
 * justo el tipo de comprobación que se deja de hacer en cuanto hay prisa.
 *
 * No valida el contenido de cada pantalla —para eso están sus propios tests—,
 * sino que el árbol de componentes, los proveedores y las consultas encajan. Un
 * fallo de render en React deja la página en blanco sin mensaje, así que este
 * test existe sobre todo para que eso no llegue a producción.
 */
import { QueryClientProvider } from '@tanstack/react-query'
import { render, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createQueryClient } from '../api/queryClient'
import Layout from '../components/Layout'
import SettingsLayout from '../components/SettingsLayout'
import { LanguageProvider } from '../i18n'
import { ThemeProvider } from '../contexts/ThemeContext'

import AboutPage from '../pages/AboutPage'
import AccountsPage from '../pages/AccountsPage'
import AnalyticsPage from '../pages/AnalyticsPage'
import AppearancePage from '../pages/AppearancePage'
import BackupPage from '../pages/BackupPage'
import CategoriesPage from '../pages/CategoriesPage'
import ConnectorsPage from '../pages/ConnectorsPage'
import Dashboard from '../pages/Dashboard'
import FinancesOverviewPage from '../pages/FinancesOverviewPage'
import InvestmentsLandingPage from '../pages/InvestmentsLandingPage'
import RulesPage from '../pages/RulesPage'
import SettingsPage from '../pages/SettingsPage'
import StatementsPage from '../pages/StatementsPage'
import TransactionsPage from '../pages/TransactionsPage'

// ── Dobles de la capa de API ─────────────────────────────────────────────────
// Se devuelven respuestas vacías pero con la forma correcta: interesa que el
// árbol monte, no ejercitar los datos.
//
// Las constantes van dentro de la factoría porque vi.mock se eleva al principio
// del fichero y no puede leer variables declaradas fuera.

vi.mock('../api/client', () => {
  const EMPTY_OVERVIEW = {
    total_expense: 0, total_income: 0, net: 0,
    num_transactions: 0, top_category: null, currency: 'EUR',
  }
  const empty = <T,>(v: T) => vi.fn().mockResolvedValue(v)
  return {
    formatEur: (n: number) => `${n} €`,
    getAccounts: empty([]),
    getCategories: empty([]),
    getTags: empty([]),
    getRules: empty([]),
    getTransactions: empty({ items: [], total: 0, limit: 50, offset: 0 }),
    getOverview: empty(EMPTY_OVERVIEW),
    getOverviewMonths: empty({ months: [], latest: null }),
    getByCategory: empty([]),
    getByAccount: empty([]),
    getByMerchant: empty([]),
    getByMonth: empty([]),
    getByDay: empty([]),
    getCashflow: empty({ income: [], expense: [], total_income: 0, total_expense: 0, currency: 'EUR' }),
    getCombinedOverview: empty({
      total_value_eur: 0, total_invested_eur: 0,
      total_gain_loss_eur: 0, total_gain_loss_pct: 0,
      providers: [], by_provider: [], by_asset_class: [],
    }),
    getConnections: empty([]),
    getInvestmentPlugins: empty([]),
    getInvestmentPortfolio: empty(null),
    getStatementMonths: empty([]),
    getStatementReminder: empty({ year: null, month: null, missing_account_ids: [] }),
    getStatementOriginals: empty([]),
    getAppVersion: empty({ version: '0.1.0', commit: null, built_at: null }),
    getNotifications: empty([]),
    getUnreadCount: empty({ count: 0 }),
    getNotificationChannels: empty([]),
    getBackupPreview: empty(null),
    updateTransaction: vi.fn(),
    createAccount: vi.fn(),
    deleteAccount: vi.fn(),
    updateCategory: vi.fn(),
    createTag: vi.fn(),
    updateTag: vi.fn(),
    deleteTag: vi.fn(),
    markNotificationRead: vi.fn(),
    markAllNotificationsRead: vi.fn(),
    dismissNotification: vi.fn(),
    registerOn401Handler: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    getMe: vi.fn(),
    getAuthStatus: vi.fn(),
    setupUser: vi.fn(),
  }
})

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    loading: false, initialized: true, authenticated: true, username: 'demo',
    onSetupSuccess: vi.fn(), onLoginSuccess: vi.fn(), onLogout: vi.fn(),
  }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}))

/** Rutas tal y como las declara App.tsx. */
const ROUTES: [string, React.ReactNode][] = [
  ['/', <Dashboard key="d" />],
  ['/finances', <FinancesOverviewPage key="f" />],
  ['/transactions', <TransactionsPage key="t" />],
  ['/analytics', <AnalyticsPage key="a" />],
  ['/statements', <StatementsPage key="s" />],
  ['/investments', <InvestmentsLandingPage key="i" />],
  ['/settings/accounts', <AccountsPage key="sa" />],
  ['/settings/tags', <SettingsPage key="st" />],
  ['/settings/categories', <CategoriesPage key="sc" />],
  ['/settings/rules', <RulesPage key="sr" />],
  ['/settings/appearance', <AppearancePage key="sap" />],
  ['/settings/connectors', <ConnectorsPage key="scon" />],
  ['/settings/backup', <BackupPage key="sb" />],
  ['/settings/about', <AboutPage key="sab" />],
]

function renderRoute(path: string, element: React.ReactNode) {
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

let errors: string[] = []
let consoleError: typeof console.error

beforeEach(() => {
  errors = []
  consoleError = console.error
  // React avisa por consola de bastantes problemas que no llegan a lanzar;
  // se capturan para que no pasen desapercibidos.
  console.error = (...args: unknown[]) => {
    errors.push(args.map(a => String(a)).join(' '))
  }
})

afterEach(() => {
  console.error = consoleError
})

describe('todas las rutas montan', () => {
  it.each(ROUTES)('%s', async (path, element) => {
    const { container } = renderRoute(path, element)

    await waitFor(() => {
      expect(container.querySelector('.app-shell')).not.toBeNull()
    })

    // Se descartan los avisos de act(), que son ruido de las pruebas y no de la
    // aplicación.
    const real = errors.filter(e => !e.includes('not wrapped in act'))
    expect(real).toEqual([])
  })
})

describe('la navegación lateral se pinta entera', () => {
  it('muestra las secciones principales', async () => {
    const { container } = renderRoute('/', <Dashboard />)

    await waitFor(() => {
      expect(container.querySelector('.sidebar-nav')).not.toBeNull()
    })

    // Se busca dentro de la barra lateral: varias etiquetas se repiten en el
    // contenido de la página y una búsqueda global encontraría más de una.
    const nav = container.querySelector('.sidebar-nav') as HTMLElement
    for (const label of ['Inicio', 'Finanzas', 'Inversiones', 'Ajustes']) {
      expect(within(nav).getByText(label)).toBeInTheDocument()
    }
  })
})
