/**
 * Period-comparison tests.
 *
 * This is pure logic that drives the change-variance badges on the dashboard,
 * Statements, and category breakdown. A bug here doesn't break anything
 * visibly — it just shows a wrong percentage, which is exactly the kind of
 * failure nobody notices in a finance app.
 */
import { describe, expect, it } from 'vitest'

import type { CategorySummary, Overview } from '../api/types'
import {
  computeDelta,
  previousCalendarMonth,
  savingsRate,
  selectTopMovers,
} from './comparison'

function overview(partial: Partial<Overview> = {}): Overview {
  return {
    total_expense: 0,
    total_income: 0,
    net: 0,
    num_transactions: 0,
    top_category: null,
    currency: 'EUR',
    ...partial,
  }
}

function category(name: string, id: number, amount: number): CategorySummary {
  return { category: name, category_id: id, amount, count: 1 }
}

// ── previousCalendarMonth ────────────────────────────────────────────────────

describe('previousCalendarMonth', () => {
  it('returns the full preceding calendar month', () => {
    expect(previousCalendarMonth('2026-07-15')).toEqual({
      from: '2026-06-01',
      to: '2026-06-30',
    })
  })

  it('crosses the year boundary', () => {
    expect(previousCalendarMonth('2026-01-09')).toEqual({
      from: '2025-12-01',
      to: '2025-12-31',
    })
  })

  it('resolves February of a leap year', () => {
    // 2028 is a leap year: the month before March ends on the 29th.
    expect(previousCalendarMonth('2028-03-01')).toEqual({
      from: '2028-02-01',
      to: '2028-02-29',
    })
  })

  it('resolves February of a non-leap year', () => {
    expect(previousCalendarMonth('2027-03-01')).toEqual({
      from: '2027-02-01',
      to: '2027-02-28',
    })
  })

  it('returns null for unusable inputs', () => {
    expect(previousCalendarMonth('')).toBeNull()
    expect(previousCalendarMonth('not-a-date')).toBeNull()
    expect(previousCalendarMonth('2026-13-01')).toBeNull()
    expect(previousCalendarMonth('2026-00-01')).toBeNull()
  })
})

// ── computeDelta ─────────────────────────────────────────────────────────────

describe('computeDelta', () => {
  it('computes absolute and percentage change', () => {
    expect(computeDelta(120, 100)).toEqual({ abs: 20, pct: 20, isNew: false })
  })

  it('preserves the sign when the value decreases', () => {
    expect(computeDelta(80, 100)).toEqual({ abs: -20, pct: -20, isNew: false })
  })

  it('marks as new what had no prior value', () => {
    // Without a prior reference there is no valid percentage: dividing by zero would produce Infinity and the UI would show "+Infinity %".
    const delta = computeDelta(50, 0)
    expect(delta).toEqual({ abs: 50, pct: null, isNew: true })
  })

  it('does not mark as new what remains at zero', () => {
    expect(computeDelta(0, 0)).toEqual({ abs: 0, pct: null, isNew: false })
  })

  it('returns null when there is no previous period', () => {
    expect(computeDelta(100, null)).toBeNull()
    expect(computeDelta(100, undefined)).toBeNull()
  })

  it('handles a negative baseline correctly', () => {
    // Going from -100 to -50 means spending less, so the absolute delta is positive.
    const delta = computeDelta(-50, -100)
    expect(delta?.abs).toBe(50)
    expect(delta?.pct).toBe(-50)
  })
})

// ── savingsRate ──────────────────────────────────────────────────────────────

describe('savingsRate', () => {
  it('is net over income, expressed as a percentage', () => {
    expect(savingsRate(overview({ total_income: 1000, net: 250 }))).toBe(25)
  })

  it('returns null when income is zero', () => {
    // Without income the rate is undefined; returning 0 would say "you save nothing", which is different from "cannot compute".
    expect(savingsRate(overview({ total_income: 0, net: -100 }))).toBeNull()
    expect(savingsRate(overview({ total_income: -50, net: -100 }))).toBeNull()
  })

  it('accepts negative rates when spending exceeds income', () => {
    expect(savingsRate(overview({ total_income: 1000, net: -200 }))).toBe(-20)
  })
})

// ── selectTopMovers ──────────────────────────────────────────────────────────

describe('selectTopMovers', () => {
  it('sorts by absolute change in euros, not by percentage', () => {
    // Dining is up 900 % but only €90; Housing is up 25 % but €200. The amount is what matters to the user.
    const movers = selectTopMovers(
      [category('Dining', 1, 100), category('Housing', 2, 1000)],
      [category('Dining', 1, 10), category('Housing', 2, 800)],
    )

    expect(movers.map(m => m.category)).toEqual(['Housing', 'Dining'])
  })

  it('accounts for decreases as well as increases', () => {
    const movers = selectTopMovers(
      [category('Dining', 1, 10)],
      [category('Dining', 1, 500)],
    )

    expect(movers[0].delta?.abs).toBe(-490)
  })

  it('returns empty when there is no previous period to compare', () => {
    expect(selectTopMovers([category('Dining', 1, 100)], [])).toEqual([])
  })

  it('includes categories that disappear in the current period', () => {
    // Stopping spending on a category is as informative as starting.
    const movers = selectTopMovers([], [category('Travel', 3, 300)])

    expect(movers).toHaveLength(1)
    expect(movers[0]).toMatchObject({ category: 'Travel', current: 0, previous: 300 })
  })

  it('marks as new categories that did not exist before', () => {
    const movers = selectTopMovers(
      [category('Travel', 3, 300)],
      [category('Dining', 1, 10)],
    )

    const travel = movers.find(m => m.category === 'Travel')
    expect(travel?.previous).toBeNull()
    expect(travel?.delta?.isNew).toBe(true)
  })

  it('respects the requested row limit', () => {
    const current = Array.from({ length: 10 }, (_, i) => category(`c${i}`, i, (i + 1) * 100))
    const previous = Array.from({ length: 10 }, (_, i) => category(`c${i}`, i, 1))

    expect(selectTopMovers(current, previous, 3)).toHaveLength(3)
    expect(selectTopMovers(current, previous)).toHaveLength(5)
  })
})
