function pad2(n: number): string {
  return String(n).padStart(2, '0')
}

/**
 * `YYYY-MM-DD` for the LOCAL calendar day of `d`.
 *
 * Never `toISOString().slice(0, 10)`: it converts to UTC first, so in Spain it
 * returns yesterday between midnight and 02:00, and a local midnight such as
 * `new Date(y, m, 1)` always comes out as the last day of the previous month.
 */
export function isoDate(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
}

/** Today's local date as `YYYY-MM-DD`. */
export function todayIso(): string {
  return isoDate(new Date())
}

/** Local midnight `n` calendar days after `d`, so a DST change cannot skip or repeat a day. */
export function addDays(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n)
}
