/**
 * Dashboard tests focused on partial degradation.
 *
 * A fetch failure for investments used to leave total net worth as "—", hiding
 * even the bank-account net that was already available. These tests lock in that
 * a failure in one data source never suppresses another that is working — a
 * regression that only surfaces when something goes wrong and therefore easily
 * slips back unnoticed.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import Dashboard from './Dashboard'
import { createQueryClient } from '../api/queryClient'
import type { AccountSummary, CombinedOverview, Overview } from '../api/types'

// ── API layer doubles ────────────────────────────────────────────────────────

const getAccounts = vi.fn()
const getOverview = vi.fn()
const getOverviewMonths = vi.fn()
const getByAccount = vi.fn()
const getCombinedOverview = vi.fn()
const getStatementReminder = vi.fn()
const getMortgageNetWorth = vi.fn()

vi.mock('../api/client', () => ({
  getAccounts: (...a: unknown[]) => getAccounts(...a),
  getOverview: (...a: unknown[]) => getOverview(...a),
  getOverviewMonths: (...a: unknown[]) => getOverviewMonths(...a),
  getByAccount: (...a: unknown[]) => getByAccount(...a),
  getCombinedOverview: (...a: unknown[]) => getCombinedOverview(...a),
  getStatementReminder: (...a: unknown[]) => getStatementReminder(...a),
  getMortgageNetWorth: (...a: unknown[]) => getMortgageNetWorth(...a),
}))

// The investments card has its own load; stub it out here.
vi.mock('../components/InvestmentSnapshotCard', () => ({
  default: () => null,
}))

// Same for the mortgage card: it runs its own queries and is covered elsewhere.
vi.mock('../components/MortgageSnapshotCard', () => ({
  default: () => null,
}))

vi.mock('../contexts/NotificationsContext', () => ({
  useNotifications: () => ({ notifications: [] }),
}))

const ACCOUNTS = [
  { id: 1, name: 'BBVA', type: 'bank', currency: 'EUR', tx_count: 40, account_number_masked: '**** 4821' },
  { id: 2, name: 'Santander', type: 'bank', currency: 'EUR', tx_count: 12, account_number_masked: '**** 9032' },
]

const BY_ACCOUNT: AccountSummary[] = [
  { account: 'BBVA', expense: 1840.55, income: 5000, net: 12430.2, currency: 'EUR' },
  { account: 'Santander', expense: 210.4, income: 29110, net: 28900, currency: 'EUR' },
]

const OVERVIEW: Overview = {
  total_expense: 2050,
  total_income: 5000,
  net: 2950,
  num_transactions: 41,
  top_category: null,
  currency: 'EUR',
}

const COMBINED: CombinedOverview = {
  total_value_eur: 29670.9,
  total_invested_eur: 27000,
  total_gain_loss_eur: 2670.9,
  total_gain_loss_pct: 9.89,
  providers: [],
  by_provider: [],
  by_asset_class: [],
} as unknown as CombinedOverview

function renderDashboard() {
  // Fresh client per render to isolate the cache between tests. No retries:
  // degradation tests reject with TypeError, and the default retry would
  // exhaust waitFor before the query reaches its error state.
  const client = createQueryClient()
  client.setDefaultOptions({
    queries: { ...client.getDefaultOptions().queries, retry: false },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** Text of the net-worth hero block, with whitespace normalized. */
function heroText(): string {
  const hero = document.querySelector('.dashboard-kpi-hero')
  return (hero?.textContent ?? '').replace(/\s+/g, ' ')
}

beforeEach(() => {
  vi.clearAllMocks()
  getAccounts.mockResolvedValue(ACCOUNTS)
  getByAccount.mockResolvedValue(BY_ACCOUNT)
  getOverview.mockResolvedValue(OVERVIEW)
  getOverviewMonths.mockResolvedValue({ months: ['2026-05', '2026-06'], latest: '2026-06' })
  getCombinedOverview.mockResolvedValue(COMBINED)
  getStatementReminder.mockResolvedValue({ year: null, month: null, missing_account_ids: [] })
  // No mortgage configured: the KPI must stay exactly as it was before the module.
  getMortgageNetWorth.mockResolvedValue({
    outstanding_debt: 0, property_value: 0, net_contribution: 0, count: 0,
  })
})

// ── Happy path ────────────────────────────────────────────────────────────────

