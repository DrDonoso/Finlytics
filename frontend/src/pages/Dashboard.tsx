import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Account, Category, Tag, GlobalFilters, Overview, CategorySummary, ImportResult } from '../api/types'
import {
  getAccounts, getCategories, getTags, getOverview,
  getByCategory,
} from '../api/client'
import GlobalFilterBar from '../components/GlobalFilterBar'
import KpiCards from '../components/KpiCards'
import SpendingByCategory from '../components/SpendingByCategory'
import CategoryMovers from '../components/CategoryMovers'
import SpendingHeatmap from '../components/SpendingHeatmap'
import TopMerchants from '../components/TopMerchants'
import ImportModal from '../components/ImportModal'
import ImportLauncher, { type ImportLauncherHandle } from '../components/ImportLauncher'
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

/** Serialize GlobalFilters to URLSearchParams for the Transactions page.
 *  Special rule: day → from=<day>&to=<day>; no `day` param sent. */
function filtersToParams(f: GlobalFilters): string {
  const p = new URLSearchParams()
  if (f.from) p.set('from', f.from)
  if (f.to)   p.set('to',   f.to)
  // day overrides from/to (Transactions uses date range, not exact day)
  if (f.day)  { p.set('from', f.day); p.set('to', f.day) }
  if (f.account_id  !== undefined) p.set('account_id',  String(f.account_id))
  if (f.category_id !== undefined) p.set('category_id', String(f.category_id))
  if (f.flow)     p.set('flow',     f.flow)
  if (f.merchant) p.set('merchant', f.merchant)
  for (const tag of f.tags) p.append('tag', tag)
  return p.toString()
}

