// Pure helpers for period comparison — no side effects, unit-testable.

import type { Overview, CategorySummary } from '../api/types'

function pad(n: number): string { return String(n).padStart(2, '0') }
function ymd(d: Date): string { return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` }

/**
 * Returns the full calendar month immediately before the month of `from`.
 * E.g. from="2026-07-15" → { from: "2026-06-01", to: "2026-06-30" }.
 * Returns null for missing or invalid input (graceful degradation for non-standard ranges).
 */
export function previousCalendarMonth(from: string): { from: string; to: string } | null {
  if (!from) return null
  try {
    const parts = from.split('-')
    const y = Number(parts[0])
    const m = Number(parts[1])
    if (!y || !m || m < 1 || m > 12) return null
    const first = new Date(y, m - 2, 1)    // 0-indexed: m-1 is current, m-2 is previous
    const last  = new Date(y, m - 1, 0)    // day 0 of month m-1 = last day of month m-2
    return { from: ymd(first), to: ymd(last) }
  } catch {
    return null
  }
}

/** Signed difference + percentage change between two values. */
export interface DeltaResult {
  /** current − previous (signed; positive = increase). */
  abs: number
  /** Percentage change; null when previous = 0 and current ≠ 0 (render "NEW"). */
  pct: number | null
  /** true when pct is null (previous = 0, current > 0). */
  isNew: boolean
}

/**
 * Compute signed delta between current and previous value.
 * Returns null when previous is null/undefined — caller should render "—" or hide the badge.
 */
export function computeDelta(
  current: number,
  previous: number | null | undefined,
): DeltaResult | null {
  if (previous === null || previous === undefined) return null
  const abs = current - previous
  if (previous === 0) {
    return { abs, pct: null, isNew: current !== 0 }
  }
  return { abs, pct: (abs / previous) * 100, isNew: false }
}

/**
 * Savings rate as a percentage (0–100+). Returns null when income ≤ 0.
 *
 * Assumption: uses total_income as reported by the overview (gross inflows —
 * no refund/correction netting is applied). Zero or negative income → undefined
 * savings rate. If this assumption needs revisiting, update Shuri's overview
 * endpoint to separate refunds.
 */
export function savingsRate(o: Overview): number | null {
  if (o.total_income <= 0) return null
  return (o.net / o.total_income) * 100
}

export interface MoverRow {
  category: string
  category_id: number
  current: number
  /** null = category absent from previous period (effectively 0, displayed as "—"). */
  previous: number | null
  delta: DeltaResult | null
}

/**
 * Select top `n` categories by absolute € change between current and previous periods.
 * Returns an empty array when previous is empty (no previous-period data to compare).
 * Categories absent from previous are treated as previous = 0 (renders as "NEW").
 */
export function selectTopMovers(
  current: CategorySummary[],
  previous: CategorySummary[],
  n = 5,
): MoverRow[] {
  if (previous.length === 0) return []

  const prevMap = new Map(previous.map(p => [p.category_id, p.amount]))
  const seen = new Set<number>()
  const rows: MoverRow[] = []

  for (const c of current) {
    seen.add(c.category_id)
    // If category absent from previous, treat as 0 (new category this month → "NEW")
    const prevAmt = prevMap.get(c.category_id) ?? 0
    rows.push({
      category: c.category,
      category_id: c.category_id,
      current: c.amount,
      previous: prevMap.has(c.category_id) ? prevAmt : null,
      delta: computeDelta(c.amount, prevAmt),
    })
  }

  // Categories present in previous but absent from current (dropped to 0 this month)
  for (const p of previous) {
    if (!seen.has(p.category_id)) {
      rows.push({
        category: p.category,
        category_id: p.category_id,
        current: 0,
        previous: p.amount,
        delta: computeDelta(0, p.amount),
      })
    }
  }

  rows.sort((a, b) => Math.abs(b.delta?.abs ?? 0) - Math.abs(a.delta?.abs ?? 0))

  return rows.slice(0, n)
}
