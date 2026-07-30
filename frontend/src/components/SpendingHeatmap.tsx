import { useState, useEffect, useMemo } from 'react'
import type { CSSProperties } from 'react'
import type { DaySummary, GlobalFilters } from '../api/types'
import { getByDay } from '../api/client'
import { useT } from '../i18n'
import type { Lang } from '../i18n'
import { IconAlert, IconLoading, IconCalendar } from './icons'

interface Props {
  globalFilters: GlobalFilters
  onSelectPeriod: (from: string, to: string) => void
  onResetPeriod?: () => void
  refreshKey?: number
}

// ─── Date utilities ────────────────────────────────────────────────────────────

function pad2(n: number) { return String(n).padStart(2, '0') }

function toDateStr(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
}

function parseDate(s: string): Date {
  const [y, m, d] = s.split('-').map(Number)
  return new Date(y, m - 1, d)
}

// JS getDay(): 0=Sun…6=Sat  →  Mon-first index: Mon=0…Sun=6
function toMon1(jsDay: number): number { return (jsDay + 6) % 7 }

function mondayOnOrBefore(d: Date): Date {
  const r = new Date(d)
  r.setDate(r.getDate() - toMon1(r.getDay()))
  return r
}

function sundayOnOrAfter(d: Date): Date {
  const r = new Date(d)
  r.setDate(r.getDate() + (6 - toMon1(r.getDay())))
  return r
}

// ─── Grid building ─────────────────────────────────────────────────────────────

interface Cell { date: string | null; expense: number }

function buildWeeks(fromDate: Date, toDate: Date, expMap: Map<string, number>): Cell[][] {
  const start = mondayOnOrBefore(fromDate)
  const end   = sundayOnOrAfter(toDate)
  const weeks: Cell[][] = []
  const cur = new Date(start)
  while (cur <= end) {
    const week: Cell[] = []
    for (let i = 0; i < 7; i++) {
      const s = toDateStr(cur)
      const inRange = cur >= fromDate && cur <= toDate
      week.push({ date: inRange ? s : null, expense: inRange ? (expMap.get(s) ?? 0) : 0 })
      cur.setDate(cur.getDate() + 1)
    }
    weeks.push(week)
  }
  return weeks
}

// ─── Color buckets (0 = zero/empty, 1–4 = intensity of expense) ────────────────

function colorBucket(expense: number, max: number): 0 | 1 | 2 | 3 | 4 {
  if (expense <= 0 || max <= 0) return 0
  const f = expense / max
  if (f < 0.2) return 1
  if (f < 0.4) return 2
  if (f < 0.7) return 3
  return 4
}

// ─── Formatting helpers ────────────────────────────────────────────────────────

function fmtMonthLabel(dateStr: string, lang: Lang): string {
  const d = parseDate(dateStr)
  return new Intl.DateTimeFormat(lang === 'es' ? 'es-ES' : 'en-GB', { month: 'short' }).format(d)
}

function fmtDayTooltip(
  dateStr: string,
  expense: number,
  lang: Lang,
  formatCurrency: (n: number) => string,
): string {
  const d = parseDate(dateStr)
  const label = new Intl.DateTimeFormat(
    lang === 'es' ? 'es-ES' : 'en-GB',
    { day: 'numeric', month: 'short' },
  ).format(d)
  return expense > 0 ? `${label} · ${formatCurrency(expense)}` : label
}

function computeWeekdayLabels(lang: Lang): string[] {
  const fmt = new Intl.DateTimeFormat(lang === 'es' ? 'es-ES' : 'en-GB', { weekday: 'narrow' })
  // 2024-01-01 = Monday → indices 0–6 span Mon–Sun
  return Array.from({ length: 7 }, (_, i) => fmt.format(new Date(2024, 0, 1 + i)))
}

function isMonthInRange(year: number, monthIdx: number, fromStr: string, toStr: string): boolean {
  const key = `${year}-${String(monthIdx + 1).padStart(2, '0')}`
  return key >= fromStr.slice(0, 7) && key <= toStr.slice(0, 7)
}

// ─── Component ─────────────────────────────────────────────────────────────────

