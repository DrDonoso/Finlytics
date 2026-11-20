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
import type { FidelityImportPreview, InvestmentPlugin, NotificationOut } from '../api/types'
import NotificationBell from '../components/NotificationBell'
import { NotificationsProvider } from '../contexts/NotificationsContext'
import { ToastProvider } from '../contexts/ToastContext'
import { handlers } from '../demo/handlers'
import { buildScenario } from '../demo/scenario'
import { LanguageProvider } from '../i18n'
import en from '../i18n/en'
import es from '../i18n/es'
import FidelityView from '../investments/views/FidelityView'
import Dashboard from '../pages/Dashboard'
import ConnectorsPage from '../pages/ConnectorsPage'

const server = setupServer(...handlers)
const scenario = buildScenario()
const fidelityPlugin: InvestmentPlugin = {
  id: 'fidelity-espp', name: 'Fidelity ESPP', description: '', icon: '',
  status: 'connected', auth_type: 'none', supported_features: ['import'],
  import_route: '/investments/fidelity-espp',
}
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
    cost_basis_per_share_usd: 400,
    cost_basis_total_usd: 800,
    share_source: 'SP',
    grant_date: null,
  }],
  duplicate_count: 0,
  total_in_file: 1,
  source_currency: 'USD',
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
    http.get('/api/notifications/channels', () => HttpResponse.json([])),
    http.get('/api/notifications/import-summary-settings', () => HttpResponse.json({
      enabled: false, channel_id: null, language: 'en', ai_available: false,
    })),
    http.get('/api/notifications/import-summaries', () => HttpResponse.json([])),
    http.get('/api/investments/plugins', () => HttpResponse.json([fidelityPlugin])),
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
    { path: '/settings/connectors', element: <ConnectorsPage /> },
    { path: '/bell', element: <NotificationBell /> },
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
  it.each(['en', 'es'] as const)('explains a currency rejection in %s without allowing confirmation', async lang => {
    localStorage.setItem('finlytics_lang', lang)
    const t = lang === 'en' ? en : es
    vi.mocked(api.fidelityImportPreview).mockRejectedValue(Object.assign(
      new Error('Only USD exports are supported.'), { code: 'fidelity_usd_required' },
    ))
    const user = userEvent.setup()
    renderPage('/investments/fidelity-espp?import=1')
    const dialog = within(await screen.findByRole('dialog', { name: t.fidelityImportTitle }))
    await user.upload(dialog.getByLabelText(t.fidelityImportCta), new File(['synthetic'], 'eur.csv', { type: 'text/csv' }))
    await user.click(dialog.getByRole('button', { name: t.fidelityImportConfirmBtn }))
    expect(await dialog.findByRole('alert')).toHaveTextContent(t.fidelityUsdRequired)
    expect(api.fidelityImportConfirm).not.toHaveBeenCalled()
    expect(dialog.queryByText(t.fidelityImportPreviewTitle)).toBeNull()
  })

  it('labels preview amounts in USD and keeps private amounts covered', async () => {
    const user = userEvent.setup()
    renderPage('/investments/fidelity-espp?import=1')
    const dialog = await uploadCsv(user)
    expect(dialog.getByText(en.fidelityPreviewUsd)).toBeInTheDocument()
    const cost = dialog.getByText('US$800.00')
    expect(cost).toHaveClass('private')
    expect(dialog.queryByText('€800.00')).toBeNull()
  })

  it('blocks a legacy deep link and directs the owner to the explicit reset', async () => {
    server.use(http.get('/api/investments/fidelity/kpis', () => HttpResponse.json({
      ...scenario.espp.kpis, requires_usd_reimport: true, cost_basis_usd: null,
    })))
    renderPage('/investments/fidelity-espp?import=1')
    expect(await screen.findByText(en.fidelityLegacyNotice)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: en.fidelityImportBtn })).toBeDisabled()
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.getByRole('link', { name: en.fidelityClearData })).toHaveAttribute('href', '/settings/connectors')
  })

  it('resets only Fidelity after an explicit destructive confirmation', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true)
    const disconnect = vi.spyOn(api, 'disconnectConnection').mockResolvedValue(undefined)
    const user = userEvent.setup()
    const { client } = renderPage('/settings/connectors')
    client.setQueryData(queryKeys.fidelityKpis, scenario.espp.kpis)
    const button = await screen.findByRole('button', { name: en.fidelityClearData })
    await user.click(button)
    expect(disconnect).not.toHaveBeenCalled()
    await user.click(button)
    expect(confirm).toHaveBeenCalledWith(en.fidelityClearDataConfirm)
    const connection = scenario.connections.find(c => c.plugin_id === 'fidelity-espp')
    expect(connection).toBeDefined()
    expect(disconnect).toHaveBeenCalledExactlyOnceWith(connection?.id)
    await waitFor(() => expect(client.getQueryState(queryKeys.fidelityKpis)?.isInvalidated).toBe(true))
  })

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

