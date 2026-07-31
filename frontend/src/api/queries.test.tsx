/**
 * Verifies that a slow response from a previous filter cannot overwrite the
 * active one.
 *
 * This is the bug that motivated migrating to keyed queries: when switching
 * periods quickly, the old useEffect + setState pattern would display results
 * from the first request if it resolved after the second. No error thrown — just
 * numbers that don't match the selected filter, practically invisible to the eye.
 */
import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { createQueryClient } from './queryClient'
import { useOverview } from './queries'
import type { Overview, SummaryParams } from './types'

const getOverview = vi.fn()

vi.mock('./client', () => ({
  getAccounts: vi.fn(),
  getByAccount: vi.fn(),
  getByCategory: vi.fn(),
  getByDay: vi.fn(),
  getByMerchant: vi.fn(),
  getByMonth: vi.fn(),
  getCashflow: vi.fn(),
  getCategories: vi.fn(),
  getCombinedOverview: vi.fn(),
  getConnections: vi.fn(),
  getOverview: (...a: unknown[]) => getOverview(...a),
  getOverviewMonths: vi.fn(),
  getRules: vi.fn(),
  getStatementMonths: vi.fn(),
  getStatementReminder: vi.fn(),
  getTags: vi.fn(),
}))

function overview(totalExpense: number): Overview {
  return {
    total_expense: totalExpense,
    total_income: 0,
    net: 0,
    num_transactions: 0,
    top_category: null,
    currency: 'EUR',
  }
}

/** Renders the total expense for the requested period so we can see which response won. */
function Probe({ params }: { params: SummaryParams }) {
  const { data, isPending } = useOverview(params)
  if (isPending) return <span data-testid="value">loading</span>
  return <span data-testid="value">{data?.total_expense ?? 'no data'}</span>
}

function wrapper(children: ReactNode) {
  const client = createQueryClient()
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('useOverview with changing filters', () => {
  it('discards stale responses even when they arrive last', async () => {
    const MAY = { from: '2026-05-01', to: '2026-05-31' }
    const JULY = { from: '2026-07-01', to: '2026-07-31' }

    let resolveMay: (v: Overview) => void = () => {}
    getOverview.mockImplementation((params: SummaryParams) => {
      if (params.from === MAY.from) {
        // MAY is deliberately left hanging — it will resolve last.
        return new Promise<Overview>(resolve => { resolveMay = resolve })
      }
      return Promise.resolve(overview(7000))
    })

    const { rerender } = render(wrapper(<Probe params={MAY} />))
    expect(await screen.findByText('loading')).toBeInTheDocument()

    // The user switches to July before May has responded.
    rerender(wrapper(<Probe params={JULY} />))
    await waitFor(() => expect(screen.getByTestId('value')).toHaveTextContent('7000'))

    // Now, late, the May response arrives.
    resolveMay(overview(5000))
    await new Promise(r => setTimeout(r, 50))

    // The screen must still show July, which is the active filter.
    expect(screen.getByTestId('value')).toHaveTextContent('7000')
    expect(screen.getByTestId('value')).not.toHaveTextContent('5000')
  })

  it('deduplicates concurrent requests for the same params', async () => {
    getOverview.mockResolvedValue(overview(1234))
    const params = { from: '2026-06-01', to: '2026-06-30' }

    const client = createQueryClient()
    const view = (
      <QueryClientProvider client={client}>
        <Probe params={params} />
        <Probe params={params} />
      </QueryClientProvider>
    )

    render(view)
    await waitFor(() => {
      expect(screen.getAllByTestId('value')[0]).toHaveTextContent('1234')
    })

    // Two components requesting the same data used to fire two requests.
    expect(getOverview).toHaveBeenCalledTimes(1)
  })

  it('keeps separate cache entries for different periods', async () => {
    getOverview.mockImplementation((params: SummaryParams) =>
      Promise.resolve(overview(params.from === '2026-05-01' ? 5000 : 7000)),
    )

    const client = createQueryClient()
    render(
      <QueryClientProvider client={client}>
        <Probe params={{ from: '2026-05-01', to: '2026-05-31' }} />
        <Probe params={{ from: '2026-07-01', to: '2026-07-31' }} />
      </QueryClientProvider>,
    )

    await waitFor(() => {
      const values = screen.getAllByTestId('value').map(n => n.textContent)
      expect(values).toContain('5000')
      expect(values).toContain('7000')
    })
    expect(getOverview).toHaveBeenCalledTimes(2)
  })
})

describe('the old useEffect pattern was genuinely broken', () => {
  /**
   * Reproduces the useEffect + setState pattern that existed before, to
   * document that the bug was real and not a theoretical precaution. If this
   * test stopped failing in its unguarded form, the migration would not have
   * been necessary.
   */
  function LegacyProbe({ params }: { params: SummaryParams }) {
    const [value, setValue] = useState<number | null>(null)

    useEffect(() => {
      setValue(null)
      getOverview(params).then((d: Overview) => setValue(d.total_expense))
    }, [params])

    return <span data-testid="legacy">{value === null ? 'loading' : value}</span>
  }

  it('leaves stale data on screen when a late response overwrites the active one', async () => {
    const MAY = { from: '2026-05-01', to: '2026-05-31' }
    const JULY = { from: '2026-07-01', to: '2026-07-31' }

    let resolveMay: (v: Overview) => void = () => {}
    getOverview.mockImplementation((params: SummaryParams) => {
      if (params.from === MAY.from) {
        return new Promise<Overview>(resolve => { resolveMay = resolve })
      }
      return Promise.resolve(overview(7000))
    })

    const { rerender } = render(<LegacyProbe params={MAY} />)
    rerender(<LegacyProbe params={JULY} />)
    await waitFor(() => expect(screen.getByTestId('legacy')).toHaveTextContent('7000'))

    // May arrives late...
    resolveMay(overview(5000))

    // ...and overwrites July: the screen shows May data with July as the active filter.
    await waitFor(() => expect(screen.getByTestId('legacy')).toHaveTextContent('5000'))
  })
})
