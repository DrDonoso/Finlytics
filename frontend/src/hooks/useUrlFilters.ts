import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router'
import type { TransactionsViewFilters } from '../api/types'
import type { DateRange } from '../utils'

export type FiltersUpdate =
  | TransactionsViewFilters
  | ((prev: TransactionsViewFilters) => TransactionsViewFilters)

const FILTER_KEYS = new Set([
  'from', 'to', 'account_id', 'category_id', 'tag', 'flow', 'merchant', 'q', 'min', 'max', 'day',
])

function isIsoDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const [y, m, d] = value.split('-').map(Number)
  const date = new Date(Date.UTC(y, m - 1, d))
  return date.getUTCFullYear() === y && date.getUTCMonth() === m - 1 && date.getUTCDate() === d
}

function readRangeEnd(params: URLSearchParams, key: 'from' | 'to', fallback: string): string {
  const raw = params.get(key)
  if (raw === null) return fallback
  if (raw === '') return ''
  return isIsoDate(raw) ? raw : fallback
}

function readId(params: URLSearchParams, key: string): number | undefined {
  const raw = params.get(key)
  if (raw === null || !/^\d+$/.test(raw)) return undefined
  const n = Number(raw)
  return Number.isSafeInteger(n) && n > 0 ? n : undefined
}

function readAmount(params: URLSearchParams, key: string): number | undefined {
  const raw = params.get(key)?.trim()
  if (!raw) return undefined
  const n = Number(raw)
  return Number.isFinite(n) && n >= 0 ? n : undefined
}

function readText(params: URLSearchParams, key: string): string | undefined {
  const raw = params.get(key)
  return raw !== null && raw.trim() !== '' ? raw : undefined
}

/**
 * URL → filters. A missing `from`/`to` means the page default; a present but
 * empty one means an open end. Malformed values are dropped, never thrown.
 */
export function parseFilters(params: URLSearchParams, defaults: DateRange): TransactionsViewFilters {
  const filters: TransactionsViewFilters = {
    from: readRangeEnd(params, 'from', defaults.from),
    to:   readRangeEnd(params, 'to', defaults.to),
    tags: [...new Set(params.getAll('tag').filter(tag => tag.trim() !== ''))],
  }
  const accountId = readId(params, 'account_id')
  if (accountId !== undefined) filters.account_id = accountId
  const categoryId = readId(params, 'category_id')
  if (categoryId !== undefined) filters.category_id = categoryId
  const flow = params.get('flow')
  if (flow === 'expense' || flow === 'income') filters.flow = flow
  const merchant = readText(params, 'merchant')
  if (merchant !== undefined) filters.merchant = merchant
  const description = readText(params, 'q')
  if (description !== undefined) filters.description = description
  const amountMin = readAmount(params, 'min')
  if (amountMin !== undefined) filters.amount_min = amountMin
  const amountMax = readAmount(params, 'max')
  if (amountMax !== undefined) filters.amount_max = amountMax
  const day = params.get('day')
  if (day !== null && isIsoDate(day)) filters.day = day
  return filters
}

/**
 * Filters → URL. A customised range writes both ends, so a shared link keeps
 * its period instead of drifting with the page default as the months pass.
 */
export function serializeFilters(filters: TransactionsViewFilters, defaults: DateRange): URLSearchParams {
  const params = new URLSearchParams()
  if (filters.from !== defaults.from || filters.to !== defaults.to) {
    if (filters.from || defaults.from) params.set('from', filters.from)
    if (filters.to || defaults.to) params.set('to', filters.to)
  }
  if (filters.account_id !== undefined) params.set('account_id', String(filters.account_id))
  if (filters.category_id !== undefined) params.set('category_id', String(filters.category_id))
  for (const tag of filters.tags) params.append('tag', tag)
  if (filters.flow) params.set('flow', filters.flow)
  if (filters.merchant) params.set('merchant', filters.merchant)
  if (filters.description) params.set('q', filters.description)
  if (filters.amount_min !== undefined) params.set('min', String(filters.amount_min))
  if (filters.amount_max !== undefined) params.set('max', String(filters.amount_max))
  if (filters.day) params.set('day', filters.day)
  return params
}

/**
 * Filter state kept in the query string, so a reload, the back button or a
 * shared link restores the same view. `makeDefaults` is read once, on mount.
 */
export function useUrlFilters(makeDefaults: () => DateRange) {
  const [searchParams, setSearchParams] = useSearchParams()
  const [defaults] = useState<DateRange>(() => {
    const { from, to } = makeDefaults()
    return { from, to }
  })
  const filters = useMemo(() => parseFilters(searchParams, defaults), [searchParams, defaults])

  // Navigations commit in a transition, so two updates in one tick would both
  // start from the rendered URL and the second would drop the first. Updates
  // therefore compose on the last value written, which the URL adopts only when
  // it actually moves.
  const latest = useRef({ filters, search: searchParams.toString() })
  const seenParams = useRef(searchParams)
  const setParamsRef = useRef(setSearchParams)
  useLayoutEffect(() => {
    setParamsRef.current = setSearchParams
    if (seenParams.current !== searchParams) {
      seenParams.current = searchParams
      latest.current = { filters, search: searchParams.toString() }
    }
  })

  const setFilters = useCallback((next: FiltersUpdate) => {
    const current = latest.current
    const resolved = typeof next === 'function' ? next(current.filters) : next
    const params = serializeFilters(resolved, defaults)
    for (const [key, value] of new URLSearchParams(current.search)) {
      if (!FILTER_KEYS.has(key)) params.append(key, value)
    }
    const search = params.toString()
    if (search === current.search) return
    latest.current = { filters: parseFilters(params, defaults), search }
    setParamsRef.current(params, { replace: true })
  }, [defaults])

  return { filters, setFilters, defaults }
}

type DebouncedKey = 'description' | 'merchant' | 'amount_min' | 'amount_max'

function isAmountKey(key: DebouncedKey): key is 'amount_min' | 'amount_max' {
  return key === 'amount_min' || key === 'amount_max'
}

function normalizeInput(key: DebouncedKey, raw: string): string {
  const trimmed = raw.trim()
  if (!isAmountKey(key) || trimmed === '') return trimmed
  const n = Number(trimmed)
  return Number.isFinite(n) && n >= 0 ? String(n) : ''
}

function withValue(filters: TransactionsViewFilters, key: DebouncedKey, value: string): TransactionsViewFilters {
  const next = { ...filters }
  if (value === '') delete next[key]
  else if (isAmountKey(key)) next[key] = Number(value)
  else next[key] = value
  return next
}

/**
 * Text box bound to one URL filter: the box updates on every keystroke, the
 * filter 300 ms after the last one, and a change made elsewhere (a chip, the
 * clear button, the back button) is written back into the box.
 */
export function useDebouncedFilter(
  filters: TransactionsViewFilters,
  setFilters: (next: FiltersUpdate) => void,
  key: DebouncedKey,
  delay = 300,
): [string, (raw: string) => void] {
  const current = filters[key]
  const committed = current === undefined ? '' : String(current)
  const [raw, setRaw] = useState(committed)
  const expected = useRef(committed)

  useEffect(() => {
    const value = normalizeInput(key, raw)
    if (value === expected.current) return
    const timer = setTimeout(() => {
      expected.current = value
      setFilters(f => withValue(f, key, value))
    }, delay)
    return () => clearTimeout(timer)
  }, [raw, key, delay, setFilters])

  useEffect(() => {
    if (committed === expected.current) return
    expected.current = committed
    setRaw(committed)
  }, [committed])

  return [raw, setRaw]
}
