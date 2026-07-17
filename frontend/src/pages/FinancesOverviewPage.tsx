import { useState, useEffect, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import type { Account, Category, Tag, GlobalFilters, Overview, CategorySummary, ImportResult } from '../api/types'
import {
  getAccounts, getCategories, getTags, getOverview, getByCategory,
} from '../api/client'
import GlobalFilterBar from '../components/GlobalFilterBar'
import KpiCards from '../components/KpiCards'
import SpendingByCategory from '../components/SpendingByCategory'
import TopMerchants from '../components/TopMerchants'
import SpendingHeatmap from '../components/SpendingHeatmap'
import CategoryMovers from '../components/CategoryMovers'
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

export default function FinancesOverviewPage() {
  const { t } = useT()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [filters, setFilters] = useState<GlobalFilters>(() => {
    const next = makeDefaultFilters()
    const accountId = Number(searchParams.get('account_id'))
    if (Number.isFinite(accountId) && accountId > 0) next.account_id = accountId
    return next
  })
  const [accounts,   setAccounts]   = useState<Account[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [allTags,    setAllTags]    = useState<Tag[]>([])

  const [overview,      setOverview]      = useState<AsyncState<Overview>>(idle())
  const [byCategory,    setByCategory]    = useState<AsyncState<CategorySummary[]>>(idle())
  const [prevOverview,   setPrevOverview]   = useState<AsyncState<Overview>>(idle())
  const [prevByCategory, setPrevByCategory] = useState<AsyncState<CategorySummary[]>>(idle())

  const [importFiles, setImportFiles] = useState<File[] | null>(null)
  const launcherRef = useRef<ImportLauncherHandle>(null)
  const [refreshKey, setRefreshKey]   = useState(0)
  const [toast,      setToast]        = useState<string | null>(null)
  const [preZoomFilters, setPreZoomFilters] = useState<GlobalFilters | null>(null)

  function handleImportSuccess(result: ImportResult) {
    setImportFiles(null)
    setToast(t.toastSuccess(result.num_inserted, result.num_duplicates))
    setTimeout(() => setToast(null), 6000)
    setRefreshKey(k => k + 1)
  }

  function handleSelectPeriod(from: string, to: string) {
    setPreZoomFilters(filters)
    setFilters(f => ({ ...f, from, to, day: undefined }))
  }

  function handleResetPeriod() {
    if (preZoomFilters) {
      setFilters(preZoomFilters)
      setPreZoomFilters(null)
    }
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
      merchant:    filters.merchant || undefined,
      day:         filters.day || undefined,
    }

    setOverview(idle())
    setByCategory(idle())
    setPrevOverview(idle())
    setPrevByCategory(idle())

    getOverview(params)
      .then(d  => setOverview({ loading: false, error: null,     data: d }))
      .catch(e => setOverview({ loading: false, error: String(e), data: null }))

    getByCategory({ from: params.from, to: params.to, account_id: params.account_id, tags: params.tags, flow: params.flow, merchant: params.merchant, day: params.day })
      .then(d  => setByCategory({ loading: false, error: null,     data: d }))
      .catch(e => setByCategory({ loading: false, error: String(e), data: null }))

    const prevRange = previousCalendarMonth(filters.from)
    if (prevRange) {
      const prevParams = { ...params, from: prevRange.from, to: prevRange.to, day: undefined }
      getOverview(prevParams)
        .then(d  => setPrevOverview({ loading: false, error: null, data: d }))
        .catch(() => setPrevOverview({ loading: false, error: null, data: null }))
      getByCategory({ from: prevRange.from, to: prevRange.to, account_id: params.account_id, tags: params.tags, flow: params.flow, merchant: params.merchant })
        .then(d  => setPrevByCategory({ loading: false, error: null, data: d }))
        .catch(() => setPrevByCategory({ loading: false, error: null, data: null }))
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
            onChange={f => { setFilters(f); setPreZoomFilters(null) }}
            onClear={() => { setFilters(makeDefaultFilters()); setPreZoomFilters(null) }}
          />
          <KpiCards
            overview={overview.data}
            loading={overview.loading}
            error={overview.error}
            compact
            previousOverview={prevOverview.data}
          />
          <div className="dashboard-header-actions">
            <button
              className="btn-secondary"
              onClick={() => navigate('/transactions')}
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
            onSelectPeriod={handleSelectPeriod}
            onResetPeriod={preZoomFilters ? handleResetPeriod : undefined}
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
