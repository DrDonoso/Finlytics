/** A code-split page whose chunk cannot be fetched — the normal state of a tab left
 *  open across a deploy, since the deploy replaces the hashed files — must not take
 *  the whole app down with it: the failure stays in the content area, says how to
 *  recover, and clears once the user navigates somewhere else.
 */
import { render, screen } from '@testing-library/react'
import { lazy, Suspense, type ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import PageLoading from '../components/PageLoading'
import RouteErrorBoundary from '../components/RouteErrorBoundary'
import { LanguageProvider } from '../i18n'
import en from '../i18n/en'

beforeEach(() => {
  localStorage.setItem('finlytics_lang', 'en')
  // React reports every error a boundary catches, and failing is the point here.
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
})

function route(pathname: string, page: ReactNode) {
  return (
    <LanguageProvider>
      <RouteErrorBoundary resetKey={pathname}>
        <Suspense fallback={<PageLoading />}>{page}</Suspense>
      </RouteErrorBoundary>
    </LanguageProvider>
  )
}

const Missing = lazy(() => Promise.reject(new TypeError('Failed to fetch dynamically imported module')))

describe('a page whose code cannot be loaded', () => {
  it('is replaced by a reload prompt, which navigating away clears', async () => {
    const { rerender } = render(route('/mortgage', <Missing />))

    expect(await screen.findByRole('alert')).toHaveTextContent(en.pageLoadFailed)
    expect(screen.getByRole('button', { name: en.pageReload })).toBeInTheDocument()

    rerender(route('/', <p>Dashboard</p>))

    expect(screen.getByText('Dashboard')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('keeps the prompt while the location is unchanged', async () => {
    const { rerender } = render(route('/mortgage', <Missing />))
    await screen.findByRole('alert')

    rerender(route('/mortgage', <p>Dashboard</p>))

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.queryByText('Dashboard')).not.toBeInTheDocument()
  })
})
