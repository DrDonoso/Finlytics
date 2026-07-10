import { useState, useEffect, useMemo } from 'react'
import type { CSSProperties } from 'react'
import type { DaySummary, GlobalFilters } from '../api/types'
import { getByDay } from '../api/client'
import { useT } from '../i18n'
import type { Lang } from '../i18n'

interface Props {
  globalFilters: GlobalFilters
  selectedDay?: string
  onDayClick: (day: string) => void
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

// ─── Component ─────────────────────────────────────────────────────────────────

export default function SpendingHeatmap({ globalFilters, selectedDay, onDayClick, refreshKey = 0 }: Props) {
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

  const hasData = !loading && !error && data.some(d => d.expense > 0)
  const isEmpty = !loading && !error && !hasData

  // Adaptive cell size based on number of week columns
  const weekCount = grid ? grid.weeks.length : 52
  const cellPx   = weekCount <= 6 ? 30 : weekCount <= 12 ? 20 : weekCount <= 26 ? 16 : 14
  const radiusPx = weekCount <= 6 ? 4  : weekCount <= 12 ? 3  : 2

  return (
    <div className="card heatmap-card">
      <div className="card-title">{t.heatmapTitle}</div>

      {error && (
        <div className="state-box error">
          <span className="icon">⚠</span>
          <span>{error}</span>
        </div>
      )}

      {!error && loading && (
        <div className="state-box">
          <span className="icon">⏳</span>
          <span>{t.loading}</span>
        </div>
      )}

      {isEmpty && (
        <div className="state-box">
          <span className="icon">📅</span>
          <span>{t.heatmapEmpty}</span>
        </div>
      )}

      {!error && !loading && hasData && grid && (
        <div className="heatmap-outer">
          <div
            className="heatmap-wrap"
            style={{ '--hm-cell': `${cellPx}px`, '--hm-radius': `${radiusPx}px` } as CSSProperties}
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
                  const isSelected = date !== null && date === selectedDay
                  const title      = date ? fmtDayTooltip(date, expense, lang, formatCurrency) : undefined
                  return (
                    <div
                      key={`${weekIdx}-${dayIdx}`}
                      className={[
                        'hm-cell',
                        isOut ? 'hm-cell--out' : `hm-cell--${b}`,
                        isSelected ? 'hm-cell--selected' : '',
                      ].filter(Boolean).join(' ')}
                      title={title}
                      aria-label={title}
                      aria-pressed={isSelected || undefined}
                      role={!isOut ? 'button' : undefined}
                      onClick={(!isOut && date) ? () => onDayClick(date) : undefined}
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
        </div>
      )}
    </div>
  )
}
