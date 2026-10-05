import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { delay, http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import { createQueryClient } from '../api/queryClient'
import { queryKeys } from '../api/queries'
import type { ImportSummaryJob, ImportSummarySettings as Settings, NotificationChannelOut } from '../api/types'
import ImportSummarySettings from '../components/ImportSummarySettings'
import { LanguageProvider } from '../i18n'
import en from '../i18n/en'
import es from '../i18n/es'

let settings: Settings
let jobs: ImportSummaryJob[]
let writes: unknown[]
let retries: unknown[]

const channels: NotificationChannelOut[] = [{
  id: 7, channel: 'telegram', enabled: true, label: 'Telegram test', created_at: '2026-06-01T00:00:00Z',
}]

const server = setupServer(
  http.get('/api/notifications/import-summary-settings', () => HttpResponse.json(settings)),
  http.put('/api/notifications/import-summary-settings', async ({ request }) => {
    const payload = await request.json()
    writes.push(payload)
    settings = { ...settings, ...payload as Settings }
    return HttpResponse.json(settings)
  }),
  http.get('/api/notifications/import-summaries', () => HttpResponse.json(jobs)),
  http.post('/api/notifications/import-summaries/:id/retry', async ({ request }) => {
    retries.push(await request.json())
    return HttpResponse.json(jobs[0])
  }),
)

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
beforeEach(() => {
  settings = { enabled: false, channel_id: null, language: 'en', ai_available: true }
  jobs = []
  writes = []
  retries = []
  localStorage.setItem('finlytics_lang', 'en')
})
afterEach(() => {
  server.resetHandlers()
  localStorage.clear()
  vi.restoreAllMocks()
})

function renderSettings(available = channels) {
  const client = createQueryClient()
  client.setDefaultOptions({ queries: { retry: false } })
  const onConnect = vi.fn()
  render(
    <QueryClientProvider client={client}>
      <LanguageProvider>
        <ImportSummarySettings channels={available} onConnect={onConnect} />
      </LanguageProvider>
    </QueryClientProvider>,
  )
  return { client, onConnect }
}

describe('import summary preferences', () => {
  it('starts disabled and requires a selected configured channel', async () => {
    const user = userEvent.setup()
    renderSettings()
    const toggle = await screen.findByRole('checkbox', { name: en.importSummaryEnable })
    expect(toggle).not.toBeChecked()
    await user.click(toggle)
    expect(screen.getByRole('button', { name: en.assistantSettingsSave })).toBeDisabled()
    await user.selectOptions(screen.getByLabelText(en.importSummaryChannel), '7')
    await user.click(screen.getByRole('button', { name: en.assistantSettingsSave }))
    await waitFor(() => expect(writes).toEqual([{ enabled: true, channel_id: 7, language: 'en' }]))
    expect(await screen.findByRole('status')).toHaveTextContent(en.assistantSettingsSaved)
    expect(screen.getByRole('checkbox')).toBeChecked()
  })

  it('provides the existing Telegram setup entry point when no channels exist', async () => {
    const user = userEvent.setup()
    const { onConnect } = renderSettings([])
    expect(await screen.findByText(en.importSummaryNoChannels)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: en.notifSettingsConnectBtn }))
    expect(onConnect).toHaveBeenCalledOnce()
    await user.click(screen.getByRole('checkbox'))
    expect(screen.getByRole('button', { name: en.assistantSettingsSave })).toBeDisabled()
  })

  it('does not mount the form with empty defaults while settings are loading', async () => {
    server.use(http.get('/api/notifications/import-summary-settings', async () => {
      await delay(100)
      return HttpResponse.json({ ...settings, enabled: true, channel_id: 7 })
    }))
    renderSettings()
    expect(screen.queryByRole('checkbox')).toBeNull()
    expect(await screen.findByRole('checkbox')).toBeChecked()
    expect(screen.getByRole('combobox')).toHaveValue('7')
  })

  it('shows failed reads instead of inventing settings', async () => {
    server.use(http.get('/api/notifications/import-summary-settings', () =>
      HttpResponse.json({ detail: 'Settings unavailable' }, { status: 500 }),
    ))
    renderSettings()
    expect(await screen.findByRole('alert')).toHaveTextContent('500')
    expect(screen.queryByRole('checkbox')).toBeNull()
  })

  it('blocks activation without AI while allowing the feature to be disabled', async () => {
    settings = { ...settings, ai_available: false }
    const { client } = renderSettings()
    expect(await screen.findByRole('checkbox')).toBeDisabled()
    client.setQueryData(queryKeys.importSummarySettings, { ...settings, enabled: true, channel_id: 7 })
    await waitFor(() => expect(screen.getByRole('checkbox')).toBeEnabled())
    await userEvent.click(screen.getByRole('checkbox'))
    expect(screen.getByRole('button', { name: en.assistantSettingsSave })).toBeEnabled()
  })

  it('follows a persisted channel removal without preserving stale enabled form state', async () => {
    settings = { ...settings, enabled: true, channel_id: 7 }
    const { client } = renderSettings()
    expect(await screen.findByRole('checkbox')).toBeChecked()
    client.setQueryData(queryKeys.importSummarySettings, { ...settings, enabled: false, channel_id: null })
    await waitFor(() => expect(screen.getByRole('checkbox')).not.toBeChecked())
  })

  it.each(['en', 'es'] as const)('localizes the form and persists %s for background delivery', async language => {
    localStorage.setItem('finlytics_lang', language)
    const t = language === 'es' ? es : en
    const user = userEvent.setup()
    renderSettings()
    expect(screen.getByRole('heading', { name: t.importSummaryTitle })).toBeInTheDocument()
    await user.click(await screen.findByRole('checkbox', { name: t.importSummaryEnable }))
    await user.selectOptions(screen.getByLabelText(t.importSummaryChannel), '7')
    await user.click(screen.getByRole('button', { name: t.assistantSettingsSave }))
    await waitFor(() => expect(writes).toEqual([{ enabled: true, channel_id: 7, language }]))
  })

  it('requires explicit acknowledgement before retrying an uncertain delivery', async () => {
    settings = { ...settings, enabled: true, channel_id: 7 }
    jobs = [{
      id: 3, import_run_id: 9, account_name: 'Checking', from_date: '2026-06-01',
      to_date: '2026-06-30', language: 'en', status: 'uncertain', error: 'delivery_uncertain',
      created_at: '2026-07-01T00:00:00Z', sent_at: null,
    }]
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderSettings()
    const retry = await screen.findByRole('button', { name: en.importSummaryRetry })
    await waitFor(() => expect(retry).toBeEnabled())
    await userEvent.click(retry)
    expect(retries).toEqual([])
    confirm.mockReturnValue(true)
    await userEvent.click(retry)
    await waitFor(() => expect(retries).toEqual([{ acknowledge_uncertain: true }]))
    expect(confirm).toHaveBeenCalledWith(en.importSummaryUncertainConfirm)
  })
})
