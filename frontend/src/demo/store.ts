/** In-memory demo store.
 *
 * One list of transactions is the single source of truth: the ledger, every KPI,
 * every chart and every `tx_count` are derived from it on each request. That is
 * the whole point of this file — the old `api/mock.ts` returned aggregates from
 * frozen constants while edits went to separate mutable arrays, so a change made
 * in the UI never showed up in the totals.
 *
 * Filter semantics mirror `src/finlytics/db/queries.py::_apply_filters`:
 *   · `from`/`to`/`day` compare ISO dates inclusively
 *   · `tags` matches ANY of the given tags (SQL `IN`), not all of them
 *   · `amount_min`/`amount_max` compare the ABSOLUTE amount
 *   · `description`/`merchant` are case-insensitive substring matches
 *   · `flow=expense` is `amount < 0`, `flow=income` is `amount > 0`
 *
 * State lives in module scope and is intentionally NOT persisted: a reload gives
 * every visitor the same clean scenario back.
 */

import type {
  Account, AccountSummary, CashflowSummary, Category, CategorySummary,
  CombinedOverview, DaySummary, FidelityEvolution, FidelityKpis, FidelityLots,
  FidelityReminderResponse, InvestmentConnection, InvestmentPortfolio,
  MerchantSummary, MonthSummary, Overview, SummaryMonths,
  Tag, Transaction, TransactionPage, TransactionPatch,
} from '../api/types'
import { buildScenario } from './scenario'

const scenario = buildScenario()

/** Newest-first, matching the API's default `sort=date&order=desc`. */
let transactions: Transaction[] = scenario.transactions

// ─── Filtering ────────────────────────────────────────────────────────────────

export interface Filters {
  from?: string
  to?: string
  day?: string
  account_id?: number
  category_id?: number
  tags?: string[]
  flow?: string
  description?: string
  amount_min?: number
  amount_max?: number
  merchant?: string
}

function accountNameById(id: number): string | undefined {
  return scenario.accounts.find(a => a.id === id)?.name
}

function categoryNameById(id: number): string | undefined {
  return scenario.categories.find(c => c.id === id)?.name
}

function includesCI(haystack: string | null | undefined, needle: string): boolean {
  if (!haystack) return false
  return haystack.toLowerCase().includes(needle.trim().toLowerCase())
}

export function applyFilters(rows: Transaction[], f: Filters): Transaction[] {
  const accountName = f.account_id !== undefined ? accountNameById(f.account_id) : undefined
  const categoryName = f.category_id !== undefined ? categoryNameById(f.category_id) : undefined
  const wantedTags = f.tags?.map(t => t.trim().toLowerCase()).filter(Boolean) ?? []

  return rows.filter(tx => {
    if (tx.is_system) return false
    if (f.from && tx.transaction_date < f.from) return false
    if (f.to && tx.transaction_date > f.to) return false
    if (f.day && tx.transaction_date !== f.day) return false
    // An unknown account_id/category_id must match nothing, not everything.
    if (f.account_id !== undefined && tx.account !== accountName) return false
    if (f.category_id !== undefined && tx.category !== categoryName) return false
    if (wantedTags.length > 0) {
      const own = tx.tags.map(t => t.toLowerCase())
      if (!wantedTags.some(t => own.includes(t))) return false
    }
    if (f.flow === 'expense' && tx.amount >= 0) return false
    if (f.flow === 'income' && tx.amount <= 0) return false
    if (f.description?.trim() && !includesCI(tx.description, f.description)) return false
    if (f.merchant?.trim() && !includesCI(tx.merchant, f.merchant)) return false
    if (f.amount_min !== undefined && Math.abs(tx.amount) < f.amount_min) return false
    if (f.amount_max !== undefined && Math.abs(tx.amount) > f.amount_max) return false
    return true
  })
}

// ─── Rounding ─────────────────────────────────────────────────────────────────

/** Summing floats accumulates error; every aggregate is rounded to cents. */
function cents(n: number): number {
  return Math.round(n * 100) / 100
}

// ─── Reference lists (tx_count derived live) ──────────────────────────────────

export function listAccounts(): Account[] {
  return scenario.accounts.map(a => ({
    ...a,
    tx_count: transactions.filter(t => t.account === a.name).length,
  }))
}

export function listCategories(): Category[] {
  return scenario.categories.map(c => ({
    ...c,
    tx_count: transactions.filter(t => t.category === c.name).length,
  }))
}