describe('Dashboard with all sources available', () => {
  it('adds accounts and investments into net worth', async () => {
    renderDashboard()

    // 12.430,20 + 28.900,00 + 29.670,90
    await waitFor(() => expect(heroText()).toContain('71.001,10'))
  })

  it('breaks down net worth into accounts and investments', async () => {
    renderDashboard()

    await waitFor(() => expect(heroText()).toContain('71.001,10'))
    expect(heroText()).toContain('41.330,20')
    expect(heroText()).toContain('29.670,90')
  })

  it('does not warn about incomplete data when there is none', async () => {
    renderDashboard()

    await waitFor(() => expect(heroText()).toContain('71.001,10'))
    expect(document.querySelector('.dashboard-kpi-hero__notice')).toBeNull()
  })
})

// ── Partial degradation ────────────────────────────────────────────────────────

describe('Dashboard with the investments connector down', () => {
  beforeEach(() => {
    getCombinedOverview.mockRejectedValue(new TypeError('Failed to fetch'))
  })

  it('still shows net worth from what could be read', async () => {
    renderDashboard()

    // Accounts only: 12,430.20 + 28,900.00. This used to show "—".
    await waitFor(() => expect(heroText()).toContain('41.330,20'))
  })

  it('marks investments as unavailable rather than counting them as zero', async () => {
    renderDashboard()

    await waitFor(() => expect(heroText()).toContain('41.330,20'))
    const missing = document.querySelector('.dashboard-kpi-breakdown__missing')
    expect(missing).not.toBeNull()
    expect(missing?.textContent).toBeTruthy()
  })

  it('warns that the figure excludes investments', async () => {
    renderDashboard()

    await waitFor(() => expect(heroText()).toContain('41.330,20'))
    expect(document.querySelector('.dashboard-kpi-hero__notice')).not.toBeNull()
  })

  it('does not silently add zero to net worth', async () => {
    renderDashboard()

    await waitFor(() => expect(heroText()).toContain('41.330,20'))
    // If investments were counted as 0 the total would be the same but without
    // a warning — the user would believe that is their complete net worth.
    expect(document.querySelector('.dashboard-kpi-hero__notice')).not.toBeNull()
  })

  it('keeps the accounts table usable', async () => {
    renderDashboard()

    await waitFor(() => expect(heroText()).toContain('41.330,20'))
    const table = document.querySelector('.dashboard-accounts-table')
    expect(table).not.toBeNull()
    expect(within(table as HTMLElement).getByText('BBVA')).toBeInTheDocument()
    expect(within(table as HTMLElement).getByText('Santander')).toBeInTheDocument()
  })
})

// ── Primary source failure ────────────────────────────────────────────────────

describe('Dashboard when accounts cannot be read', () => {
  it('leaves net worth blank because its main component is missing', async () => {
    getByAccount.mockRejectedValue(new TypeError('Failed to fetch'))

    renderDashboard()

    await waitFor(() => expect(heroText()).toContain('—'))
    // Without accounts there is no breakdown to show.
    expect(document.querySelector('.dashboard-kpi-breakdown')).toBeNull()
  })

  it('reports the failure in the accounts card', async () => {
    getByAccount.mockRejectedValue(new TypeError('Failed to fetch'))

    renderDashboard()

    await waitFor(() => {
      expect(document.querySelector('.dashboard-accounts-card .state-box.error')).not.toBeNull()
    })
  })
})

// ── Savings rate ──────────────────────────────────────────────────────────────

describe('Savings-rate change indicator', () => {
  it('is not shown when there is only one month of data', async () => {
    // With a single month there is nothing to compare against; fabricating a
    // baseline would be worse than showing nothing.
    getOverviewMonths.mockResolvedValue({ months: ['2026-06'], latest: '2026-06' })

    renderDashboard()

    await waitFor(() => expect(heroText()).toContain('71.001,10'))
    expect(screen.queryByText(/pp/)).toBeNull()
  })

  it('compares the two most recent months with data', async () => {
    renderDashboard()

    await waitFor(() => expect(getOverview).toHaveBeenCalled())
    // One unfiltered call for the historical baseline and one per month compared.
    await waitFor(() => {
      const ranges = getOverview.mock.calls
        .map(c => c[0])
        .filter(Boolean) as { from: string; to: string }[]
      expect(ranges).toContainEqual({ from: '2026-06-01', to: '2026-06-30' })
      expect(ranges).toContainEqual({ from: '2026-05-01', to: '2026-05-31' })
    })
  })
})