export default function Dashboard() {
  const { t } = useT()
  const navigate = useNavigate()
  const [filters, setFilters] = useState<GlobalFilters>(makeDefaultFilters)
  const [accounts,   setAccounts]   = useState<Account[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [allTags,    setAllTags]    = useState<Tag[]>([])

  const [overview,   setOverview]   = useState<AsyncState<Overview>>(idle())
  const [byCategory, setByCategory] = useState<AsyncState<CategorySummary[]>>(idle())

  // Unfiltered net — refreshes only on import, ignores all active filters
  const [globalOverview, setGlobalOverview] = useState<AsyncState<Overview>>(idle())

  // Previous-period data for comparison (Slice 1 + 2 — fetched client-side)
  const [prevOverview,    setPrevOverview]    = useState<AsyncState<Overview>>(idle())
  const [prevByCategory,  setPrevByCategory]  = useState<AsyncState<CategorySummary[]>>(idle())

  const [importFiles, setImportFiles] = useState<File[] | null>(null)
  const launcherRef = useRef<ImportLauncherHandle>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [toast,      setToast]      = useState<string | null>(null)

  function handleImportSuccess(result: ImportResult) {
    setImportFiles(null)
    setToast(t.toastSuccess(result.num_inserted, result.num_duplicates))
    setTimeout(() => setToast(null), 6000)
    setRefreshKey(k => k + 1)
  }

  useEffect(() => {
    getAccounts().then(setAccounts).catch(() => {})
    getCategories().then(setCategories).catch(() => {})
    getTags().then(setAllTags).catch(() => {})
  }, [])

  // Unfiltered overview — only re-runs when data changes (import), not on filter changes
  useEffect(() => {
    setGlobalOverview(idle())
    getOverview()
      .then(d  => setGlobalOverview({ loading: false, error: null,     data: d }))
      .catch(e => setGlobalOverview({ loading: false, error: String(e), data: null }))
  }, [refreshKey])

  useEffect(() => {
    const params = {
      from:        filters.from || undefined,
      to:          filters.to   || undefined,
      account_id:  filters.account_id,
      category_id: filters.category_id,
      tags:        filters.tags.length > 0 ? filters.tags : undefined,
      flow:        filters.flow,
      merchant:    filters.merchant || undefined,
      day:         filters.day || undefined,
    }

    setOverview(idle())
    setByCategory(idle())
    setPrevOverview(idle())
    setPrevByCategory(idle())

    getOverview(params)
      .then(d  => setOverview ({ loading: false, error: null,     data: d }))
      .catch(e => setOverview ({ loading: false, error: String(e), data: null }))

    // by-category donut shows ALL categories (no category_id) so the user can switch/clear
    getByCategory({ from: params.from, to: params.to, account_id: params.account_id, tags: params.tags, flow: params.flow, merchant: params.merchant, day: params.day })
      .then(d  => setByCategory({ loading: false, error: null,     data: d }))
      .catch(e => setByCategory({ loading: false, error: String(e), data: null }))

    // ── Previous-period fetches (Slice 1 + 2) ─────────────────────────────
    // Derive previous calendar month from the filter's from-date.
    const prevRange = previousCalendarMonth(filters.from)
    if (prevRange) {
      // prev period: spread merchant but NOT day (keep month-over-month comparison meaningful)
      const prevParams = { ...params, from: prevRange.from, to: prevRange.to, day: undefined }
      getOverview(prevParams)
        .then(d  => setPrevOverview({ loading: false, error: null,     data: d }))
        .catch(() => setPrevOverview({ loading: false, error: null,     data: null }))

      getByCategory({ from: prevRange.from, to: prevRange.to, account_id: params.account_id, tags: params.tags, flow: params.flow, merchant: params.merchant })
        .then(d  => setPrevByCategory({ loading: false, error: null,     data: d }))
        .catch(() => setPrevByCategory({ loading: false, error: null,     data: null }))
    } else {
      setPrevOverview({ loading: false, error: null, data: null })
      setPrevByCategory({ loading: false, error: null, data: null })
    }
  }, [filters, refreshKey])

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
            constantOverview={globalOverview.data}
          />
          <div className="dashboard-header-actions">
            <button
              className="btn-secondary"
              onClick={() => {
                const qs = filtersToParams(filters)
                navigate(`/transactions${qs ? `?${qs}` : ''}`)
              }}
            >
              {t.btnViewTransactions}
            </button>
            <button
              className="btn-primary"
              onClick={() => launcherRef.current?.open()}
            >
              {t.btnImport}
            </button>
          </div>
        </div>

        {/* Row: gastos por categoría | top comercios */}
        <div className="charts-row-category">
          <SpendingByCategory
            data={byCategory.data ?? []}
            categories={categories}
            loading={byCategory.loading}
            error={byCategory.error}
            selectedCategoryId={filters.category_id}
            onCategoryClick={(id) => setFilters(f => ({ ...f, category_id: id }))}
          />
          <TopMerchants
            globalFilters={filters}
            selectedMerchant={filters.merchant}
            onMerchantClick={m => setFilters(f => ({ ...f, merchant: f.merchant === m ? undefined : m }))}
            refreshKey={refreshKey}
            periodTotalExpense={overview.data?.total_expense ?? null}
          />
        </div>

        {/* Full-width: spending heatmap */}
        <div className="charts-row-full">
          <SpendingHeatmap
            globalFilters={filters}
            selectedDay={filters.day}
            onDayClick={day => setFilters(f => ({ ...f, day: f.day === day ? undefined : day }))}
            refreshKey={refreshKey}
          />
        </div>

        {/* Full-width: category movers */}
        <div className="charts-row-full">
          <CategoryMovers
            current={byCategory.data ?? []}
            previous={prevByCategory.data ?? []}
            categories={categories}
            loading={byCategory.loading}
            prevLoading={prevByCategory.loading}
            error={byCategory.error}
          />
        </div>
      </main>

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

      {toast && (
        <div className="toast">
          <span>{toast}</span>
          <button className="toast-close" onClick={() => setToast(null)} aria-label={t.toastClose}>✕</button>
        </div>
      )}
    </>
  )
}

