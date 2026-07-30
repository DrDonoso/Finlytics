import { useState, useEffect, useRef, useCallback } from 'react'
import type { CSSProperties, KeyboardEvent } from 'react'
import { useT } from '../i18n'
import type { Lang } from '../i18n'
import { IconChevronDown } from './icons'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function shortMonthName(month: number, lang: Lang): string {
  return new Intl.DateTimeFormat(lang === 'es' ? 'es-ES' : 'en-US', { month: 'short' }).format(
    new Date(2024, month - 1, 1),
  )
}

function formatMonthTrigger(year: number, month: number, lang: Lang): string {
  return new Intl.DateTimeFormat(lang === 'es' ? 'es-ES' : 'en-US', {
    month: 'long',
    year: 'numeric',
  }).format(new Date(year, month - 1, 1))
}

function fullMonthLabel(year: number, month: number, lang: Lang): string {
  return new Intl.DateTimeFormat(lang === 'es' ? 'es-ES' : 'en-US', {
    month: 'long',
    year: 'numeric',
  }).format(new Date(year, month - 1, 1))
}

// ─── Props ────────────────────────────────────────────────────────────────────

interface MonthPickerProps {
  value: string              // YYYY-MM
  onChange: (v: string) => void
  min?: string               // YYYY-MM, optional lower bound
  max?: string               // YYYY-MM, optional upper bound
  /** Months that have data — shown at full opacity; others dimmed */
  activeMonths?: string[]    // YYYY-MM[]
  disabled?: boolean
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function MonthPicker({ value, onChange, min, max, activeMonths, disabled }: MonthPickerProps) {
  const { t, lang } = useT()

  // Parse selected value
  const parts = value ? value.split('-').map(Number) : [0, 0]
  const selYear  = parts[0] ?? 0
  const selMonth = parts[1] ?? 0

  // Today
  const today  = new Date()
  const todayY = today.getFullYear()
  const todayM = today.getMonth() + 1

  const [open,         setOpen]         = useState(false)
  const [panelYear,    setPanelYear]    = useState(selYear || todayY)
  const [focusedMonth, setFocusedMonth] = useState(selMonth || todayM)
  const [panelStyle,   setPanelStyle]   = useState<CSSProperties>({})

  const triggerRef = useRef<HTMLButtonElement>(null)
  const panelRef   = useRef<HTMLDivElement>(null)
  const cellRefs   = useRef<(HTMLButtonElement | null)[]>(Array.from({ length: 12 }, () => null))

  // Flag: only steal focus to month cell when opening or using keyboard nav
  const focusCellOnRender = useRef(false)

  // ── Min/max helpers ─────────────────────────────────────────────────────────

  const isDisabledMonth = useCallback((year: number, month: number): boolean => {
    const ym = year * 100 + month
    if (min) {
      const [mnY, mnM] = min.split('-').map(Number)
      if (ym < mnY * 100 + mnM) return true
    }
    if (max) {
      const [mxY, mxM] = max.split('-').map(Number)
      if (ym > mxY * 100 + mxM) return true
    }
    return false
  }, [min, max])

  const isEmptyMonth = useCallback((year: number, month: number): boolean => {
    if (!activeMonths || activeMonths.length === 0) return false
    const ym = `${year}-${String(month).padStart(2, '0')}`
    return !activeMonths.includes(ym)
  }, [activeMonths])

  // ── Open / close ────────────────────────────────────────────────────────────

  function openPicker() {
    if (disabled) return
    if (triggerRef.current) {
      const r = triggerRef.current.getBoundingClientRect()
      const PANEL_H = 240
      const PANEL_W = 240
      let top  = r.bottom + 4
      let left = r.left
      // Viewport flip: if panel bottom would overflow, open above instead
      if (top + PANEL_H > window.innerHeight) top = r.top - PANEL_H - 4
      // Right-edge clamp
      if (left + PANEL_W > window.innerWidth) left = window.innerWidth - PANEL_W - 8
      setPanelStyle({ top, left })
    }
    const initYear  = selYear || todayY
    const initMonth = selMonth || todayM
    setPanelYear(initYear)
    setFocusedMonth(initMonth)
    focusCellOnRender.current = true
    setOpen(true)
  }

  function closePicker() {
    setOpen(false)
    triggerRef.current?.focus()
  }

  function selectMonth(year: number, month: number) {
    if (isDisabledMonth(year, month)) return
    if (isEmptyMonth(year, month)) return
    onChange(`${year}-${String(month).padStart(2, '0')}`)
    closePicker()
  }

  // ── Focus management: focus the active cell after keyboard nav or open ───────

  useEffect(() => {
    if (open && focusCellOnRender.current) {
      focusCellOnRender.current = false
      const idx = focusedMonth - 1
      const timer = setTimeout(() => { cellRefs.current[idx]?.focus() }, 0)
      return () => clearTimeout(timer)
    }
  }, [open, focusedMonth, panelYear])

  // ── Click outside to close ──────────────────────────────────────────────────

  useEffect(() => {
    if (!open) return
    function handleMouseDown(e: MouseEvent) {
      if (
        panelRef.current && !panelRef.current.contains(e.target as Node) &&
        triggerRef.current && !triggerRef.current.contains(e.target as Node)
      ) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleMouseDown)
    return () => document.removeEventListener('mousedown', handleMouseDown)
  }, [open])

  // ── Keyboard navigation (panel) ─────────────────────────────────────────────

  function handleKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    switch (e.key) {
      case 'ArrowLeft': {
        e.preventDefault()
        let newM = focusedMonth - 1, newY = panelYear
        if (newM < 1) { newM = 12; newY-- }
        focusCellOnRender.current = true
        setPanelYear(newY)
        setFocusedMonth(newM)
        break
      }
      case 'ArrowRight': {
        e.preventDefault()
        let newM = focusedMonth + 1, newY = panelYear
        if (newM > 12) { newM = 1; newY++ }
        focusCellOnRender.current = true
        setPanelYear(newY)
        setFocusedMonth(newM)
        break
      }
      case 'ArrowUp': {
        e.preventDefault()
        let newM = focusedMonth - 3, newY = panelYear
        if (newM < 1) { newM += 12; newY-- }
        focusCellOnRender.current = true
        setPanelYear(newY)
        setFocusedMonth(newM)
        break
      }
      case 'ArrowDown': {
        e.preventDefault()
        let newM = focusedMonth + 3, newY = panelYear
        if (newM > 12) { newM -= 12; newY++ }
        focusCellOnRender.current = true
        setPanelYear(newY)
        setFocusedMonth(newM)
        break
      }
      case 'PageUp': {
        e.preventDefault()
        focusCellOnRender.current = true
        setPanelYear(y => y - 1)
        break
      }
      case 'PageDown': {
        e.preventDefault()
        focusCellOnRender.current = true
        setPanelYear(y => y + 1)
        break
      }
      case 'Home': {
        e.preventDefault()
        const first = [1,2,3,4,5,6,7,8,9,10,11,12].find(m => !isDisabledMonth(panelYear, m) && !isEmptyMonth(panelYear, m))
        if (first !== undefined) {
          focusCellOnRender.current = true
          setFocusedMonth(first)
        }
        break
      }
      case 'End': {
        e.preventDefault()
        const last = [12,11,10,9,8,7,6,5,4,3,2,1].find(m => !isDisabledMonth(panelYear, m) && !isEmptyMonth(panelYear, m))
        if (last !== undefined) {
          focusCellOnRender.current = true
          setFocusedMonth(last)
        }
        break
      }
      case 'Enter':
      case ' ': {
        if ((e.target as HTMLElement)?.classList.contains('month-cell')) {
          e.preventDefault()
          selectMonth(panelYear, focusedMonth)
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

  // ── Derived values ──────────────────────────────────────────────────────────

  const formattedValue = selYear
    ? formatMonthTrigger(selYear, selMonth, lang)
    : '—'

  const isCurrentMonthSelected = selYear === todayY && selMonth === todayM

  const prevYearDisabled = min
    ? (panelYear - 1) * 100 + 12 < ((): number => {
        const [mnY, mnM] = min.split('-').map(Number)
        return mnY * 100 + mnM
      })()
    : false

  const nextYearDisabled = max
    ? (panelYear + 1) * 100 + 1 > ((): number => {
        const [mxY, mxM] = max.split('-').map(Number)
        return mxY * 100 + mxM
      })()
    : false

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className={`month-picker-trigger${open ? ' is-open' : ''}`}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={t.monthPickerTriggerLabel(formattedValue)}
        disabled={disabled}
        onClick={open ? closePicker : openPicker}
      >
        <span>{formattedValue}</span>
        <IconChevronDown size={14} className="month-picker-trigger__chevron" />
      </button>

      {open && (
        <div
          ref={panelRef}
          className="picker-panel month-picker-panel"
          role="dialog"
          aria-modal="true"
          aria-label={t.monthPickerDialogLabel}
          style={panelStyle}
          onKeyDown={handleKeyDown}
          onBlur={e => {
            const related = e.relatedTarget as Node | null
            if (
              !panelRef.current?.contains(related) &&
              !triggerRef.current?.contains(related)
            ) {
              setTimeout(() => {
                if (!panelRef.current?.contains(document.activeElement)) {
                  setOpen(false)
                }
              }, 150)
            }
          }}
        >
          {/* Year stepper */}
          <div className="picker-panel-header">
            <button
              type="button"
              className="picker-nav-btn"
              aria-label={t.monthPickerPrevYear}
              disabled={prevYearDisabled}
              onClick={() => setPanelYear(y => y - 1)}
            >‹</button>
            <span className="picker-panel-title">{panelYear}</span>
            <button
              type="button"
              className="picker-nav-btn"
              aria-label={t.monthPickerNextYear}
              disabled={nextYearDisabled}
              onClick={() => setPanelYear(y => y + 1)}
            >›</button>
          </div>

          {/* Month grid */}
          <div className="month-grid" role="grid" aria-label={String(panelYear)}>
            {Array.from({ length: 12 }, (_, i) => {
              const month      = i + 1
              const isSelected = panelYear === selYear && month === selMonth
              const isCurrent  = panelYear === todayY  && month === todayM
              const isDisabled = isDisabledMonth(panelYear, month)
              const isEmpty    = !isDisabled && isEmptyMonth(panelYear, month)
              const isFocused  = month === focusedMonth

              let className = 'month-cell'
              if (isSelected) className += ' is-selected'
              // is-current only when the month actually has data — empty months must look inert regardless
              if (isCurrent && !isSelected && !isEmpty && !isDisabled) className += ' is-current'
              if (isDisabled) className += ' is-disabled'
              else if (isEmpty) className += ' is-empty'

              const cellLabel = fullMonthLabel(panelYear, month, lang)

              return (
                <button
                  key={month}
                  ref={el => { cellRefs.current[i] = el }}
                  type="button"
                  role="gridcell"
                  className={className}
                  aria-selected={isSelected}
                  aria-disabled={isDisabled || isEmpty}
                  aria-label={cellLabel}
                  tabIndex={(isFocused && !isEmpty && !isDisabled) ? 0 : -1}
                  onClick={() => selectMonth(panelYear, month)}
                  onFocus={() => setFocusedMonth(month)}
                >
                  {shortMonthName(month, lang)}
                </button>
              )
            })}
          </div>

          {/* "Mes actual / Current month" reset button */}
          <button
            type="button"
            className={`picker-today-btn${isCurrentMonthSelected ? ' is-hidden' : ''}`}
            onClick={() => selectMonth(todayY, todayM)}
          >
            {t.monthPickerCurrentMonth}
          </button>
        </div>
      )}
    </>
  )
}
