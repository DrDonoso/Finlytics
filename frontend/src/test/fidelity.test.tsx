import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import * as api from '../api/client'
import { queryKeys } from '../api/queries'
import { createQueryClient } from '../api/queryClient'
import type { FidelityImportPreview, NotificationOut } from '../api/types'
import { NotificationsProvider } from '../contexts/NotificationsContext'
import { ToastProvider } from '../contexts/ToastContext'
import { handlers } from '../demo/handlers'
import { buildScenario } from '../demo/scenario'
import { LanguageProvider } from '../i18n'
import en from '../i18n/en'
import FidelityView from '../investments/views/FidelityView'
import Dashboard from '../pages/Dashboard'

const server = setupServer(...handlers)
const scenario = buildScenario()
const pendingPurchase: NotificationOut = {
  id: 1,
  source: 'espp',
  type: 'espp_overdue',
  severity: 'warning',
  title_key: 'notif.espp_overdue',
  title_args: { period: 'Q3 2026' },
  body_key: null,
  body_args: null,
  action_link: '/investments/fidelity-espp',
  created_at: '2026-10-01T00:00:00Z',
  read_at: null,
  dismissed_at: null,
}
const preview: FidelityImportPreview = {
  new_lots: [{
    purchase_date: '2026-09-30',
    shares: 2,
    cost_basis_per_share_eur: 400,
    cost_basis_total_eur: 800,
    share_source: 'SP',
    grant_date: null,
  }],
  duplicate_count: 0,
  total_in_file: 1,
  source_currency: 'EUR',
  file_already_imported: false,
}

let imported = false
let notificationReads = 0

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
beforeEach(() => {
  localStorage.setItem('finlytics_lang', 'en')
  imported = false
  notificationReads = 0
  vi.spyOn(api, 'fidelityImportPreview').mockResolvedValue(preview)
  vi.spyOn(api, 'fidelityImportConfirm').mockImplementation(async () => {
    imported = true
    return { inserted: 1, duplicates: 0 }
  })
  server.use(
    http.get('/api/notifications', () => {
      notificationReads += 1
      return HttpResponse.json(imported ? [] : [pendingPurchase])
    }),
    http.get('/api/notifications/unread-count', () =>
      HttpResponse.json({ count: imported ? 0 : 1 })),
  )
})
afterEach(() => {
  vi.restoreAllMocks()
  server.resetHandlers()
  localStorage.clear()
})

function renderPage(path = '/investments/fidelity-espp') {
  const client = createQueryClient()
  client.setDefaultOptions({ queries: { ...client.getDefaultOptions().queries, retry: false } })
  const router = createMemoryRouter([
    { path: '/', element: <Dashboard /> },
    { path: '/investments/fidelity-espp', element: <FidelityView /> },
  ], { initialEntries: [path] })
  render(
    <QueryClientProvider client={client}>
      <LanguageProvider>
        <ToastProvider>
          <NotificationsProvider>
            <RouterProvider router={router} />
          </NotificationsProvider>
        </ToastProvider>
      </LanguageProvider>
    </QueryClientProvider>,
  )
  return { client, router }
}

async function uploadCsv(user: ReturnType<typeof userEvent.setup>) {
  const dialog = within(await screen.findByRole('dialog', { name: en.fidelityImportTitle }))
  await user.upload(
    dialog.getByLabelText(en.fidelityImportCta),
    new File(['synthetic CSV'], 'lots.csv', { type: 'text/csv' }),
  )
  await user.click(dialog.getByRole('button', { name: en.fidelityImportConfirmBtn }))
  await dialog.findByText(en.fidelityImportPreviewTitle)
  return dialog
}