export default function SpendingHeatmap({ globalFilters, onSelectPeriod, onResetPeriod, refreshKey = 0 }: Props) {
  const { t, lang, formatCurrency } = useT()
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)
  const [data, setData]       = useState<DaySummary[]>([])

  useEffect(() => {
    setLoading(true)
    setError(null)
    // byDay: pass merchant (+ existing incl. category_id). Do NOT pass day (it's the source).
    getByDay({
      from:        globalFilters.from  || undefined,
      to:          globalFilters.to    || undefined,
      account_id:  globalFilters.account_id,
      category_id: globalFilters.category_id,
      tags:        globalFilters.tags.length > 0 ? globalFilters.tags : undefined,
      flow:        globalFilters.flow,
      merchant:    globalFilters.merchant,
    })
      .then(rows => { setData(rows); setLoading(false) })
      .catch(e   => { setError(String(e)); setLoading(false) })
  }, [globalFilters, refreshKey])

  const grid = useMemo(() => {
    if (data.length === 0) return null

    const expMap   = new Map(data.map(d => [d.day, d.expense]))
    const fromStr  = globalFilters.from || data[0].day
    const toStr    = globalFilters.to   || data[data.length - 1].day
    const fromDate = parseDate(fromStr)
    const toDate   = parseDate(toStr)

    const weeks  = buildWeeks(fromDate, toDate, expMap)
    const maxExp = Math.max(0, ...data.map(d => d.expense))

    // One month label per week column, placed at the first week of each new month
    const monthCols = new Array<string>(weeks.length).fill('')
    let prevMonth   = -1
    for (let wi = 0; wi < weeks.length; wi++) {
      const first = weeks[wi].find(c => c.date !== null)
      if (!first?.date) continue
      const mo = parseInt(first.date.slice(5, 7))
      if (mo !== prevMonth) {
        monthCols[wi] = fmtMonthLabel(first.date, lang)
        prevMonth = mo
      }
    }

    // Flat cell list in CSS grid row-major order: dayIdx (0=Mon) outer, weekIdx inner
    const cells = Array.from({ length: 7 }, (_, dayIdx) =>
      weeks.map((week, weekIdx) => {
        const cell = week[dayIdx] ?? { date: null, expense: 0 }
        return { ...cell, weekIdx, dayIdx }
      })
    ).flat()

    return { weeks, maxExp, monthCols, cells, wdLabels: computeWeekdayLabels(lang) }
  }, [data, globalFilters.from, globalFilters.to, lang])

  // ── Mode detection (3 adaptive modes by totalDays) ─────────────────────────
  const totalDays = useMemo(() => {
    if (data.length === 0) return 0
    const fromStr = globalFilters.from || data[0].day
    const toStr   = globalFilters.to   || data[data.length - 1].day
    return Math.round((parseDate(toStr).getTime() - parseDate(fromStr).getTime()) / 86_400_000) + 1
  }, [data, globalFilters.from, globalFilters.to])

  const mode: 'daily' | 'compact' | 'monthly' =
    totalDays <= 182 ? 'daily'
    : totalDays <= 547 ? 'compact'
    : 'monthly'

  // ── Adaptive sizes for daily + compact ────────────────────────────────────
  const weekCount = grid ? grid.weeks.length : 52
  const cellPx    = mode === 'compact' ? 11
    : weekCount <= 6  ? 20
    : weekCount <= 12 ? 18
    : weekCount <= 26 ? 16
    : 14
  const gapPx     = mode === 'compact' ? 2 : 3
  const radiusPx  = mode === 'compact' ? 2 : weekCount <= 6 ? 4 : weekCount <= 12 ? 3 : 2

  // ── Monthly grid data (mode C: > 18 months) ───────────────────────────────
  const monthGrid = useMemo(() => {
    if (mode !== 'monthly' || !grid || data.length === 0) return null
    const monthMap = new Map<string, number>()
    for (const row of data) {
      const key = row.day.slice(0, 7)
      monthMap.set(key, (monthMap.get(key) ?? 0) + row.expense)
    }
    const maxMonthExp = Math.max(0, ...monthMap.values())
    const fromStr  = globalFilters.from || data[0].day
    const toStr    = globalFilters.to   || data[data.length - 1].day
    const fromYear = parseInt(fromStr.slice(0, 4))
    const toYear   = parseInt(toStr.slice(0, 4))
    const years    = Array.from({ length: toYear - fromYear + 1 }, (_, i) => fromYear + i)
    return { monthMap, maxMonthExp, years, fromStr, toStr }
  }, [data, mode, globalFilters.from, globalFilters.to, grid])

  // ── Month column labels (Intl, i18n) ──────────────────────────────────────
  const MONTH_LABELS = useMemo(() => {
    const locale = lang === 'es' ? 'es-ES' : 'en-GB'
    const fmt = new Intl.DateTimeFormat(locale, { month: 'short' })
    return Array.from({ length: 12 }, (_, m) => fmt.format(new Date(2024, m, 1)))
  }, [lang])

  const hasData = !loading && !error && data.some(d => d.expense > 0)
  const isEmpty = !loading && !error && !hasData

  return (
    <div className="card heatmap-card">
      <div className={`card-title${onResetPeriod ? ' card-title--has-action' : ''}`}>
        <span>{t.heatmapTitle}</span>
        {onResetPeriod && (
          <button className="hm-reset-btn" onClick={onResetPeriod}>
            {t.heatmapZoomOut}
          </button>
        )}
      </div>

      {error && (
        <div className="state-box error">
          <IconAlert size={18} />
          <span>{error}</span>
        </div>
      )}

      {!error && loading && (
        <div className="state-box">
          <IconLoading size={18} />
          <span>{t.loading}</span>
        </div>
      )}

      {isEmpty && (
        <div className="state-box">
          <IconCalendar size={18} />
          <span>{t.heatmapEmpty}</span>
        </div>
      )}

      {!error && !loading && hasData && grid && (
        <div className="heatmap-outer">

          {mode === 'monthly' && monthGrid ? (
            /* ── Modo C: Monthly Grid (> 18 months) ── */
            <div className="heatmap-month-grid-wrap">
              <div className="heatmap-month-header">
                <div className="hm-year-placeholder" />
                {MONTH_LABELS.map(label => (
                  <div key={label} className="hm-month-col-label">{label}</div>
                ))}
              </div>
              {monthGrid.years.map(year => (
                <div key={year} className="heatmap-month-row">
                  <div className="hm-year-label">{year}</div>
                  {Array.from({ length: 12 }, (_, m) => {
                    const key    = `${year}-${String(m + 1).padStart(2, '0')}`
                    const exp    = monthGrid.monthMap.get(key) ?? 0
                    const isOut  = !isMonthInRange(year, m, monthGrid.fromStr, monthGrid.toStr)
                    const b      = isOut ? 0 : colorBucket(exp, monthGrid.maxMonthExp)
                    const title  = isOut
                      ? undefined
                      : exp > 0 ? `${MONTH_LABELS[m]} ${year} · ${formatCurrency(exp)}` : `${MONTH_LABELS[m]} ${year}`
                    const firstDay = `${year}-${String(m + 1).padStart(2, '0')}-01`
                    const lastDay  = toDateStr(new Date(year, m + 1, 0))
                    return (
                      <div
                        key={m}
                        className={['hm-cell', isOut ? 'hm-cell--out' : `hm-cell--${b}`].join(' ')}
                        title={title}
                        aria-label={title}
                        tabIndex={!isOut ? 0 : undefined}
                        role={!isOut ? 'button' : undefined}
                        onClick={!isOut ? () => onSelectPeriod(firstDay, lastDay) : undefined}
                        onKeyDown={!isOut ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelectPeriod(firstDay, lastDay) } } : undefined}
                      />
                    )
                  })}
                </div>
              ))}

              {/* Legend */}
              <div className="heatmap-legend" style={{ marginLeft: 40 }}>
                <span className="hm-legend-label">{t.heatmapLess}</span>
                {([0, 1, 2, 3, 4] as const).map(b => (
                  <div key={b} className={`hm-cell hm-cell--${b}`} />
                ))}
                <span className="hm-legend-label">{t.heatmapMore}</span>
              </div>
            </div>

          ) : (
            /* ── Modos A/B: Daily / Compact calendar ── */
            <div
              className="heatmap-wrap"
              style={{
                '--hm-cell': `${Math.max(10, cellPx)}px`,
                '--hm-gap': `${gapPx}px`,
                '--hm-radius': `${radiusPx}px`,
              } as CSSProperties}
            >

              {/* Month labels — one per week column */}
              <div
                className="heatmap-months"
                style={{ gridTemplateColumns: `repeat(${grid.weeks.length}, var(--hm-cell))` }}
              >
                {grid.monthCols.map((label, i) => (
                  <div key={i} className="hm-month-label">{label}</div>
                ))}
              </div>

              {/* Weekday labels + cell grid */}
              <div className="heatmap-body">
                <div className="heatmap-weekdays">
                  {grid.wdLabels.map((label, i) => (
                    <div key={i} className="hm-weekday">
                      {/* Only show Mon / Wed / Fri to avoid crowding */}
                      {i % 2 === 0 ? label : ''}
                    </div>
                  ))}
                </div>

                <div
                  className="heatmap-grid"
                  role="grid"
                  aria-label={t.heatmapTitle}
                  style={{ gridTemplateColumns: `repeat(${grid.weeks.length}, var(--hm-cell))` }}
                >
                  {grid.cells.map(({ date, expense, weekIdx, dayIdx }) => {
                    const isOut      = date === null
                    const b          = isOut ? 0 : colorBucket(expense, grid.maxExp)
                    const title      = date ? fmtDayTooltip(date, expense, lang, formatCurrency) : undefined
                    return (
                      <div
                        key={`${weekIdx}-${dayIdx}`}
                        className={[
                          'hm-cell',
                          isOut ? 'hm-cell--out' : `hm-cell--${b}`,
                        ].filter(Boolean).join(' ')}
                        title={title}
                        aria-label={title}
                        tabIndex={(!isOut && date) ? 0 : undefined}
                        role={(!isOut && date) ? 'button' : undefined}
                        onClick={(!isOut && date) ? () => onSelectPeriod(date, date) : undefined}
                        onKeyDown={(!isOut && date) ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelectPeriod(date, date) } } : undefined}
                      />
                    )
                  })}
                </div>
              </div>

              {/* Legend */}
              <div className="heatmap-legend">
                <span className="hm-legend-label">{t.heatmapLess}</span>
                {([0, 1, 2, 3, 4] as const).map(b => (
                  <div key={b} className={`hm-cell hm-cell--${b}`} />
                ))}
                <span className="hm-legend-label">{t.heatmapMore}</span>
              </div>

            </div>
          )}

        </div>
      )}
    </div>
  )
}
