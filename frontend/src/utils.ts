import { isoDate } from './utils/dates'

// ─── Date range helpers ───────────────────────────────────────────────────────

export interface DateRange { from: string; to: string }

export const RANGE_PRESETS = ['thisMonth', 'lastMonth', '3m', 'ytd', '12m', 'all'] as const
export type RangePreset = typeof RANGE_PRESETS[number]

/** Calendar-month ranges built from local date parts; `all` is the open range. Rolling presets end on the last day of the current month, so a preset keeps matching for the whole month. */
export function presetRange(preset: RangePreset, now: Date = new Date()): DateRange {
  const y = now.getFullYear()
  const m = now.getMonth()
  const endOfMonth = isoDate(new Date(y, m + 1, 0))
  switch (preset) {
    case 'thisMonth': return { from: isoDate(new Date(y, m, 1)), to: endOfMonth }
    case 'lastMonth': return { from: isoDate(new Date(y, m - 1, 1)), to: isoDate(new Date(y, m, 0)) }
    case '3m':        return { from: isoDate(new Date(y, m - 2, 1)), to: endOfMonth }
    case 'ytd':       return { from: isoDate(new Date(y, 0, 1)), to: endOfMonth }
    case '12m':       return { from: isoDate(new Date(y, m - 11, 1)), to: endOfMonth }
    case 'all':       return { from: '', to: '' }
  }
}

/**
 * The preset whose range equals `range`, if any. Presets can coincide — in
 * January "this month" is also "year to date" — so `preferred`, the one the
 * user picked, wins whenever it still matches.
 */
export function matchPreset(
  range: DateRange,
  now: Date = new Date(),
  preferred?: RangePreset,
): RangePreset | undefined {
  const matches = (p: RangePreset) => {
    const r = presetRange(p, now)
    return r.from === range.from && r.to === range.to
  }
  if (preferred && matches(preferred)) return preferred
  return RANGE_PRESETS.find(matches)
}

/** Returns {from, to} spanning the whole previous calendar month, using local date parts. */
export function defaultRange(): DateRange {
  return presetRange('lastMonth')
}
