import { useState, useEffect, useRef, useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import type { Account, Category, Tag, GlobalFilters, Overview, CategorySummary, ImportResult } from '../api/types'
import { getAccounts, getCategories, getTags, getOverview, getByCategory,
  getByAccount, formatEur,
} from '../api/client'
import GlobalFilterBar from '../components/GlobalFilterBar'
import KpiCards from '../components/KpiCards'
import SpendingByCategory from '../components/SpendingByCategory'
import TopMerchants from '../components/TopMerchants'
import SpendingHeatmap from '../components/SpendingHeatmap'
import ImportModal from '../components/ImportModal'
import ImportLauncher, { type ImportLauncherHandle } from '../components/ImportLauncher'
import TransactionsTable from '../components/TransactionsTable'
import { useT, categoryLabel, formatDate } from '../i18n'
import { defaultRange } from '../utils'

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
  const { t, lang } = useT()
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

  const [importFiles, setImportFiles] = useState<File[] | null>(null)
  const launcherRef = useRef<ImportLauncherHandle>(null)
  const [refreshKey, setRefreshKey]   = useState(0)
  const [toast,      setToast]        = useState<string | null>(null)
  const [preZoomFilters, setPreZoomFilters] = useState<GlobalFilters | null>(null)
  const [historicNet, setHistoricNet] = useState<number | null>(null)

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

  // Computed label map for category names (ES translations)
  const dynamicEs = useMemo(
    () => Object.fromEntries(categories.filter(c => c.name_es).map(c => [c.name, c.name_es!])),
    [categories],
  )

  // Clears only chart-driven drill-downs; preserves GlobalFilterBar's period/account/tags
  function handleClearDrillDowns() {
    if (preZoomFilters) {
      setFilters(f => ({
        ...f,
        from: preZoomFilters.from,
        to:   preZoomFilters.to,
        category_id: undefined,
        merchant:    undefined,
        day:         undefined,
      }))
      setPreZoomFilters(null)
    } else {
      setFilters(f => ({ ...f, category_id: undefined, merchant: undefined, day: undefined }))
    }
  }

  useEffect(() => {
    getAccounts().then(setAccounts).catch(() => {})
    getCategories().then(setCategories).catch(() => {})
    getTags().then(setAllTags).catch(() => {})
    getByAccount()
      .then(rows => setHistoricNet(rows.reduce((s, r) => s + r.net, 0)))
      .catch(() => {})
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

    getOverview(params)
      .then(d  => setOverview({ loading: false, error: null,     data: d }))
      .catch(e => setOverview({ loading: false, error: String(e), data: null }))

    getByCategory({ from: params.from, to: params.to, account_id: params.account_id, tags: params.tags, flow: params.flow, merchant: params.merchant, day: params.day })
      .then(d  => setByCategory({ loading: false, error: null,     data: d }))
      .catch(e => setByCategory({ loading: false, error: String(e), data: null }))
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
          />
          <div className="dashboard-header-actions">
            <div className="finances-historic-net-kpi">
              <div className="finances-historic-net-kpi__label">{t.dashboardAccountsNet}</div>
              <div className={`finances-historic-net-kpi__value${historicNet !== null ? historicNet >= 0 ? ' inv-kpi-card__value--pos' : ' inv-kpi-card__value--neg' : ''}`}>
                {historicNet === null ? '—' : formatEur(historicNet)}
              </div>
            </div>
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
            onCategoryClick={(id) => setFilters(f => ({ ...f, category_id: f.category_id === id ? undefined : id }))}
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

        {/* Active drill-down filter chips */}
        {(filters.category_id || filters.merchant || filters.day || preZoomFilters) && (
          <div className="charts-row-full">
            <div className="drill-down-chips">
              <span className="drill-down-label">{t.drillDownActiveFilters}:</span>

              {filters.category_id !== undefined && (() => {
                const cat = categories.find(c => c.id === filters.category_id)
                return (
                  <span className="filter-chip">
                    {t.tableColCategory}: {cat ? categoryLabel(cat.name, lang, dynamicEs) : filters.category_id}
                    <button
                      type="button"
                      className="filter-chip-remove"
                      onClick={() => setFilters(f => ({ ...f, category_id: undefined }))}
                      aria-label={t.filterClearChip}
                    >✕</button>
                  </span>
                )
              })()}

              {filters.merchant && (
                <span className="filter-chip">
                  {t.colMerchant}: {filters.merchant}
                  <button
                    type="button"
                    className="filter-chip-remove"
                    onClick={() => setFilters(f => ({ ...f, merchant: undefined }))}
                    aria-label={t.filterClearChip}
                  >✕</button>
                </span>
              )}

              {preZoomFilters && (
                <span className="filter-chip">
                  {filters.from === filters.to
                    ? `${t.filterChipDay}: ${formatDate(filters.from || '', lang)}`
                    : `${formatDate(filters.from || '', lang)} – ${formatDate(filters.to || '', lang)}`}
                  <button
                    type="button"
                    className="filter-chip-remove"
                    onClick={handleResetPeriod}
                    aria-label={t.filterClearChip}
                  >✕</button>
                </span>
              )}

              {filters.day && !preZoomFilters && (
                <span className="filter-chip">
                  {t.filterChipDay}: {formatDate(filters.day, lang)}
                  <button
                    type="button"
                    className="filter-chip-remove"
                    onClick={() => setFilters(f => ({ ...f, day: undefined }))}
                    aria-label={t.filterClearChip}
                  >✕</button>
                </span>
              )}

              <button
                type="button"
                className="btn-clear-filters"
                onClick={handleClearDrillDowns}
              >{t.drillDownClearAll}</button>
            </div>
          </div>
        )}

        {/* Full-width: drill-down transactions table */}
        <div className="charts-row-full">
          <TransactionsTable
            globalFilters={filters}
            categories={categories}
            allTags={allTags}
            merchant={filters.merchant}
            hideInternalFilters
            onEditSuccess={() => setRefreshKey(k => k + 1)}
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
