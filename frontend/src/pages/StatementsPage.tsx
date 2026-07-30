import { useState, useEffect, useMemo, useRef } from 'react'
import type { GlobalFilters, ImportResult, SummaryParams } from '../api/types'
import { deleteStatementMonth, downloadStatementOriginal } from '../api/client'
import { useQueryClient } from '@tanstack/react-query'
import {
  useAccounts, useCategories, useTags,
  useStatementMonths, useStatementOriginals,
  useOverview, useByCategory,
} from '../api/queries'
import { errorMessage } from '../api/errors'
import { useT } from '../i18n'
import type { Lang } from '../i18n'
import { IconAlert, IconDownload, IconFileText, TrendArrow } from '../components/icons'
import TransactionsTable from '../components/TransactionsTable'
import CategoryMovers from '../components/CategoryMovers'
import StatementsDeleteModal from '../components/StatementsDeleteModal'
import ImportModal from '../components/ImportModal'
import ImportLauncher, { type ImportLauncherHandle } from '../components/ImportLauncher'
import MonthPicker from '../components/MonthPicker'
import { previousCalendarMonth, computeDelta, type DeltaResult } from '../utils/comparison'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function lastDayOf(year: number, month: number): number {
  return new Date(year, month, 0).getDate()
}

function pad2(n: number): string {
  return String(n).padStart(2, '0')
}

function formatMonthLabel(year: number, month: number, lang: Lang): string {
  const locale = lang === 'es' ? 'es-ES' : 'en-GB'
  return new Intl.DateTimeFormat(locale, { month: 'long', year: 'numeric' }).format(
    new Date(year, month - 1, 1),
  )
}

function todayYM(): { y: number; m: number } {
  const d = new Date()
  return { y: d.getFullYear(), m: d.getMonth() + 1 }
}

// ─── KPI delta badge for month-over-month comparison ─────────────────────────