export function listTags(): Tag[] {
  return scenario.tags.map(t => ({
    ...t,
    tx_count: transactions.filter(tx => tx.tags.includes(t.name)).length,
  }))
}

// ─── Transactions ─────────────────────────────────────────────────────────────

const SORT_KEYS = ['date', 'amount', 'description', 'merchant', 'category', 'account'] as const
type SortKey = typeof SORT_KEYS[number]

function sortValue(tx: Transaction, key: SortKey): string | number | null {
  switch (key) {
    case 'amount': return tx.amount
    case 'description': return tx.description
    case 'merchant': return tx.merchant
    case 'category': return tx.category
    case 'account': return tx.account
    case 'date': return tx.transaction_date
  }
}

export function listTransactions(
  f: Filters,
  opts: { limit?: number; offset?: number; sort?: string; order?: string } = {},
): TransactionPage {
  const filtered = applyFilters(transactions, f)

  const key: SortKey = (SORT_KEYS as readonly string[]).includes(opts.sort ?? '')
    ? opts.sort as SortKey
    : 'date'
  const dir = opts.order === 'asc' ? 1 : -1

  const sorted = [...filtered].sort((a, b) => {
    const av = sortValue(a, key)
    const bv = sortValue(b, key)
    // NULLS LAST regardless of direction, matching the backend's nullslast().
    if (av === null && bv === null) return b.id - a.id
    if (av === null) return 1
    if (bv === null) return -1
    let cmp: number
    if (typeof av === 'number' && typeof bv === 'number') cmp = av - bv
    else cmp = String(av).localeCompare(String(bv))
    // Stable secondary sort on id desc, as the backend does.
    return cmp !== 0 ? cmp * dir : b.id - a.id
  })

  const limit = opts.limit ?? 50
  const offset = opts.offset ?? 0
  return { items: sorted.slice(offset, offset + limit), total: sorted.length, limit, offset }
}

/** Applies a patch in place and returns the updated row, or null when unknown. */
export function patchTransaction(id: number, patch: TransactionPatch): Transaction | null {
  const idx = transactions.findIndex(t => t.id === id)
  if (idx === -1) return null

  const current = transactions[idx]
  const updated: Transaction = {
    ...current,
    ...(patch.description !== undefined ? { description: patch.description } : {}),
    ...(patch.category !== undefined ? { category: patch.category } : {}),
    ...(patch.amount !== undefined ? { amount: cents(patch.amount) } : {}),
    ...(patch.tags !== undefined ? { tags: [...patch.tags] } : {}),
    ...(patch.merchant !== undefined ? { merchant: patch.merchant } : {}),
  }
  transactions = [...transactions.slice(0, idx), updated, ...transactions.slice(idx + 1)]
  return updated
}

// ─── Aggregates ───────────────────────────────────────────────────────────────

export function overview(f: Filters): Overview {
  const rows = applyFilters(transactions, f)
  const expense = rows.filter(t => t.amount < 0).reduce((sum, t) => sum - t.amount, 0)
  const income = rows.filter(t => t.amount > 0).reduce((sum, t) => sum + t.amount, 0)

  const byCategory = new Map<string, number>()
  for (const t of rows) {
    if (t.amount >= 0) continue
    byCategory.set(t.category, (byCategory.get(t.category) ?? 0) - t.amount)
  }
  const top = [...byCategory.entries()].sort((a, b) => b[1] - a[1])[0]

  return {
    total_expense: cents(expense),
    total_income: cents(income),
    net: cents(income - expense),
    num_transactions: rows.length,
    top_category: top ? { name: top[0], amount: cents(top[1]) } : null,
    currency: 'EUR',
  }
}

/** Expenses only, grouped by category, biggest first (backend parity). */
export function byCategory(f: Filters): CategorySummary[] {
  const rows = applyFilters(transactions, f).filter(t => t.amount < 0)
  const acc = new Map<string, { amount: number; count: number }>()
  for (const t of rows) {
    const cur = acc.get(t.category) ?? { amount: 0, count: 0 }
    acc.set(t.category, { amount: cur.amount - t.amount, count: cur.count + 1 })
  }
  return [...acc.entries()]
    .map(([category, v]) => ({
      category,
      category_id: scenario.categories.find(c => c.name === category)?.id ?? 0,
      amount: cents(v.amount),
      count: v.count,
    }))
    .sort((a, b) => b.amount - a.amount)
}