describe('Fidelity import actions', () => {
  it.each(['/', '/investments/fidelity-espp'])('opens the importer from the reminder on %s', async path => {
    const user = userEvent.setup()
    const { router } = renderPage(path)

    await user.click(await screen.findByRole(path === '/' ? 'link' : 'button', {
      name: en.esppReminderAction,
    }))

    expect(await screen.findByRole('dialog', { name: en.fidelityImportTitle })).toBeVisible()
    expect(router.state.location.pathname).toBe('/investments/fidelity-espp')
    expect(imported).toBe(false)
  })

  it('closes a deep-linked importer without dropping other parameters and reopens it cleanly', async () => {
    const user = userEvent.setup()
    const { router } = renderPage('/investments/fidelity-espp?view=lots&import=1')
    const dialog = within(await screen.findByRole('dialog', { name: en.fidelityImportTitle }))
    await user.upload(
      dialog.getByLabelText(en.fidelityImportCta),
      new File(['synthetic CSV'], 'lots.csv', { type: 'text/csv' }),
    )

    await user.click(dialog.getByRole('button', { name: en.modalBtnCancel }))

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(router.state.location.search).toBe('?view=lots')
    await user.click(screen.getByRole('button', { name: en.fidelityImportBtn }))
    const reopened = within(await screen.findByRole('dialog', { name: en.fidelityImportTitle }))
    expect(reopened.queryByText('lots.csv')).toBeNull()
    expect(reopened.getByRole('button', { name: en.fidelityImportConfirmBtn })).toBeDisabled()
    expect(new URLSearchParams(router.state.location.search).get('view')).toBe('lots')
  })

  it('refreshes notifications and investment caches only after a confirmed import', async () => {
    const user = userEvent.setup()
    const { client } = renderPage()
    client.setQueryData(queryKeys.combinedOverview, scenario.combined)
    client.setQueryData(queryKeys.connections, scenario.connections)

    await user.click(await screen.findByRole('button', { name: en.fidelityImportBtn }))
    const dialog = await uploadCsv(user)
    expect(imported).toBe(false)
    expect(api.fidelityImportPreview).toHaveBeenCalledWith(expect.objectContaining({ name: 'lots.csv' }))
    expect(api.fidelityImportConfirm).not.toHaveBeenCalled()
    expect(notificationReads).toBe(1)
    expect(screen.getByText(en.esppReminderBanner('Q3 2026'))).toBeInTheDocument()

    await user.click(dialog.getByRole('button', { name: en.fidelityImportConfirmBtn }))

    expect(await dialog.findByText(en.fidelityImportSuccessTitle)).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByText(en.esppReminderBanner('Q3 2026'))).toBeNull())
    expect(imported).toBe(true)
    expect(api.fidelityImportConfirm).toHaveBeenCalledWith(vi.mocked(api.fidelityImportPreview).mock.calls[0][0])
    expect(notificationReads).toBe(2)
    expect(client.getQueryState(queryKeys.combinedOverview)?.isInvalidated).toBe(true)
    expect(client.getQueryState(queryKeys.connections)?.isInvalidated).toBe(true)
  })

  it('keeps the reminder and preview available when the import fails', async () => {
    vi.mocked(api.fidelityImportConfirm).mockRejectedValue(new Error('HTTP 503 Service Unavailable'))
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: en.fidelityImportBtn }))
    const dialog = await uploadCsv(user)
    await user.click(dialog.getByRole('button', { name: en.fidelityImportConfirmBtn }))

    expect(await dialog.findByRole('alert')).toHaveTextContent('HTTP 503 Service Unavailable')
    expect(dialog.getByText(en.fidelityImportPreviewTitle)).toBeInTheDocument()
    expect(screen.getByText(en.esppReminderBanner('Q3 2026'))).toBeInTheDocument()
    expect(notificationReads).toBe(1)
    expect(imported).toBe(false)
  })

  it('keeps the regular importer available without a pending purchase', async () => {
    server.use(
      http.get('/api/notifications', () => HttpResponse.json([])),
      http.get('/api/notifications/unread-count', () => HttpResponse.json({ count: 0 })),
    )
    const user = userEvent.setup()
    renderPage()

    await screen.findByText(en.fidelityKpiShares)
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.queryByRole('button', { name: en.esppReminderAction })).toBeNull()
    await user.click(screen.getByRole('button', { name: en.fidelityImportBtn }))
    expect(await screen.findByRole('dialog', { name: en.fidelityImportTitle })).toBeVisible()
  })
})
