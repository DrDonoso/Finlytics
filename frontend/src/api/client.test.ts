/**
 * A failed read must reject. These functions used to catch every error and
 * resolve with the mock dataset, so a 500 or a dropped connection rendered
 * invented balances as if they were the user's.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  getAccounts,
  getByAccount,
  getByCategory,
  getByDay,
  getByMerchant,
  getByMonth,
  getCashflow,
  getCategories,
  getMortgageNetWorth,
  getNotifications,
  getOverview,
  getTags,
  getTransactions,
  putImportSummarySettings,
  retryImportSummary,
} from './client'

const READS: Array<[string, () => Promise<unknown>]> = [
  ['getAccounts', getAccounts],
  ['getByAccount', getByAccount],
  ['getByCategory', getByCategory],
  ['getByDay', getByDay],
  ['getByMerchant', getByMerchant],
  ['getByMonth', getByMonth],
  ['getCashflow', getCashflow],
  ['getCategories', getCategories],
  ['getMortgageNetWorth', getMortgageNetWorth],
  ['getNotifications', getNotifications],
  ['getOverview', getOverview],
  ['getTags', getTags],
  ['getTransactions', getTransactions],
]

afterEach(() => {
  vi.unstubAllGlobals()
})

describe.each(READS)('%s', (_name, read) => {
  it('rejects on a server error', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('boom', { status: 500 })))

    await expect(read()).rejects.toThrow('HTTP 500')
  })

  it('rejects when the network is down', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch') }))

    await expect(read()).rejects.toThrow('Failed to fetch')
  })
})

describe('import summary requests', () => {
  it.each([false, true])('sends the settings as JSON when enabled=%s', async enabled => {
    const payload = {
      enabled,
      channel_id: enabled ? 7 : null,
      language: 'es' as const,
    }
    const stored = { ...payload, ai_available: true }
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify(stored)))
    vi.stubGlobal('fetch', fetchMock)

    await expect(putImportSummarySettings(payload)).resolves.toEqual(stored)

    const [url, options] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/notifications/import-summary-settings')
    expect(options?.method).toBe('PUT')
    expect(options?.credentials).toBe('same-origin')
    expect(new Headers(options?.headers).get('Content-Type')).toBe('application/json')
    expect(options?.body).toBe(JSON.stringify(payload))
  })

  it.each([false, true])('sends a retry as JSON with acknowledgeUncertain=%s', async acknowledgeUncertain => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(new Response('{}'))
    vi.stubGlobal('fetch', fetchMock)

    await retryImportSummary(3, acknowledgeUncertain)

    const [url, options] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/notifications/import-summaries/3/retry')
    expect(options?.method).toBe('POST')
    expect(options?.credentials).toBe('same-origin')
    expect(new Headers(options?.headers).get('Content-Type')).toBe('application/json')
    expect(options?.body).toBe(JSON.stringify({ acknowledge_uncertain: acknowledgeUncertain }))
  })
})
