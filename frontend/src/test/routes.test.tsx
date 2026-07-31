/**
 * Route smoke tests.
 *
 * Verifies that each screen mounts and renders something without throwing.
 * Covers what was previously checked by hand in the browser — exactly the kind
 * of verification that gets skipped when there is a deadline.
 *
 * This does not validate screen content (each page has its own tests); it checks
 * that the component tree, providers, and queries fit together. A React render
 * failure leaves the page blank with no message, so this test exists primarily
 * to prevent that reaching production.
 */
import { QueryClientProvider } from '@tanstack/react-query'
import { render, waitFor } from '@testing-library/react'
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
import AssistantSettingsPage from '../pages/AssistantSettingsPage'
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

// ── API doubles ──────────────────────────────────────────────────────────────
// Return empty but correctly shaped responses: the goal is that the tree
// mounts, not that data is exercised.
//
// Constants are defined inside the factory because vi.mock is hoisted to the
// top of the file and cannot read variables declared outside.

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
    // The assistant reports itself disabled here, so Layout mounts the launcher
    // and the launcher correctly renders nothing — which is the path a route
    // smoke test should exercise, not a live chat panel.
    getAssistantStatus: empty({ enabled: false, reason: 'LLM not configured' }),
    getAssistantSuggestions: empty({ suggestions: [] }),
    getAssistantConversations: empty([]),
    getAssistantConversation: empty({ id: 1, title: '', created_at: '', updated_at: '', messages: [] }),
    getAssistantSettings: empty({
      custom_instructions: null, rate_limit_messages: null,
      rate_limit_window_seconds: null, monthly_token_budget: null,
      effective_rate_limit_messages: 30, effective_rate_limit_window_seconds: 3600,
      max_custom_instructions_chars: 2000,
    }),
    getAssistantUsage: empty({
      this_month: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, messages: 0 },
      all_time: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, messages: 0 },
      by_day: [], monthly_token_budget: null, budget_remaining: null, usage_available: true,
    }),
    putAssistantSettings: vi.fn(),
    createAssistantConversation: vi.fn(),
    deleteAssistantConversation: vi.fn(),
    streamAssistantMessage: vi.fn(),
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

/** Routes as declared in App.tsx. */
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
  ['/settings/assistant', <AssistantSettingsPage key="sasi" />],
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
  // React logs many issues via console.error that don't throw; capture them so they aren't silently swallowed.
  console.error = (...args: unknown[]) => {
    errors.push(args.map(a => String(a)).join(' '))
  }
})

afterEach(() => {
  console.error = consoleError
})

describe('all routes mount', () => {
  it.each(ROUTES)('%s', async (path, element) => {
    const { container } = renderRoute(path, element)

    await waitFor(() => {
      expect(container.querySelector('.app-shell')).not.toBeNull()
    })

    // Discard act() warnings: they are test infrastructure noise, not app bugs.
    const real = errors.filter(e => !e.includes('not wrapped in act'))
    expect(real).toEqual([])
  })
})

describe('the sidebar navigation renders completely', () => {
  it('links to the main sections', async () => {
    const { container } = renderRoute('/', <Dashboard />)

    await waitFor(() => {
      expect(container.querySelector('.sidebar-nav')).not.toBeNull()
    })

    // Check structure rather than labels: the app starts in the browser's locale,
    // so visible text depends on the environment running the tests.
    const nav = container.querySelector('.sidebar-nav') as HTMLElement

    // The home link is the only top-level anchor; the rest are buttons that expand their section, so their links don't exist until opened.
    const hrefs = [...nav.querySelectorAll('a')].map(a => a.getAttribute('href'))
    expect(hrefs).toContain('/')

    // Finances, Investments, and Settings.
    expect(nav.querySelectorAll('.sidebar-section-btn').length).toBeGreaterThanOrEqual(3)

    // Each entry uses an icon from the custom set, not an emoji.
    expect(nav.querySelectorAll('svg.icon').length).toBeGreaterThanOrEqual(4)
  })
})
