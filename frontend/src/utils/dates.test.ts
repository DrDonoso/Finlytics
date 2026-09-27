import { afterEach, describe, expect, it, vi } from 'vitest'

import { addDays, isoDate, todayIso } from './dates'

afterEach(() => {
  vi.useRealTimers()
})

describe('isoDate', () => {
  it('keeps a local midnight on its own day', () => {
    expect(isoDate(new Date(2026, 5, 1))).toBe('2026-06-01')
  })

  it('zero-pads month and day', () => {
    expect(isoDate(new Date(2026, 0, 9, 23, 59))).toBe('2026-01-09')
  })
})

describe('todayIso', () => {
  it('answers the local day even when UTC is still on the previous one', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 2, 1, 0, 30))
    expect(todayIso()).toBe('2026-03-01')
  })
})

describe('addDays', () => {
  it('rolls over month and year ends', () => {
    expect(isoDate(addDays(new Date(2025, 11, 31), 1))).toBe('2026-01-01')
    expect(isoDate(addDays(new Date(2026, 2, 1), -1))).toBe('2026-02-28')
  })

  it('returns a new local midnight and leaves the input alone', () => {
    const from = new Date(2026, 2, 28, 15, 45)
    const next = addDays(from, 7)
    expect(isoDate(next)).toBe('2026-04-04')
    expect(next.getHours()).toBe(0)
    expect(isoDate(from)).toBe('2026-03-28')
  })
})
