/**
 * The shell's navigation state follows the route: the drawer closes once a
 * link lands on another page, and a nav group unfolds when one of its routes
 * becomes active yet stays foldable by hand while the visitor is on it.
 */
import { QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import Layout from './Layout'
import { createQueryClient } from '../api/queryClient'
import { ThemeProvider } from '../contexts/ThemeContext'
import { handlers } from '../demo/handlers'
import { COMPACT_NAV_QUERY } from '../hooks/useMediaQuery'
import { LanguageProvider } from '../i18n'

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

let realMatchMedia: typeof window.matchMedia
beforeEach(() => { realMatchMedia = window.matchMedia })
afterEach(() => { window.matchMedia = realMatchMedia })

function emulateCompactViewport() {
  window.matchMedia = ((query: string) => ({
    matches: query === COMPACT_NAV_QUERY,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia
}

function renderShell() {
  const view = render(
    <QueryClientProvider client={createQueryClient()}>
      <ThemeProvider>
        <LanguageProvider>
          <MemoryRouter initialEntries={['/']}>
            <Routes>
              <Route path="/" element={<Layout />}>
                <Route index element={<p>home</p>} />
                <Route path="*" element={<p>page</p>} />
              </Route>
            </Routes>
          </MemoryRouter>
        </LanguageProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  )
  const sidebar = view.container.querySelector<HTMLElement>('aside#app-sidebar')!
  return { ...view, sidebar }
}

describe('the mobile drawer', () => {
  it('closes once a link lands on another page', async () => {
    emulateCompactViewport()
    const { container, sidebar } = renderShell()

    fireEvent.click(container.querySelector('.hamburger-btn')!)
    expect(sidebar).toHaveClass('mobile-open')

    fireEvent.click(sidebar.querySelector('a[href="/mortgage"]')!)

    await screen.findByText('page')
    expect(sidebar).not.toHaveClass('mobile-open')
  })

  it('closes on Escape', () => {
    emulateCompactViewport()
    const { container, sidebar } = renderShell()

    fireEvent.click(container.querySelector('.hamburger-btn')!)
    expect(sidebar).toHaveClass('mobile-open')

    fireEvent.keyDown(window, { key: 'Escape' })
    expect(sidebar).not.toHaveClass('mobile-open')
  })
})

describe('a nav group', () => {
  it('unfolds when its route becomes active and can be folded while on it', async () => {
    const { sidebar } = renderShell()
    const section = sidebar.querySelector<HTMLElement>('[data-prefetch="/finances"]')!
    const arrow = section.closest('.sidebar-section-header')!
      .querySelector<HTMLElement>('.sidebar-section-arrow-btn')!
    const transactionsLink = () => sidebar.querySelector('a[href="/transactions"]')

    expect(arrow).toHaveAttribute('aria-expanded', 'false')
    expect(transactionsLink()).toBeNull()

    fireEvent.click(section)
    await screen.findByText('page')
    expect(arrow).toHaveAttribute('aria-expanded', 'true')
    expect(transactionsLink()).not.toBeNull()

    fireEvent.click(arrow)
    expect(arrow).toHaveAttribute('aria-expanded', 'false')
    expect(transactionsLink()).toBeNull()

    // Opening the section it is already on does not undo the visitor's choice
    await act(async () => { fireEvent.click(section) })
    expect(arrow).toHaveAttribute('aria-expanded', 'false')

    // Leaving and coming back unfolds it again
    fireEvent.click(sidebar.querySelector('.sidebar-nav a[href="/"]')!)
    await screen.findByText('home')
    fireEvent.click(section)
    await screen.findByText('page')
    expect(arrow).toHaveAttribute('aria-expanded', 'true')
  })
})
