/**
 * Pointing at or focusing a sidebar entry starts downloading its page, so the
 * chunk is usually in by the time the click lands.
 *
 * The page modules are replaced by doubles that record when they are imported:
 * the assertion is on the import itself, which is what a prefetch buys.
 */
import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, waitFor } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'

import { createQueryClient } from '../api/queryClient'
import Layout from '../components/Layout'
import { ThemeProvider } from '../contexts/ThemeContext'
import { handlers } from '../demo/handlers'
import { LanguageProvider } from '../i18n'

const imported = vi.hoisted(() => vi.fn<(page: string) => void>())

vi.mock('../pages/MortgagePage', () => {
  imported('mortgage')
  return { default: () => null }
})

vi.mock('../pages/FinancesOverviewPage', () => {
  imported('finances')
  return { default: () => null }
})

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    loading: false, initialized: true, authenticated: true, username: 'demo',
    onSetupSuccess: vi.fn(), onLoginSuccess: vi.fn(), onLogout: vi.fn(),
  }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}))

const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterAll(() => server.close())

function renderShell() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <ThemeProvider>
        <LanguageProvider>
          <MemoryRouter initialEntries={['/']}>
            <Routes>
              <Route path="/" element={<Layout />}>
                <Route index element={<p>home</p>} />
              </Route>
            </Routes>
          </MemoryRouter>
        </LanguageProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  )
}

describe('the shell prefetches the page a visitor is about to open', () => {
  it('when a link is pointed at', async () => {
    const { container } = renderShell()
    const link = container.querySelector('.sidebar-nav a[href="/mortgage"]')
    expect(link).not.toBeNull()
    expect(imported).not.toHaveBeenCalledWith('mortgage')

    fireEvent.pointerOver(link!.querySelector('.nav-label')!)

    await waitFor(() => expect(imported).toHaveBeenCalledWith('mortgage'))
  })

  it('when a section button is focused', async () => {
    const { container } = renderShell()
    const button = container.querySelector('[data-prefetch="/finances"]')
    expect(button).not.toBeNull()
    expect(imported).not.toHaveBeenCalledWith('finances')

    fireEvent.focus(button!)

    await waitFor(() => expect(imported).toHaveBeenCalledWith('finances'))
  })
})
