/**
 * A connected account that cannot be read still holds money. Rendering its
 * absence as zeros, or a total without it as the whole, tells the user their
 * portfolio is smaller than it is — and nothing on screen says otherwise.
 */
import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { MemoryRouter } from 'react-router'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest'

import { createQueryClient } from '../api/queryClient'
import type { InvestmentPortfolio } from '../api/types'
import { handlers } from '../demo/handlers'
import { buildScenario } from '../demo/scenario'
import { LanguageProvider } from '../i18n'
import en from '../i18n/en'
import IndexaView from '../investments/views/IndexaView'
import InvestmentsLandingPage from '../pages/InvestmentsLandingPage'

const scenario = buildScenario()
const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterAll(() => server.close())
beforeEach(() => localStorage.setItem('finlytics_lang', 'en'))
afterEach(() => {
  server.resetHandlers()
  localStorage.clear()
})

function servePortfolio(portfolio: InvestmentPortfolio) {
  server.use(http.get('/api/investments/portfolio', () => HttpResponse.json(portfolio)))
}

function renderPage(page: React.ReactNode) {
  const client = createQueryClient()
  client.setDefaultOptions({ queries: { ...client.getDefaultOptions().queries, retry: false } })
  return render(
    <QueryClientProvider client={client}>
      <LanguageProvider>
        <MemoryRouter>{page}</MemoryRouter>
      </LanguageProvider>
    </QueryClientProvider>,
  )
}

describe('the Indexa view', () => {
  it('reports an unreadable connection instead of an empty portfolio', async () => {
    servePortfolio({
      ...scenario.portfolio,
      total_value: 0,
      plugins_connected: 0,
      last_updated: null,
      accounts_unavailable: 1,
      holdings: [],
    })

    renderPage(<IndexaView />)

    expect(await screen.findByText(en.invAccountsUnreadable)).toBeInTheDocument()
    expect(screen.queryByText(en.investmentsEmptyHoldings)).toBeNull()
    expect(screen.getByRole('link', { name: new RegExp(en.investmentsManageConnectors) }))
      .toHaveAttribute('href', '/settings/connectors')
  })

  it('shows what was read and says how many accounts are missing', async () => {
    servePortfolio({ ...scenario.portfolio, accounts_unavailable: 2 })

    renderPage(<IndexaView />)

    expect(await screen.findByText(en.invAccountsUnavailable(2))).toBeInTheDocument()
    expect(screen.getByText(en.invSummaryValorTotal)).toBeInTheDocument()
  })

  it('stays quiet when every account was read', async () => {
    renderPage(<IndexaView />)

    expect(await screen.findByText(en.invSummaryValorTotal)).toBeInTheDocument()
    expect(document.querySelector('.inv-partial-banner')).toBeNull()
  })
})

describe('the investments overview', () => {
  it('flags a total that leaves a provider out', async () => {
    server.use(http.get('/api/investments/combined-overview', () =>
      HttpResponse.json({ ...scenario.combined, partial: true })))

    renderPage(<InvestmentsLandingPage />)

    expect(await screen.findByText(en.invPartialTotal)).toBeInTheDocument()
  })

  it('does not flag a complete total', async () => {
    renderPage(<InvestmentsLandingPage />)

    expect(await screen.findByText(en.invCombinedTotalValue)).toBeInTheDocument()
    expect(screen.queryByText(en.invPartialTotal)).toBeNull()
  })
})
