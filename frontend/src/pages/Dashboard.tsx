import { useState, useEffect } from 'react'
import type { Account, Category, Tag, GlobalFilters, Overview, CategorySummary, MonthSummary, AccountSummary, ImportResult, CashflowSummary } from '../api/types'
import {
  getAccounts, getCategories, getTags, getOverview,
  getByCategory, getByMonth, getByAccount, getCashflow,
} from '../api/client'
import GlobalFilterBar from '../components/GlobalFilterBar'
import KpiCards from '../components/KpiCards'
import SpendingByCategory from '../components/SpendingByCategory'
import SpendingOverTime from '../components/SpendingOverTime'
import SpendingByAccount from '../components/SpendingByAccount'
import CashflowSankey from '../components/CashflowSankey'
import CategoryMovers from '../components/CategoryMovers'
import TransactionsTable from '../components/TransactionsTable'
import ImportModal from '../components/ImportModal'
import { useT } from '../i18n'
import { defaultRange } from '../utils'
import { previousCalendarMonth } from '../utils/comparison'

function makeDefaultFilters(): GlobalFilters {
  return { ...defaultRange(), tags: [] }
}

interface AsyncState<T> {
  loading: boolean
  error: string | null
  data: T | null
}

function idle<T>(): AsyncState<T> { return { loading: true, error: null, data: null } }

