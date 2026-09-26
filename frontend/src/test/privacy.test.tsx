/**
 * Privacy mode is a CSS-only guard driven by one attribute on <html>, so what
 * actually has to hold is that the attribute and the persisted flag stay in
 * step — including across a reload, which is where the FOUC guard reads it.
 */
import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { setupServer } from 'msw/node'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { PrivacyProvider, usePrivacy } from '../contexts/PrivacyContext'
import { ThemeProvider } from '../contexts/ThemeContext'
import { createQueryClient } from '../api/queryClient'
import { handlers } from '../demo/handlers'
import { LanguageProvider } from '../i18n'
import Layout from '../components/Layout'
import PrivacyToggle from '../components/PrivacyToggle'

import Dashboard from '../pages/Dashboard'
import FinancesOverviewPage from '../pages/FinancesOverviewPage'
import InvestmentsLandingPage from '../pages/InvestmentsLandingPage'
import MortgagePage from '../pages/MortgagePage'
import TransactionsPage from '../pages/TransactionsPage'

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    loading: false, initialized: true, authenticated: true, username: 'demo',
    onSetupSuccess: vi.fn(), onLoginSuccess: vi.fn(), onLogout: vi.fn(),
  }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}))

function attr(): string | null {
  return document.documentElement.getAttribute('data-privacy')
}

function Harness() {
  const { hidden, toggle } = usePrivacy()
  return (
    <>
      <span data-testid="state">{hidden ? 'hidden' : 'visible'}</span>
      <button type="button" onClick={toggle}>toggle</button>
    </>
  )
}

function renderToggle() {
  return render(
    <PrivacyProvider>
      <LanguageProvider><PrivacyToggle /></LanguageProvider>
    </PrivacyProvider>,
  )
}

describe('privacy mode', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-privacy')
  })

  it('starts visible and sets the attribute when toggled on', async () => {
    const user = userEvent.setup()
    render(<PrivacyProvider><Harness /></PrivacyProvider>)

    expect(attr()).toBeNull()
    expect(screen.getByTestId('state')).toHaveTextContent('visible')

    await user.click(screen.getByRole('button', { name: 'toggle' }))
    expect(attr()).toBe('on')
    expect(screen.getByTestId('state')).toHaveTextContent('hidden')

    await user.click(screen.getByRole('button', { name: 'toggle' }))
    expect(attr()).toBeNull()
  })

  it('persists the choice so the FOUC guard can restore it', async () => {
    const user = userEvent.setup()
    render(<PrivacyProvider><Harness /></PrivacyProvider>)

    await user.click(screen.getByRole('button', { name: 'toggle' }))
    expect(localStorage.getItem('finlytics_privacy')).toBe('1')
  })

  it('rehydrates as hidden when storage says so', () => {
    localStorage.setItem('finlytics_privacy', '1')
    render(<PrivacyProvider><Harness /></PrivacyProvider>)

    expect(screen.getByTestId('state')).toHaveTextContent('hidden')
    expect(attr()).toBe('on')
  })

  it('toggles from the keyboard shortcut', async () => {
    const user = userEvent.setup()
    render(<PrivacyProvider><Harness /></PrivacyProvider>)

    await user.keyboard('{Alt>}{Shift>}H{/Shift}{/Alt}')
    expect(attr()).toBe('on')
  })

  it('ignores the shortcut while typing', async () => {
    const user = userEvent.setup()
    render(
      <PrivacyProvider>
        <>
          <input aria-label="note" />
          <Harness />
        </>
      </PrivacyProvider>,
    )

    await user.click(screen.getByLabelText('note'))
    await user.keyboard('{Alt>}{Shift>}H{/Shift}{/Alt}')
    expect(attr()).toBeNull()
  })

  it('exposes the toggle button state to assistive tech', async () => {
    const user = userEvent.setup()
    renderToggle()

    const btn = screen.getByRole('button')
    expect(btn).toHaveAttribute('aria-pressed', 'false')

    await user.click(btn)
    expect(screen.getByRole('button')).toHaveAttribute('aria-pressed', 'true')
  })
})

/**
 * The guard is only as good as its coverage: a screen that renders an amount
 * outside a `.private` subtree leaks it, and nothing throws when that happens.
 * Mounting the money-bearing routes against the demo dataset is what turns a
 * missed call site into a failing test instead of a silent hole.
 */
const server = setupServer(...handlers)

/** Matches a rendered euro amount in either locale ("1.234,50 €" / "€1,234.50"). */
const EURO = /\d[\d.,\s]*€|€\s?\d/

const MONEY_ROUTES: [string, React.ReactNode][] = [
  ['/', <Dashboard key="d" />],
  ['/finances', <FinancesOverviewPage key="f" />],
  ['/transactions', <TransactionsPage key="t" />],
  ['/investments', <InvestmentsLandingPage key="i" />],
  ['/mortgage', <MortgagePage key="m" />],
]

function renderRoute(path: string, element: React.ReactNode) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <ThemeProvider>
        <PrivacyProvider>
          <LanguageProvider>
            <MemoryRouter initialEntries={[path]}>
              <Routes>
                <Route path="/" element={<Layout />}>
                  <Route path={path === '/' ? '/' : path.slice(1)} element={element} />
                </Route>
              </Routes>
            </MemoryRouter>
          </LanguageProvider>
        </PrivacyProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  )
}

/** Amounts rendered without a `.private` ancestor — i.e. what would stay sharp. */
function unblurredAmounts(root: HTMLElement): string[] {
  const found: string[] = []
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  let node = walker.nextNode()
  while (node) {
    const text = node.textContent?.trim() ?? ''
    if (EURO.test(text) && !(node.parentElement?.closest('.private'))) {
      found.push(text.slice(0, 60))
    }
    node = walker.nextNode()
  }
  return found
}

describe('every rendered amount is covered by privacy mode', () => {
  beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
  afterAll(() => server.close())
  afterEach(() => server.resetHandlers())

  it.each(MONEY_ROUTES)('%s', async (path, element) => {
    const { container } = renderRoute(path, element)

    await waitFor(() => {
      expect(container.querySelector('.app-shell')).not.toBeNull()
    })
    await new Promise(r => setTimeout(r, 400))

    expect(unblurredAmounts(container)).toEqual([])
  })
})
