/**
 * The statements page lands on the newest month whenever the list of months
 * changes (an import or a delete), but not when a refetch returns the same
 * months: that would throw away the month the visitor had navigated to.
 */
import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import StatementsPage from './StatementsPage'
import { createQueryClient } from '../api/queryClient'
import type { StatementMonth } from '../api/types'
import { langLocale } from '../i18n'
import es from '../i18n/es'

const client = vi.hoisted(() => ({
  getAccounts: vi.fn(),
  getCategories: vi.fn(),
  getTags: vi.fn(),
  getStatementMonths: vi.fn(),
  getStatementOriginals: vi.fn(),
  getOverview: vi.fn(),
  getByCategory: vi.fn(),
  getTransactions: vi.fn(),
}))

vi.mock('../api/client', async importOriginal => ({
  ...(await importOriginal<typeof import('../api/client')>()),
  ...client,
}))

const MAY_AND_APRIL: StatementMonth[] = [
  { year: 2024, month: 5, count: 3 },
  { year: 2024, month: 4, count: 2 },
]

/** Every fetch answers fresh objects, as a real response would. */
function serveMonths(list: StatementMonth[]) {
  client.getStatementMonths.mockImplementation(async () => list.map(m => ({ ...m })))
}

function monthTrigger(year: number, month: number) {
  const label = new Intl.DateTimeFormat(langLocale('es'), { month: 'long', year: 'numeric' })
    .format(new Date(year, month - 1, 1))
  return { name: es.monthPickerTriggerLabel(label) }
}

function renderPage(): QueryClient {
  const queryClient = createQueryClient()
  queryClient.setDefaultOptions({
    queries: { ...queryClient.getDefaultOptions().queries, retry: false },
  })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <StatementsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return queryClient
}

/** react-query hands a refetch's result to its observers on a timer. */
async function flushNotifications() {
  await act(() => new Promise(resolve => setTimeout(resolve, 0)))
}

beforeEach(() => {
  for (const mock of Object.values(client)) mock.mockReset()
  client.getAccounts.mockResolvedValue([])
  client.getCategories.mockResolvedValue([])
  client.getTags.mockResolvedValue([])
  client.getStatementOriginals.mockResolvedValue([])
  client.getByCategory.mockResolvedValue([])
  client.getOverview.mockResolvedValue({
    total_expense: 0, total_income: 0, net: 0, num_transactions: 3, top_category: null, currency: 'EUR',
  })
  client.getTransactions.mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 })
})

describe('StatementsPage month selection', () => {
  it('lands on the newest month with statements', async () => {
    serveMonths(MAY_AND_APRIL)
    renderPage()

    expect(await screen.findByRole('button', monthTrigger(2024, 5))).toBeInTheDocument()
    expect(client.getStatementOriginals).toHaveBeenCalledWith(2024, 5, undefined)
  })

  it('lands on a month that a new import adds', async () => {
    serveMonths(MAY_AND_APRIL)
    const queryClient = renderPage()
    fireEvent.click(await screen.findByRole('button', { name: es.stmtsPrev }))
    expect(screen.getByRole('button', monthTrigger(2024, 4))).toBeInTheDocument()

    serveMonths([{ year: 2024, month: 6, count: 1 }, ...MAY_AND_APRIL])
    await act(() => queryClient.invalidateQueries({ queryKey: ['statements'] }))

    expect(await screen.findByRole('button', monthTrigger(2024, 6))).toBeInTheDocument()
  })

  it('stays on the chosen month when a refetch returns the same months', async () => {
    serveMonths(MAY_AND_APRIL)
    const queryClient = renderPage()
    fireEvent.click(await screen.findByRole('button', { name: es.stmtsPrev }))

    await act(() => queryClient.invalidateQueries({ queryKey: ['statements'] }))
    await flushNotifications()

    expect(client.getStatementMonths).toHaveBeenCalledTimes(2)
    expect(screen.getByRole('button', monthTrigger(2024, 4))).toBeInTheDocument()
  })

  it('opens on the current month when there are no statements yet', async () => {
    serveMonths([])
    renderPage()

    const now = new Date()
    expect(await screen.findByRole('button', monthTrigger(now.getFullYear(), now.getMonth() + 1)))
      .toBeInTheDocument()
  })

  it('shows why the months could not be loaded', async () => {
    client.getStatementMonths.mockRejectedValue(new Error('HTTP 500 Internal Server Error'))
    renderPage()

    expect(await screen.findByText(
      `${es.kpiErrorLoading}${es.errorUnexpected('HTTP 500 Internal Server Error')}`,
    )).toBeInTheDocument()
  })
})