function TxDeltaBadge({ delta, invert, neutral }: { delta: DeltaResult | null; invert?: boolean; neutral?: boolean }) {
  if (!delta) return null
  if (delta.isNew) return <span className="header-kpi-delta header-kpi-delta-neutral">NUEVO</span>
  if (delta.pct === null) return null
  const isUp   = delta.abs > 0
  const cls = neutral || delta.abs === 0
    ? 'header-kpi-delta-neutral'
    : (invert ? !isUp : isUp) ? 'header-kpi-delta-good' : 'header-kpi-delta-bad'
  const sign  = isUp ? '+' : ''
  return <span className={`header-kpi-delta ${cls}`}><TrendArrow value={delta.abs} /> {sign}{delta.pct.toFixed(1)}%</span>
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function StatementsPage() {
  const { t, lang, formatCurrency } = useT()

  const queryClient = useQueryClient()

  // Estabiliza el array vacío: `?? []` crea uno nuevo por render y rompería las deps de abajo
  const EMPTY: never[] = useMemo(() => [], [])

  // Selected month
  const [selY, setSelY] = useState(0)
  const [selM, setSelM] = useState(0)

  // Selected account filter (undefined = all accounts)
  const [selAccountId, setSelAccountId] = useState<number | undefined>(undefined)

  // Reference data for TransactionsTable / ImportModal
  const accounts   = useAccounts().data   ?? EMPTY
  const categories = useCategories().data ?? EMPTY
  const allTags    = useTags().data       ?? EMPTY

  // Statement months list (from API — sorted DESC)
  const monthsQuery = useStatementMonths(selAccountId)
  const months = monthsQuery.data ?? EMPTY
  const monthsLoading = monthsQuery.isPending
  const monthsError = monthsQuery.error ? errorMessage(monthsQuery.error, t) : null

  // Modal / UX state
  const [showDelete, setShowDelete] = useState(false)
  const [deleting,   setDeleting]   = useState(false)
  const [importFiles, setImportFiles] = useState<File[] | null>(null)
  const launcherRef = useRef<ImportLauncherHandle>(null)
  const [toast,      setToast]      = useState<string | null>(null)

  // refreshKey refresca la tabla de transacciones, que todavía no usa react-query
  const [refreshKey, setRefreshKey] = useState(0)

  // Originals dropdown UI state
  const [originalsDropdownOpen, setOriginalsDropdownOpen] = useState(false)
  const originalsDropdownRef = useRef<HTMLDivElement>(null)

  // Al cambiar la lista de meses (carga inicial o tras importar/borrar) aterriza en el más reciente.
  // react-query comparte estructura: un refetch con los mismos datos mantiene la referencia y no dispara esto.
  useEffect(() => {
    if (months.length > 0) {
      setSelY(months[0].year)
      setSelM(months[0].month)
    } else if (!monthsLoading) {
      const { y, m } = todayYM()
      setSelY(y)
      setSelM(m)
    }
  }, [months, monthsLoading])

  // ── Derived date strings ────────────────────────────────────────────────────
  const from = selY ? `${selY}-${pad2(selM)}-01` : ''
  const to   = selY ? `${selY}-${pad2(selM)}-${pad2(lastDayOf(selY, selM))}` : ''

  // Global filters for TransactionsTable — month-scoped, account-scoped
  const globalFilters = useMemo<GlobalFilters>(() => ({ from, to, account_id: selAccountId, tags: [] }), [from, to, selAccountId])

  // Whether the selected month has any data (avoids unnecessary overview fetch)
  const currentMonthHasData = months.some(s => s.year === selY && s.month === selM)

  // Parámetros del mes seleccionado y del anterior (deltas KPI). En useMemo para que la clave no cambie cada render.
  const monthParams: SummaryParams = useMemo(() => ({ from, to, account_id: selAccountId }), [from, to, selAccountId])
  const prevRange = useMemo(() => (from ? previousCalendarMonth(from) : null), [from])
  const prevParams: SummaryParams | undefined = useMemo(
    () => (prevRange ? { from: prevRange.from, to: prevRange.to, account_id: selAccountId } : undefined),
    [prevRange, selAccountId],
  )

  // Los resúmenes solo se consultan cuando el mes seleccionado tiene datos
  const summaryEnabled = Boolean(from && to && currentMonthHasData)

  const overviewQuery     = useOverview(monthParams, { enabled: summaryEnabled })
  const prevOverviewQuery = useOverview(prevParams,  { enabled: summaryEnabled && Boolean(prevParams) })
  const overview        = overviewQuery.data ?? null
  const overviewLoading = overviewQuery.isPending
  const prevOverview    = prevOverviewQuery.data ?? null

  const selByCatQuery  = useByCategory(monthParams, { enabled: summaryEnabled })
  const prevByCatQuery = useByCategory(prevParams,  { enabled: summaryEnabled && Boolean(prevParams) })
  const selByCat         = selByCatQuery.data  ?? EMPTY
  const prevByCat        = prevByCatQuery.data  ?? EMPTY
  const selByCatLoading  = selByCatQuery.isPending
  const prevByCatLoading = prevByCatQuery.isPending
  const byCatError       = selByCatQuery.error ? errorMessage(selByCatQuery.error, t) : null

  // Original PDFs available for the selected month
  const originalsQuery = useStatementOriginals(selY, selM, selAccountId, { enabled: Boolean(selY && selM) })
  const originals = originalsQuery.data ?? EMPTY

  // Cierra el desplegable de originales al cambiar de mes o de cuenta
  useEffect(() => {
    setOriginalsDropdownOpen(false)
  }, [selY, selM, selAccountId])

  // ── Close originals dropdown on outside click ────────────────────────────────
  useEffect(() => {
    if (!originalsDropdownOpen) return
    function handleClickOutside(e: MouseEvent) {
      if (originalsDropdownRef.current && !originalsDropdownRef.current.contains(e.target as Node)) {
        setOriginalsDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [originalsDropdownOpen])

  // ── Navigation helpers ──────────────────────────────────────────────────────
  // months[] is DESC-sorted (newest first). "prev" = earlier in time = higher idx; "next" = later = lower idx.
  const selIdx        = months.findIndex(s => s.year === selY && s.month === selM)
  const prevDataMonth = selIdx >= 0 && selIdx + 1 < months.length ? months[selIdx + 1] : null
  const nextDataMonth = selIdx > 0 ? months[selIdx - 1] : null

  const isPrevDisabled = prevDataMonth === null
  const isNextDisabled = nextDataMonth === null

  function navPrev() {
    if (!prevDataMonth) return
    setSelY(prevDataMonth.year)
    setSelM(prevDataMonth.month)
  }

  function navNext() {
    if (!nextDataMonth) return
    setSelY(nextDataMonth.year)
    setSelM(nextDataMonth.month)
  }

  // ── Derived display values ──────────────────────────────────────────────────
  const today       = todayYM()
  const oldest      = months.length > 0 ? months[months.length - 1] : null
  const monthLabel    = selY ? formatMonthLabel(selY, selM, lang) : ''
  const monthInputVal = selY ? `${selY}-${pad2(selM)}` : ''
  const minMonthVal   = oldest ? `${oldest.year}-${pad2(oldest.month)}` : undefined
  const maxMonthVal   = `${today.y}-${pad2(today.m)}`
  const activeMonths  = months.map(s => `${s.year}-${pad2(s.month)}`)

  const isEmpty  = !monthsLoading && !currentMonthHasData
  const hasData  = currentMonthHasData
  const count    = overview?.num_transactions ?? months.find(s => s.year === selY && s.month === selM)?.count ?? 0

  // Tras borrar o importar: refresca meses, resúmenes y originales, y la tabla (que aún no usa react-query)
  function refreshMonthData() {
    setRefreshKey(k => k + 1)
    queryClient.invalidateQueries({ queryKey: ['statements'] })
    queryClient.invalidateQueries({ queryKey: ['summary'] })
  }

  // ── Delete handler ──────────────────────────────────────────────────────────
  async function handleDeleteConfirm() {
    setDeleting(true)
    try {
      await deleteStatementMonth(selY, selM, selAccountId)
      setShowDelete(false)
      showToast(t.stmtsDeleteOk)
      refreshMonthData()
    } catch {
      // keep modal open; future: could surface error inline
    } finally {
      setDeleting(false)
    }
  }

  // ── Import handler ──────────────────────────────────────────────────────────
  function handleImportSuccess(result: ImportResult) {
    setImportFiles(null)
    showToast(t.toastSuccess(result.num_inserted, result.num_duplicates))
    refreshMonthData()
  }

  function showToast(msg: string) {
    setToast(msg)
    setTimeout(() => setToast(null), 6000)
  }

  // ── Early return: loading ───────────────────────────────────────────────────
  if (monthsLoading) {
    return (
      <main className="tx-page">
        <div className="spinner-wrap"><div className="spinner" /></div>
      </main>
    )
  }

  // ── Early return: error ─────────────────────────────────────────────────────
  if (monthsError) {
    return (
      <main className="tx-page">
        <div className="state-box error">
          <IconAlert size={18} />
          <span>{t.kpiErrorLoading}{monthsError}</span>
        </div>
      </main>
    )
  }

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <main
      className="tx-page stmts-page"
      onKeyDown={e => {
        // Arrow-key month navigation — skip when focus is inside an input
        if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
        if (e.key === 'ArrowLeft')  navPrev()
        if (e.key === 'ArrowRight') navNext()
      }}
    >
      {/* ── Account selector + Import button ──────────────────── */}
      <div className="stmts-account-bar">
        {accounts.length > 1 && (
          <>
            <label htmlFor="stmts-acct-sel">{t.filterAccount}</label>
            <select
              id="stmts-acct-sel"
              value={selAccountId ?? ''}
              onChange={e => setSelAccountId(e.target.value ? Number(e.target.value) : undefined)}
            >
              <option value="">{t.filterAllAccounts}</option>
              {accounts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </>
        )}
        <button
          type="button"
          className="btn-primary stmts-header-import"
          onClick={() => launcherRef.current?.open()}
        >
          {t.stmtsImportBtn}
        </button>
      </div>

      {/* ── Month nav bar ─────────────────────────────────────── */}
      <div className="month-nav">
        <button
          type="button"
          className="month-nav-arrow"
          onClick={navPrev}
          aria-label={t.stmtsPrev}
          aria-disabled={isPrevDisabled}
          disabled={isPrevDisabled}
        >‹</button>

        <MonthPicker
          value={monthInputVal}
          min={minMonthVal}
          max={maxMonthVal}
          activeMonths={activeMonths}
          onChange={v => {
            const [y, m] = v.split('-').map(Number)
            if (!isNaN(y) && !isNaN(m) && m >= 1 && m <= 12) {
              setSelY(y); setSelM(m)
            }
          }}
        />

        <button
          type="button"
          className="month-nav-arrow"
          onClick={navNext}
          aria-label={t.stmtsNext}
          aria-disabled={isNextDisabled}
          disabled={isNextDisabled}
        >›</button>
      </div>

      {/* ── Month summary header — loading skeleton ────────────── */}
      {hasData && overviewLoading && (
        <div className="month-header">
          <div className="tx-totals">
            {[0, 1, 2, 3].map(i => (
              <div key={i} className="tx-total">
                <div className="skeleton" style={{ width: 80, height: 11, marginBottom: 6 }} />
                <div className="skeleton" style={{ width: 110, height: 24 }} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Month summary header — loaded ─────────────────────── */}
      {hasData && !overviewLoading && overview && (
        <div className="month-header">
        <div className="tx-totals">
          <div className="tx-total">
            <span className="tx-total-label">{t.kpiTransactions}</span>
            <span className="tx-total-value">{overview.num_transactions}</span>
            <TxDeltaBadge delta={computeDelta(overview.num_transactions, prevOverview?.num_transactions)} neutral />
          </div>
          <div className="tx-total tx-total--income">
            <span className="tx-total-label">{t.kpiTotalIncome}</span>
            <span className="tx-total-value">+{formatCurrency(overview.total_income)}</span>
            <TxDeltaBadge delta={computeDelta(overview.total_income, prevOverview?.total_income)} />
          </div>
          <div className="tx-total tx-total--expense">
            <span className="tx-total-label">{t.kpiTotalExpense}</span>
            <span className="tx-total-value">−{formatCurrency(overview.total_expense)}</span>
            <TxDeltaBadge delta={computeDelta(overview.total_expense, prevOverview?.total_expense)} invert />
          </div>
          <div className={`tx-total tx-total--${overview.net >= 0 ? 'income' : 'expense'}`}>
            <span className="tx-total-label">{t.kpiNet}</span>
            <span className="tx-total-value">{formatCurrency(overview.net)}</span>
            <TxDeltaBadge delta={computeDelta(overview.net, prevOverview?.net)} />
          </div>
        </div>
        {originals.length > 0 && (
          <div className="stmts-download-wrap" ref={originalsDropdownRef}>
            <button
              type="button"
              className="btn-download-original"
              title={t.stmtsDownloadOriginal}
              onClick={() => {
                if (originals.length === 1) {
                  downloadStatementOriginal(originals[0].import_run_id, originals[0].source_filename).catch(() => {})
                } else {
                  setOriginalsDropdownOpen(v => !v)
                }
              }}
            >
              <IconDownload size={15} /> {t.stmtsDownloadOriginal}
            </button>
            {originals.length > 1 && originalsDropdownOpen && (
              <div className="originals-dropdown" role="menu" aria-label={t.stmtsDownloadOriginalDropdown}>
                {originals.map(o => (
                  <button
                    key={o.import_run_id}
                    type="button"
                    className="originals-dropdown-item"
                    role="menuitem"
                    onClick={() => {
                      setOriginalsDropdownOpen(false)
                      downloadStatementOriginal(o.import_run_id, o.source_filename).catch(() => {})
                    }}
                  >
                    <span className="originals-dropdown-item-filename"><IconFileText size={14} /> {o.source_filename}</span>
                    <span className="originals-dropdown-item-account">{o.account_name}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
        </div>
      )}

      {/* ── Empty state ───────────────────────────────────────── */}
      {isEmpty && (
        <div className="state-box stmts-empty">
          <IconFileText size={18} />
          <strong style={{ fontSize: 16 }}>{t.stmtsEmptyTitle(monthLabel)}</strong>
          <span>{t.stmtsEmptyHint}</span>
          <button
            type="button"
            className="btn-primary"
            onClick={() => launcherRef.current?.open()}
          >
            {t.stmtsImportBtn}
          </button>
        </div>
      )}

      {/* ── Category movers (selected month vs previous month) ── */}
      {hasData && (
        <div className="charts-row-full stmts-movers-wrap">
          <CategoryMovers
            current={selByCat}
            previous={prevByCat}
            categories={categories}
            loading={selByCatLoading}
            prevLoading={prevByCatLoading}
            error={byCatError}
          />
        </div>
      )}

      {/* ── Transactions table (only when month has data) ─────── */}
      {hasData && (
        <TransactionsTable
          globalFilters={globalFilters}
          categories={categories}
          allTags={allTags}
          refreshKey={refreshKey}
          pageSize={25}
          hideInternalFilters
          onEditSuccess={() => {
            // Editar una transacción cambia los KPIs del mes actual (y del anterior en los deltas)
            queryClient.invalidateQueries({ queryKey: ['summary', 'overview'] })
            queryClient.invalidateQueries({ queryKey: ['summary', 'by-category'] })
          }}
          headerAction={
            <button
              type="button"
              className="btn-icon-trash"
              onClick={() => setShowDelete(true)}
              aria-label={t.stmtsDeleteMonth}
              title={t.stmtsDeleteMonth}
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <polyline points="3 6 5 6 21 6"/>
                <path d="M19 6l-1 14H6L5 6"/>
                <path d="M10 11v6M14 11v6"/>
                <path d="M9 6V4h6v2"/>
              </svg>
            </button>
          }
        />
      )}

      {/* ── Delete modal ──────────────────────────────────────── */}
      {showDelete && (
        <StatementsDeleteModal
          monthLabel={monthLabel}
          count={count}
          deleting={deleting}
          onConfirm={handleDeleteConfirm}
          onCancel={() => { if (!deleting) setShowDelete(false) }}
        />
      )}

      {/* ── Import launcher (hidden file input) + modal ───────────────────── */}
      <ImportLauncher ref={launcherRef} onFiles={files => setImportFiles(files)} />

      {importFiles && (
        <ImportModal
          accounts={accounts}
          categories={categories}
          allTags={allTags}
          initialFiles={importFiles}
          onClose={() => setImportFiles(null)}
          onSuccess={handleImportSuccess}
        />
      )}

      {/* ── Toast ─────────────────────────────────────────────── */}
      {toast && (
        <div className="toast" role="status">
          {toast}
          <button type="button" className="toast-close" onClick={() => setToast(null)}>
            {t.toastClose}
          </button>
        </div>
      )}
    </main>
  )
}
