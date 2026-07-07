// ─── Date range helpers ───────────────────────────────────────────────────────

function pad(n: number) { return String(n).padStart(2, '0') }
function ymd(d: Date) { return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` }

/** Returns {from, to} spanning the whole previous calendar month, using local date parts. */
export function defaultRange(): { from: string; to: string } {
  const now = new Date()
  const first = new Date(now.getFullYear(), now.getMonth() - 1, 1)
  const last  = new Date(now.getFullYear(), now.getMonth(), 0)
  return { from: ymd(first), to: ymd(last) }
}