/** Shared expense/income/net bucketing used by the month, day and account views. */
function bucket<K extends string>(
  rows: Transaction[],
  keyOf: (tx: Transaction) => K,
): Map<K, { expense: number; income: number }> {
  const acc = new Map<K, { expense: number; income: number }>()
  for (const t of rows) {
    const k = keyOf(t)
    const cur = acc.get(k) ?? { expense: 0, income: 0 }
    if (t.amount < 0) cur.expense -= t.amount
    else cur.income += t.amount
    acc.set(k, cur)
  }
  return acc
}

export function byMonth(f: Filters): MonthSummary[] {
  const acc = bucket(applyFilters(transactions, f), t => t.transaction_date.slice(0, 7))
  return [...acc.entries()]
    .map(([month, v]) => ({
      month,
      expense: cents(v.expense),
      income: cents(v.income),
      net: cents(v.income - v.expense),
    }))
    .sort((a, b) => a.month.localeCompare(b.month))
}

export function byDay(f: Filters): DaySummary[] {
  const acc = bucket(applyFilters(transactions, f), t => t.transaction_date)
  return [...acc.entries()]
    .map(([day, v]) => ({
      day,
      expense: cents(v.expense),
      income: cents(v.income),
      net: cents(v.income - v.expense),
    }))
    .sort((a, b) => a.day.localeCompare(b.day))
}

export function byAccount(f: Filters): AccountSummary[] {
  const acc = bucket(applyFilters(transactions, f), t => t.account)
  return [...acc.entries()]
    .map(([account, v]) => ({
      account,
      expense: cents(v.expense),
      income: cents(v.income),
      net: cents(v.income - v.expense),
      currency: 'EUR',
    }))
    .sort((a, b) => b.expense - a.expense)
}

/** Expenses only, grouped by merchant; rows without a merchant are dropped. */
export function byMerchant(f: Filters): MerchantSummary[] {
  const rows = applyFilters(transactions, f).filter(t => t.amount < 0 && t.merchant?.trim())
  const acc = new Map<string, { amount: number; count: number }>()
  for (const t of rows) {
    const key = t.merchant as string
    const cur = acc.get(key) ?? { amount: 0, count: 0 }
    acc.set(key, { amount: cur.amount - t.amount, count: cur.count + 1 })
  }
  return [...acc.entries()]
    .map(([merchant, v]) => ({ merchant, amount: cents(v.amount), count: v.count }))
    .sort((a, b) => b.amount - a.amount)
}

export function cashflow(f: Filters): CashflowSummary {
  const rows = applyFilters(transactions, f)
  const group = (predicate: (t: Transaction) => boolean, sign: 1 | -1) => {
    const acc = new Map<string, number>()
    for (const t of rows) {
      if (!predicate(t)) continue
      const key = t.category || 'Other'
      acc.set(key, (acc.get(key) ?? 0) + sign * t.amount)
    }
    return [...acc.entries()]
      .map(([category, amount]) => ({ category, amount: cents(amount) }))
      .sort((a, b) => b.amount - a.amount)
  }

  const income = group(t => t.amount > 0, 1)
  const expense = group(t => t.amount < 0, -1)

  return {
    income,
    expense,
    total_income: cents(income.reduce((a, b) => a + b.amount, 0)),
    total_expense: cents(expense.reduce((a, b) => a + b.amount, 0)),
    currency: 'EUR',
  }
}

/** Every month that has at least one transaction, ascending. */
export function summaryMonths(): SummaryMonths {
  const months = [...new Set(
    transactions.filter(t => !t.is_system).map(t => t.transaction_date.slice(0, 7)),
  )].sort()
  return { months, latest: months.length > 0 ? months[months.length - 1] : null }
}

// ─── Investments ──────────────────────────────────────────────────────────────

export function portfolio(): InvestmentPortfolio { return scenario.portfolio }
export function connections(): InvestmentConnection[] { return scenario.connections }
export function combinedOverview(): CombinedOverview { return scenario.combined }

// ─── Fidelity ESPP ────────────────────────────────────────────────────────────

export function esppKpis(): FidelityKpis { return scenario.espp.kpis }
export function esppEvolution(): FidelityEvolution { return scenario.espp.evolution }
export function esppLots(): FidelityLots { return scenario.espp.lots }
export function esppReminder(): FidelityReminderResponse { return scenario.espp.reminder }