export default function Dashboard() {
  const { t } = useT()
  const [filters, setFilters] = useState<GlobalFilters>(makeDefaultFilters)
  const [accounts,   setAccounts]   = useState<Account[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [allTags,    setAllTags]    = useState<Tag[]>([])

  const [overview,   setOverview]   = useState<AsyncState<Overview>>(idle())
  const [byCategory, setByCategory] = useState<AsyncState<CategorySummary[]>>(idle())
  const [byMonth,    setByMonth]    = useState<AsyncState<MonthSummary[]>>(idle())
  const [byAccount,  setByAccount]  = useState<AsyncState<AccountSummary[]>>(idle())
  const [cashflow,   setCashflow]   = useState<AsyncState<CashflowSummary>>(idle())

  // Previous-period data for comparison (Slice 1 + 2 — fetched client-side)
  const [prevOverview,    setPrevOverview]    = useState<AsyncState<Overview>>(idle())
  const [prevByCategory,  setPrevByCategory]  = useState<AsyncState<CategorySummary[]>>(idle())

  const [showImport, setShowImport] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const [toast,      setToast]      = useState<string | null>(null)

  function handleImportSuccess(result: ImportResult) {
    setShowImport(false)
    setToast(t.toastSuccess(result.num_inserted, result.num_duplicates))
    setTimeout(() => setToast(null), 6000)
    setRefreshKey(k => k + 1)
  }

  useEffect(() => {
    getAccounts().then(setAccounts).catch(() => {})
    getCategories().then(setCategories).catch(() => {})
    getTags().then(setAllTags).catch(() => {})
  }, [])

  useEffect(() => {
    const params = {
      from:        filters.from || undefined,
      to:          filters.to   || undefined,
      account_id:  filters.account_id,
      category_id: filters.category_id,
      tags:        filters.tags.length > 0 ? filters.tags : undefined,
      flow:        filters.flow,
    }

    setOverview(idle())
    setByCategory(idle())
    setByMonth(idle())
    setByAccount(idle())
    setCashflow(idle())
    setPrevOverview(idle())
    setPrevByCategory(idle())

    getOverview(params)
      .then(d  => setOverview ({ loading: false, error: null,     data: d }))
      .catch(e => setOverview ({ loading: false, error: String(e), data: null }))

    // by-category donut shows ALL categories (no category_id) so the user can switch/clear
    getByCategory({ from: params.from, to: params.to, account_id: params.account_id, tags: params.tags, flow: params.flow })
      .then(d  => setByCategory({ loading: false, error: null,     data: d }))
      .catch(e => setByCategory({ loading: false, error: String(e), data: null }))

    getByMonth(params)
      .then(d  => setByMonth({ loading: false, error: null,     data: d }))
      .catch(e => setByMonth({ loading: false, error: String(e), data: null }))

    // by-account: no account_id (chart shows all accounts) but apply category + tag + flow
    getByAccount({ from: params.from, to: params.to, category_id: params.category_id, tags: params.tags, flow: params.flow })
      .then(d  => setByAccount({ loading: false, error: null,     data: d }))
      .catch(e => setByAccount({ loading: false, error: String(e), data: null }))

    getCashflow(params)
      .then(d  => setCashflow({ loading: false, error: null,     data: d }))
      .catch(e => setCashflow({ loading: false, error: String(e), data: null }))

    // ── Previous-period fetches (Slice 1 + 2) ─────────────────────────────
    // Derive previous calendar month from the filter's from-date.
    // Pass same non-date filters (account, tags, flow) to both calls for consistency.
    const prevRange = previousCalendarMonth(filters.from)
    if (prevRange) {
      const prevParams = { ...params, from: prevRange.from, to: prevRange.to }
      getOverview(prevParams)
        .then(d  => setPrevOverview({ loading: false, error: null,     data: d }))
        .catch(() => setPrevOverview({ loading: false, error: null,     data: null }))

      // Previous by-category: same as current (no category_id, all categories)
      getByCategory({ from: prevRange.from, to: prevRange.to, account_id: params.account_id, tags: params.tags, flow: params.flow })
        .then(d  => setPrevByCategory({ loading: false, error: null,     data: d }))
        .catch(() => setPrevByCategory({ loading: false, error: null,     data: null }))
    } else {
      // No valid previous range (edge case) — clear comparison data
      setPrevOverview({ loading: false, error: null, data: null })
      setPrevByCategory({ loading: false, error: null, data: null })
    }
  }, [filters, refreshKey])

  function handleFlowClick(flow: 'expense' | 'income' | undefined) {
    setFilters(f => ({ ...f, flow }))
  }

  return (
    <>
      <main className="dashboard">
        <div className="dashboard-header">
          <GlobalFilterBar
            filters={filters}
            accounts={accounts}
            categories={categories}
            tags={allTags}
            onChange={setFilters}
            onClear={() => setFilters(makeDefaultFilters())}
          />
          <KpiCards
            overview={overview.data}
            loading={overview.loading}
            error={overview.error}
            compact
            previousOverview={prevOverview.data}
          />
          <button
            className="btn-primary dashboard-header-import"
            onClick={() => setShowImport(true)}
          >
            {t.btnImport}
          </button>
        </div>

        {/* Row B: gastos por categoría | detalle de movimientos */}
        <div className="charts-row-category">
          <SpendingByCategory
            data={byCategory.data ?? []}
            categories={categories}
            loading={byCategory.loading}
            error={byCategory.error}
            selectedCategoryId={filters.category_id}
            onCategoryClick={(id) => setFilters(f => ({ ...f, category_id: id }))}
          />
          <TransactionsTable
            globalFilters={filters}
            categories={categories}
            allTags={allTags}
            refreshKey={refreshKey}
          />
        </div>

        {/* Top movers: current vs previous calendar month */}
        <CategoryMovers
          current={byCategory.data ?? []}
          previous={prevByCategory.data ?? []}
          categories={categories}
          loading={byCategory.loading}
          prevLoading={prevByCategory.loading}
          error={byCategory.error}
        />

        {/* Row A: desglose por cuenta | evolución mensual */}
        <div className="charts-row">
          <SpendingByAccount
            data={byAccount.data ?? []}
            loading={byAccount.loading}
            error={byAccount.error}
            selectedFlow={filters.flow}
            onFlowClick={handleFlowClick}
          />
          <SpendingOverTime
            data={byMonth.data ?? []}
            loading={byMonth.loading}
            error={byMonth.error}
            selectedFlow={filters.flow}
            onFlowClick={handleFlowClick}
          />
        </div>

        <CashflowSankey
          data={cashflow.data ?? null}
          loading={cashflow.loading}
          error={cashflow.error}
          categories={categories}
          selectedCategoryId={filters.category_id}
          onCategoryClick={(id) => setFilters(f => ({ ...f, category_id: id }))}
        />
      </main>

      {showImport && (
        <ImportModal
          accounts={accounts}
          categories={categories}
          allTags={allTags}
          onClose={() => setShowImport(false)}
          onSuccess={handleImportSuccess}
        />
      )}

      {toast && (
        <div className="toast">
          <span>{toast}</span>
          <button className="toast-close" onClick={() => setToast(null)} aria-label={t.toastClose}>✕</button>
        </div>
      )}
    </>
  )
}
