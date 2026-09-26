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
