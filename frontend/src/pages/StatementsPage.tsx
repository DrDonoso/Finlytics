import { useState, useEffect, useMemo } from 'react'
import type { Overview, Account, Category, Tag, GlobalFilters, ImportResult } from '../api/types'
import type { StatementMonth } from '../api/types'
import {
  getStatementMonths, deleteStatementMonth, getOverview,
  getAccounts, getCategories, getTags,
} from '../api/client'
import { useT } from '../i18n'
import type { Lang } from '../i18n'
import TransactionsTable from '../components/TransactionsTable'
import StatementsDeleteModal from '../components/StatementsDeleteModal'
import ImportModal from '../components/ImportModal'
import MonthPicker from '../components/MonthPicker'

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

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function StatementsPage() {
  const { t, lang, formatCurrency } = useT()

  // Statement months list (from API — sorted DESC)
  const [months,       setMonths]       = useState<StatementMonth[]>([])
  const [monthsLoading, setMonthsLoading] = useState(true)
  const [monthsError,  setMonthsError]  = useState<string | null>(null)

  // Selected month
  const [selY, setSelY] = useState(0)
  const [selM, setSelM] = useState(0)

  // Selected account filter (undefined = all accounts)
  const [selAccountId, setSelAccountId] = useState<number | undefined>(undefined)

  // Overview for the selected month (income / expense / net / count)
  const [overview,        setOverview]        = useState<Overview | null>(null)
  const [overviewLoading, setOverviewLoading] = useState(false)
  const [overviewRefKey,  setOverviewRefKey]  = useState(0)

  // Reference data for TransactionsTable / ImportModal
  const [accounts,   setAccounts]   = useState<Account[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [allTags,    setAllTags]    = useState<Tag[]>([])

  // Modal / UX state
  const [showDelete, setShowDelete] = useState(false)
  const [deleting,   setDeleting]   = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [toast,      setToast]      = useState<string | null>(null)

  // refreshKey triggers re-fetch of both the months list and the transactions table
  const [refreshKey, setRefreshKey] = useState(0)

  // ── Load reference data once ────────────────────────────────────────────────
  useEffect(() => {
    getAccounts().then(setAccounts).catch(() => {})
    getCategories().then(setCategories).catch(() => {})
    getTags().then(setAllTags).catch(() => {})
  }, [])

  // ── Load statement months (re-runs on full refresh after delete/import, or account change) ─
  useEffect(() => {
    let cancelled = false
    setMonthsLoading(true)
    setMonthsError(null)
    getStatementMonths(selAccountId)
      .then(data => {
        if (cancelled) return
        setMonths(data)
        setMonthsLoading(false)
        // Land on the most recent month with data, or current calendar month if none
        if (data.length > 0) {
          setSelY(data[0].year)
          setSelM(data[0].month)
        } else {
          const { y, m } = todayYM()
          setSelY(y)
          setSelM(m)
        }
      })
      .catch(e => {
        if (cancelled) return
        setMonthsError(String(e))
        setMonthsLoading(false)
      })
    return () => { cancelled = true }
  }, [refreshKey, selAccountId]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Derived date strings ────────────────────────────────────────────────────
  const from = selY ? `${selY}-${pad2(selM)}-01` : ''
  const to   = selY ? `${selY}-${pad2(selM)}-${pad2(lastDayOf(selY, selM))}` : ''

  // Global filters for TransactionsTable — month-scoped, account-scoped
  const globalFilters = useMemo<GlobalFilters>(() => ({ from, to, account_id: selAccountId, tags: [] }), [from, to, selAccountId])

  // Whether the selected month has any data (avoids unnecessary overview fetch)
  const currentMonthHasData = months.some(s => s.year === selY && s.month === selM)

  // ── Fetch overview whenever month changes or an edit/refresh occurs ─────────
  useEffect(() => {
    if (!from || !to || !currentMonthHasData) {
      setOverview(null)
      setOverviewLoading(false)
      return
    }
    let cancelled = false
    setOverviewLoading(true)
    setOverview(null)
    getOverview({ from, to, account_id: selAccountId })
      .then(d  => { if (!cancelled) { setOverview(d);  setOverviewLoading(false) } })
      .catch(() => { if (!cancelled) { setOverviewLoading(false) } })
    return () => { cancelled = true }
  }, [from, to, currentMonthHasData, refreshKey, overviewRefKey, selAccountId]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Navigation helpers ──────────────────────────────────────────────────────
  const today  = todayYM()
  const oldest = months.length > 0 ? months[months.length - 1] : null
  const isPrevDisabled = oldest
    ? (selY === oldest.year && selM === oldest.month)
    : true
  const isNextDisabled = selY === today.y && selM === today.m

  function navPrev() {
    if (isPrevDisabled) return
    if (selM === 1) { setSelY(y => y - 1); setSelM(12) }
    else setSelM(m => m - 1)
  }

  function navNext() {
    if (isNextDisabled) return
    if (selM === 12) { setSelY(y => y + 1); setSelM(1) }
    else setSelM(m => m + 1)
  }

  // ── Derived display values ──────────────────────────────────────────────────
  const monthLabel    = selY ? formatMonthLabel(selY, selM, lang) : ''
  const monthInputVal = selY ? `${selY}-${pad2(selM)}` : ''
  const minMonthVal   = oldest ? `${oldest.year}-${pad2(oldest.month)}` : undefined
  const maxMonthVal   = `${today.y}-${pad2(today.m)}`
  const activeMonths  = months.map(s => `${s.year}-${pad2(s.month)}`)

  const isEmpty  = !monthsLoading && !currentMonthHasData
  const hasData  = currentMonthHasData
  const count    = overview?.num_transactions ?? months.find(s => s.year === selY && s.month === selM)?.count ?? 0

  // ── Delete handler ──────────────────────────────────────────────────────────
  async function handleDeleteConfirm() {
    setDeleting(true)
    try {
      await deleteStatementMonth(selY, selM, selAccountId)
      setShowDelete(false)
      showToast(t.stmtsDeleteOk)
      setRefreshKey(k => k + 1)
    } catch {
      // keep modal open; future: could surface error inline
    } finally {
      setDeleting(false)
    }
  }

  // ── Import handler ──────────────────────────────────────────────────────────
  function handleImportSuccess(result: ImportResult) {
    setShowImport(false)
    showToast(t.toastSuccess(result.num_inserted, result.num_duplicates))
    setRefreshKey(k => k + 1)
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
          <span className="icon">⚠</span>
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
      {/* ── Account selector (only when more than one account) ── */}
      {accounts.length > 1 && (
        <div className="stmts-account-bar">
          <label htmlFor="stmts-acct-sel">{t.filterAccount}</label>
          <select
            id="stmts-acct-sel"
            value={selAccountId ?? ''}
            onChange={e => setSelAccountId(e.target.value ? Number(e.target.value) : undefined)}
          >
            <option value="">{t.filterAllAccounts}</option>
            {accounts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </div>
      )}

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
          </div>
          <div className="tx-total tx-total--income">
            <span className="tx-total-label">{t.kpiTotalIncome}</span>
            <span className="tx-total-value">+{formatCurrency(overview.total_income)}</span>
          </div>
          <div className="tx-total tx-total--expense">
            <span className="tx-total-label">{t.kpiTotalExpense}</span>
            <span className="tx-total-value">−{formatCurrency(overview.total_expense)}</span>
          </div>
          <div className={`tx-total tx-total--${overview.net >= 0 ? 'income' : 'expense'}`}>
            <span className="tx-total-label">{t.kpiNet}</span>
            <span className="tx-total-value">{formatCurrency(overview.net)}</span>
          </div>
        </div>
        </div>
      )}

      {/* ── Empty state ───────────────────────────────────────── */}
      {isEmpty && (
        <div className="state-box stmts-empty">
          <span className="icon">📄</span>
          <strong style={{ fontSize: 16 }}>{t.stmtsEmptyTitle(monthLabel)}</strong>
          <span>{t.stmtsEmptyHint}</span>
          <button
            type="button"
            className="btn-primary"
            onClick={() => setShowImport(true)}
          >
            {t.stmtsImportBtn}
          </button>
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
          onEditSuccess={() => setOverviewRefKey(k => k + 1)}
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

      {/* ── Import modal ──────────────────────────────────────── */}
      {showImport && (
        <ImportModal
          accounts={accounts}
          categories={categories}
          allTags={allTags}
          onClose={() => setShowImport(false)}
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
