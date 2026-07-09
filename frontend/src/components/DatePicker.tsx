import { useState, useEffect, useRef, useCallback } from 'react'
import type { CSSProperties, KeyboardEvent } from 'react'
import { useT } from '../i18n'
import type { Lang } from '../i18n'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function parseDate(iso: string): { year: number; month: number; day: number } | null {
  if (!iso) return null
  const parts = iso.split('-').map(Number)
  const [y, m, d] = parts
  if (!y || !m || !d || m < 1 || m > 12 || d < 1 || d > 31) return null
  return { year: y, month: m, day: d }
}

function toISO(year: number, month: number, day: number): string {
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

function formatTriggerDate(year: number, month: number, day: number, lang: Lang): string {
  return new Intl.DateTimeFormat(lang === 'es' ? 'es-ES' : 'en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  }).format(new Date(year, month - 1, day))
}

function getWeekdayNames(lang: Lang): string[] {
  // 2024-01-01 is a Monday — use 7 consecutive days for Mon–Sun
  const locale = lang === 'es' ? 'es-ES' : 'en-GB'
  return Array.from({ length: 7 }, (_, i) =>
    new Intl.DateTimeFormat(locale, { weekday: 'short' }).format(new Date(2024, 0, 1 + i)),
  )
}

function formatPanelHeader(year: number, month: number, lang: Lang): string {
  return new Intl.DateTimeFormat(lang === 'es' ? 'es-ES' : 'en-GB', {
    month: 'long',
    year: 'numeric',
  }).format(new Date(year, month - 1, 1))
}

interface DayCell {
  year: number
  month: number
  day: number
  isCurrentMonth: boolean
}

function buildGrid(year: number, month: number): DayCell[] {
  const firstDay = new Date(year, month - 1, 1)
  const firstDow = (firstDay.getDay() + 6) % 7 // 0 = Mon … 6 = Sun

  let prevMonth = month - 1, prevYear = year
  if (prevMonth < 1) { prevMonth = 12; prevYear-- }
  const daysInPrevMonth = new Date(prevYear, prevMonth, 0).getDate()

  let nextMonth = month + 1, nextYear = year
  if (nextMonth > 12) { nextMonth = 1; nextYear++ }

  const daysInMonth = new Date(year, month, 0).getDate()
  const cells: DayCell[] = []

  for (let i = firstDow - 1; i >= 0; i--)
    cells.push({ year: prevYear, month: prevMonth, day: daysInPrevMonth - i, isCurrentMonth: false })

  for (let d = 1; d <= daysInMonth; d++)
    cells.push({ year, month, day: d, isCurrentMonth: true })

  let d = 1
  while (cells.length < 42)
    cells.push({ year: nextYear, month: nextMonth, day: d++, isCurrentMonth: false })

  return cells
}

function cmpDate(y1: number, m1: number, d1: number, y2: number, m2: number, d2: number): number {
  return y1 !== y2 ? y1 - y2 : m1 !== m2 ? m1 - m2 : d1 - d2
}

// ─── Props ────────────────────────────────────────────────────────────────────

interface DatePickerProps {
  value: string            // YYYY-MM-DD or ''
  onChange: (v: string) => void
  min?: string             // YYYY-MM-DD
  max?: string             // YYYY-MM-DD
  ariaLabel?: string
  placeholder?: string
  disabled?: boolean
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function DatePicker({ value, onChange, min, max, ariaLabel, placeholder, disabled }: DatePickerProps) {
  const { t, lang } = useT()

  const today  = new Date()
  const todayY = today.getFullYear()
  const todayM = today.getMonth() + 1
  const todayD = today.getDate()

  const parsed   = parseDate(value)
  const selYear  = parsed?.year  ?? 0
  const selMonth = parsed?.month ?? 0
  const selDay   = parsed?.day   ?? 0

  const [open,       setOpen]       = useState(false)
  const [viewYear,   setViewYear]   = useState(selYear  || todayY)
  const [viewMonth,  setViewMonth]  = useState(selMonth || todayM)
  const [focusedIdx, setFocusedIdx] = useState<number>(0)
  const [panelStyle, setPanelStyle] = useState<CSSProperties>({})

  const triggerRef        = useRef<HTMLButtonElement>(null)
  const panelRef          = useRef<HTMLDivElement>(null)
  const cellRefs          = useRef<(HTMLButtonElement | null)[]>(new Array(42).fill(null))
  const focusCellOnRender = useRef(false)

  // ── Disabled-day check ───────────────────────────────────────────────────────

  const isDisabledDay = useCallback((year: number, month: number, day: number): boolean => {
    if (min) {
      const mp = parseDate(min)
      if (mp && cmpDate(year, month, day, mp.year, mp.month, mp.day) < 0) return true
    }
    if (max) {
      const xp = parseDate(max)
      if (xp && cmpDate(year, month, day, xp.year, xp.month, xp.day) > 0) return true
    }
    return false
  }, [min, max])

  // ── Open / close ─────────────────────────────────────────────────────────────

  function openPicker() {
    if (disabled) return
    if (triggerRef.current) {
      const r       = triggerRef.current.getBoundingClientRect()
      const PANEL_H = 360
      const PANEL_W = 284
      let top  = r.bottom + 4
      let left = r.left
      if (top + PANEL_H > window.innerHeight) top = r.top - PANEL_H - 4
      if (left + PANEL_W > window.innerWidth) left = window.innerWidth - PANEL_W - 8
      setPanelStyle({ top, left })
    }
    const initYear  = selYear  || todayY
    const initMonth = selMonth || todayM
    const initDay   = selDay   || todayD
    setViewYear(initYear)
    setViewMonth(initMonth)
    const initGrid       = buildGrid(initYear, initMonth)
    const selectedIdx    = initGrid.findIndex(c => c.year === initYear && c.month === initMonth && c.day === initDay)
    const firstCurrentIdx = initGrid.findIndex(c => c.isCurrentMonth)
    setFocusedIdx(selectedIdx >= 0 ? selectedIdx : firstCurrentIdx >= 0 ? firstCurrentIdx : 0)
    focusCellOnRender.current = true
    setOpen(true)
  }

  function closePicker() {
    setOpen(false)
    triggerRef.current?.focus()
  }

  function selectDay(year: number, month: number, day: number) {
    if (isDisabledDay(year, month, day)) return
    onChange(toISO(year, month, day))
    closePicker()
  }

  // ── Month navigation (button clicks — don't steal focus) ──────────────────────

  function goPrevMonth() {
    if (viewMonth === 1) { setViewYear(y => y - 1); setViewMonth(12) }
    else setViewMonth(m => m - 1)
  }

  function goNextMonth() {
    if (viewMonth === 12) { setViewYear(y => y + 1); setViewMonth(1) }
    else setViewMonth(m => m + 1)
  }

  // ── Focus management: steal focus to cell after keyboard nav or open ──────────

  useEffect(() => {
    if (open && focusCellOnRender.current) {
      focusCellOnRender.current = false
      const idx   = focusedIdx
      const timer = setTimeout(() => { cellRefs.current[idx]?.focus() }, 0)
      return () => clearTimeout(timer)
    }
  }, [open, focusedIdx, viewYear, viewMonth])

  // ── Click outside to close ────────────────────────────────────────────────────

  useEffect(() => {
    if (!open) return
    function handleMouseDown(e: MouseEvent) {
      if (
        panelRef.current && !panelRef.current.contains(e.target as Node) &&
        triggerRef.current && !triggerRef.current.contains(e.target as Node)
      ) setOpen(false)
    }
    document.addEventListener('mousedown', handleMouseDown)
    return () => document.removeEventListener('mousedown', handleMouseDown)
  }, [open])

  // ── Keyboard navigation ───────────────────────────────────────────────────────

  function handleKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const grid    = buildGrid(viewYear, viewMonth)
    const current = (focusedIdx >= 0 && focusedIdx < 42) ? grid[focusedIdx] : null

    function moveTo(newY: number, newM: number, newD: number) {
      const sameView  = (newY === viewYear && newM === viewMonth)
      if (!sameView) { setViewYear(newY); setViewMonth(newM) }
      const targetGrid = sameView ? grid : buildGrid(newY, newM)
      const idx        = targetGrid.findIndex(c => c.year === newY && c.month === newM && c.day === newD)
      setFocusedIdx(idx >= 0 ? idx : 0)
      focusCellOnRender.current = true
    }

    switch (e.key) {
      case 'ArrowLeft': {
        e.preventDefault()
        if (current) {
          const d = new Date(current.year, current.month - 1, current.day - 1)
          moveTo(d.getFullYear(), d.getMonth() + 1, d.getDate())
        }
        break
      }
      case 'ArrowRight': {
        e.preventDefault()
        if (current) {
          const d = new Date(current.year, current.month - 1, current.day + 1)
          moveTo(d.getFullYear(), d.getMonth() + 1, d.getDate())
        }
        break
      }
      case 'ArrowUp': {
        e.preventDefault()
        if (current) {
          const d = new Date(current.year, current.month - 1, current.day - 7)
          moveTo(d.getFullYear(), d.getMonth() + 1, d.getDate())
        }
        break
      }
      case 'ArrowDown': {
        e.preventDefault()
        if (current) {
          const d = new Date(current.year, current.month - 1, current.day + 7)
          moveTo(d.getFullYear(), d.getMonth() + 1, d.getDate())
        }
        break
      }
      case 'PageUp': {
        e.preventDefault()
        let newY = viewYear, newM = viewMonth - 1
        if (newM < 1) { newM = 12; newY-- }
        setViewYear(newY); setViewMonth(newM)
        if (current) {
          const maxD = new Date(newY, newM, 0).getDate()
          const newD = Math.min(current.isCurrentMonth ? current.day : 1, maxD)
          const ng   = buildGrid(newY, newM)
          const idx  = ng.findIndex(c => c.year === newY && c.month === newM && c.day === newD)
          setFocusedIdx(idx >= 0 ? idx : 0)
        }
        focusCellOnRender.current = true
        break
      }
      case 'PageDown': {
        e.preventDefault()
        let newY = viewYear, newM = viewMonth + 1
        if (newM > 12) { newM = 1; newY++ }
        setViewYear(newY); setViewMonth(newM)
        if (current) {
          const maxD = new Date(newY, newM, 0).getDate()
          const newD = Math.min(current.isCurrentMonth ? current.day : 1, maxD)
          const ng   = buildGrid(newY, newM)
          const idx  = ng.findIndex(c => c.year === newY && c.month === newM && c.day === newD)
          setFocusedIdx(idx >= 0 ? idx : 0)
        }
        focusCellOnRender.current = true
        break
      }
      case 'Enter':
      case ' ': {
        const target = e.target as HTMLElement
        if (target.classList.contains('day-cell') && !target.classList.contains('is-disabled')) {
          e.preventDefault()
          if (current) selectDay(current.year, current.month, current.day)
        }
        break
      }
      case 'Escape': {
        e.preventDefault()
        closePicker()
        break
      }
    }
  }

  // ── Derived values ────────────────────────────────────────────────────────────

  const grid         = open ? buildGrid(viewYear, viewMonth) : []
  const weekdays     = getWeekdayNames(lang)
  const panelTitle   = formatPanelHeader(viewYear, viewMonth, lang)
  const formattedVal = selYear ? formatTriggerDate(selYear, selMonth, selDay, lang) : ''

  const isTodaySelected = selYear === todayY && selMonth === todayM && selDay === todayD
  const isTodayDisabled = isDisabledDay(todayY, todayM, todayD)

  // Nav arrow disabled states (disable if the entire target month is beyond bounds)
  let prevMonthDis = false
  if (min) {
    const mp = parseDate(min)
    if (mp) {
      let pY = viewYear, pM = viewMonth - 1
      if (pM < 1) { pM = 12; pY-- }
      const lastOfPrev = new Date(pY, pM, 0).getDate()
      if (cmpDate(pY, pM, lastOfPrev, mp.year, mp.month, mp.day) < 0) prevMonthDis = true
    }
  }
  let nextMonthDis = false
  if (max) {
    const xp = parseDate(max)
    if (xp) {
      let nY = viewYear, nM = viewMonth + 1
      if (nM > 12) { nM = 1; nY++ }
      if (cmpDate(nY, nM, 1, xp.year, xp.month, xp.day) > 0) nextMonthDis = true
    }
  }

  const triggerAriaLabel = ariaLabel
    ? (formattedVal ? `${ariaLabel}: ${formattedVal}` : ariaLabel)
    : (formattedVal ? t.datePickerTriggerLabel(formattedVal) : (placeholder ?? t.datePickerPlaceholder))

  // ── Render ────────────────────────────────────────────────────────────────────

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className={`date-picker-trigger${open ? ' is-open' : ''}`}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={triggerAriaLabel}
        disabled={disabled}
        onClick={open ? closePicker : openPicker}
      >
        <span className="date-picker-trigger__value">
          {formattedVal
            ? formattedVal
            : <span className="date-picker-trigger__placeholder">{placeholder ?? t.datePickerPlaceholder}</span>
          }
        </span>
        <span className="date-picker-trigger__icon" aria-hidden="true">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
            <line x1="16" y1="2" x2="16" y2="6"/>
            <line x1="8" y1="2" x2="8" y2="6"/>
            <line x1="3" y1="10" x2="21" y2="10"/>
          </svg>
        </span>
      </button>

      {open && (
        <div
          ref={panelRef}
          className="picker-panel day-picker-panel"
          role="dialog"
          aria-modal="true"
          aria-label={t.datePickerDialogLabel}
          style={panelStyle}
          onKeyDown={handleKeyDown}
          onBlur={e => {
            const related = e.relatedTarget as Node | null
            if (
              !panelRef.current?.contains(related) &&
              !triggerRef.current?.contains(related)
            ) {
              setTimeout(() => {
                if (!panelRef.current?.contains(document.activeElement)) setOpen(false)
              }, 150)
            }
          }}
        >
          {/* Month/year header */}
          <div className="picker-panel-header">
            <button
              type="button"
              className="picker-nav-btn"
              aria-label={t.datePickerPrevMonth}
              disabled={prevMonthDis}
              onClick={goPrevMonth}
            >‹</button>
            <span className="picker-panel-title">{panelTitle}</span>
            <button
              type="button"
              className="picker-nav-btn"
              aria-label={t.datePickerNextMonth}
              disabled={nextMonthDis}
              onClick={goNextMonth}
            >›</button>
          </div>

          {/* Weekday header row (Mon–Sun) */}
          <div className="day-weekday-header" aria-hidden="true">
            {weekdays.map(wd => (
              <span key={wd} className="day-weekday-cell">{wd}</span>
            ))}
          </div>

          {/* Day grid — 6 rows × 7 columns */}
          <div className="day-grid" role="grid" aria-label={panelTitle}>
            {grid.map((cell, idx) => {
              const isSelected = selYear !== 0 &&
                cell.year === selYear && cell.month === selMonth && cell.day === selDay
              const isToday    = cell.year === todayY && cell.month === todayM && cell.day === todayD
              const isDisabled = isDisabledDay(cell.year, cell.month, cell.day)
              const isOutside  = !cell.isCurrentMonth

              const cls = [
                'day-cell',
                isSelected             ? 'is-selected' : '',
                isToday && !isSelected ? 'is-today'    : '',
                isDisabled             ? 'is-disabled' : '',
                isOutside              ? 'is-outside'  : '',
              ].filter(Boolean).join(' ')

              const cellLabel = new Intl.DateTimeFormat(lang === 'es' ? 'es-ES' : 'en-GB', {
                day: 'numeric', month: 'long', year: 'numeric',
              }).format(new Date(cell.year, cell.month - 1, cell.day))

              return (
                <button
                  key={`${cell.year}-${cell.month}-${cell.day}`}
                  ref={el => { cellRefs.current[idx] = el }}
                  type="button"
                  role="gridcell"
                  className={cls}
                  aria-selected={isSelected}
                  aria-disabled={isDisabled}
                  aria-label={cellLabel}
                  tabIndex={idx === focusedIdx ? 0 : -1}
                  onClick={() => {
                    if (!isDisabled) {
                      if (!cell.isCurrentMonth) {
                        // Outside-month day → jump view to that month, then select
                        setViewYear(cell.year)
                        setViewMonth(cell.month)
                      }
                      selectDay(cell.year, cell.month, cell.day)
                    }
                  }}
                  onFocus={() => setFocusedIdx(idx)}
                >
                  {cell.day}
                </button>
              )
            })}
          </div>

          {/* Today shortcut */}
          <button
            type="button"
            className={`picker-today-btn${(isTodaySelected || isTodayDisabled) ? ' is-hidden' : ''}`}
            onClick={() => selectDay(todayY, todayM, todayD)}
          >
            {t.datePickerToday}
          </button>
        </div>
      )}
    </>
  )
}