function modelo720Check(verdict: 'exceeds' | 'below', value: number): NotificationOut {
  return {
    id: 2,
    source: 'modelo720',
    type: `modelo720_${verdict}`,
    severity: verdict === 'exceeds' ? 'warning' : 'info',
    title_key: `notif.modelo720_${verdict}`,
    title_args: { year: '2026' },
    body_key: `notif.modelo720_${verdict}`,
    body_args: { value_eur: value },
    action_link: '/investments/fidelity-espp',
    created_at: '2027-01-15T00:00:00Z',
    read_at: null,
    dismissed_at: null,
  }
}

function serveChecks(...checks: NotificationOut[]) {
  let listed = checks
  const dismissed: string[] = []
  server.use(
    http.get('/api/notifications', () => HttpResponse.json(listed)),
    http.get('/api/notifications/unread-count', () => HttpResponse.json({ count: listed.length })),
    http.post('/api/notifications/:id/dismiss', ({ params }) => {
      dismissed.push(String(params.id))
      listed = listed.filter(check => String(check.id) !== params.id)
      return new HttpResponse(null, { status: 204 })
    }),
  )
  return dismissed
}

describe('Modelo 720 check', () => {
  it.each(['/', '/investments/fidelity-espp'])('tells the verdict and its blurred value on %s', async path => {
    const dismissed = serveChecks(modelo720Check('exceeds', 52200))
    const user = userEvent.setup()
    renderPage(path)

    const title = await screen.findByText(en.notifTitleModelo720Exceeds({ year: '2026' }))
    const banner = title.closest('.modelo720-banner') as HTMLElement
    expect(banner).toHaveAttribute('role', 'alert')
    expect(within(banner).getByText(en.notifBodyModelo720Exceeds)).toBeInTheDocument()
    expect(within(banner).getByText('€52,200.00')).toHaveClass('private')
    const link = within(banner).queryByRole('link', { name: en.modelo720Action })
    if (path === '/') expect(link).toHaveAttribute('href', '/investments/fidelity-espp')
    else expect(link).toBeNull()

    await user.click(within(banner).getByRole('button', { name: en.notifDismiss }))

    await waitFor(() => expect(screen.queryByText(en.notifTitleModelo720Exceeds({ year: '2026' }))).toBeNull())
    expect(dismissed).toEqual(['2'])
  })

  it('also tells when the shares stay below the threshold', async () => {
    localStorage.setItem('finlytics_lang', 'es')
    serveChecks(modelo720Check('below', 42000))
    renderPage()

    const title = await screen.findByText(es.notifTitleModelo720Below({ year: '2026' }))
    const banner = title.closest('.modelo720-banner') as HTMLElement
    expect(banner).toHaveAttribute('role', 'status')
    expect(banner).toHaveClass('modelo720-banner--info')
    expect(within(banner).getByText(es.notifBodyModelo720Below)).toBeInTheDocument()
    expect(within(banner).getByText(/42\.000,00\s€/)).toHaveClass('private')
  })

  it('lists it in the bell with what it means', async () => {
    serveChecks(modelo720Check('exceeds', 52200))
    const user = userEvent.setup()
    renderPage('/bell')

    await user.click(screen.getByRole('button', { name: en.notifPanelTitle }))

    const panel = within(await screen.findByRole('dialog', { name: en.notifPanelTitle }))
    expect(await panel.findByText(en.notifTitleModelo720Exceeds({ year: '2026' }))).toBeInTheDocument()
    expect(panel.getByText(en.notifBodyModelo720Exceeds)).toBeInTheDocument()
    expect(panel.queryByText(/52,200/)).toBeNull()
  })
})
