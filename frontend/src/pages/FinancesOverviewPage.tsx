import { useState, useRef, useMemo } from 'react'
import { useNavigate } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import type { GlobalFilters, ImportResult } from '../api/types'
import { queryKeys, useAccounts, useByAccount, useByCategory, useCategories, useOverview, useTags } from '../api/queries'
import { errorMessage } from '../api/errors'
import GlobalFilterBar from '../components/GlobalFilterBar'
import KpiCards from '../components/KpiCards'
import SpendingByCategory from '../components/SpendingByCategory'
import TopMerchants from '../components/TopMerchants'
import SpendingHeatmap from '../components/SpendingHeatmap'
import ImportModal from '../components/ImportModal'
import ImportLauncher, { type ImportLauncherHandle } from '../components/ImportLauncher'
import TransactionsTable from '../components/TransactionsTable'
import { Private } from '../components/Money'
import { useT, categoryLabel, formatDate } from '../i18n'
import { defaultRange } from '../utils'
import { serializeFilters, useUrlFilters } from '../hooks/useUrlFilters'
import { IconClose, IconChevronRight } from '../components/icons'
import { IS_DEMO } from '../demo/config'
import { useToast } from '../contexts/ToastContext'

export default function FinancesOverviewPage() {
  const { t, lang, formatCurrency } = useT()
  const showToast = useToast()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { filters, setFilters, defaults } = useUrlFilters(defaultRange)

  function openTransactions() {
    // A single heatmap day becomes a one-day range, so the date pickers there show it.
    const target = filters.day ? { ...filters, from: filters.day, to: filters.day, day: undefined } : filters
    const search = serializeFilters(target, { from: '', to: '' }).toString()
    navigate(search ? `/transactions?${search}` : '/transactions')
  }

  const accountsQuery = useAccounts()
  const categoriesQuery = useCategories()
  const tagsQuery = useTags()
  // Stable empty arrays: `?? []` creates a new instance on every render and
  // would force everything depending on them to recompute.
  const EMPTY: never[] = useMemo(() => [], [])
  const accounts = accountsQuery.data ?? EMPTY
  const categories = categoriesQuery.data ?? EMPTY
  const allTags = tagsQuery.data ?? EMPTY

  const [importFiles, setImportFiles] = useState<File[] | null>(null)
  const launcherRef = useRef<ImportLauncherHandle>(null)
  const [preZoomFilters, setPreZoomFilters] = useState<GlobalFilters | null>(null)

  function handleImportSuccess(result: ImportResult) {
    setImportFiles(null)
    showToast(t.toastSuccess(result.num_inserted, result.num_duplicates))
    // Importing changes transactions, so everything derived is stale.
    void queryClient.invalidateQueries()
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

  const historicNetQuery = useByAccount()
  const historicNet = historicNetQuery.data
    ? historicNetQuery.data.reduce((s, r) => s + r.net, 0)
    : null

  // Params form part of the cache key, so a slow response from a previous filter
  // can no longer overwrite the result for the active one.
  const summaryParams = useMemo(() => ({
    from:        filters.from || undefined,
    to:          filters.to   || undefined,
    account_id:  filters.account_id,
    category_id: filters.category_id,
    tags:        filters.tags.length > 0 ? filters.tags : undefined,
    flow:        filters.flow,
    merchant:    filters.merchant || undefined,
    day:         filters.day || undefined,
  }), [filters])

  // by-category intentionally ignores category_id: selecting a category would
  // collapse the chart to a single segment and make comparison useless.
  const categoryParams = useMemo(() => {
    const { category_id: _ignored, ...rest } = summaryParams
    return rest
  }, [summaryParams])

  const overviewQuery = useOverview(summaryParams)
  const byCategoryQuery = useByCategory(categoryParams)

  return (
    <>
      <main className="dashboard">
        <h1 className="sr-only">{t.navFinances}</h1>
        <div className="dashboard-header">
          <GlobalFilterBar
            filters={filters}
            defaults={defaults}
            accounts={accounts}
            categories={categories}
            tags={allTags}
            onChange={f => { setFilters(f); setPreZoomFilters(null) }}
            onClear={() => { setFilters({ ...defaults, tags: [] }); setPreZoomFilters(null) }}
          />
          <KpiCards
            overview={overviewQuery.data ?? null}
            loading={overviewQuery.isPending}
            error={overviewQuery.error ? errorMessage(overviewQuery.error, t) : null}
            compact
          />
          <div className="dashboard-header-actions">
            <div className="finances-historic-net-kpi">
              <div className="finances-historic-net-kpi__label">{t.dashboardAccountsNet}</div>
              <div className={`finances-historic-net-kpi__value${historicNet !== null ? historicNet >= 0 ? ' inv-kpi-card__value--pos' : ' inv-kpi-card__value--neg' : ''}`}>
                {historicNet === null ? '—' : <Private>{formatCurrency(historicNet)}</Private>}
              </div>
            </div>
            <button
              className="btn-secondary"
              onClick={openTransactions}
            >
              {t.btnViewTransactions} <IconChevronRight size={14} />
            </button>
            {/* Statement import runs LLM extraction server-side — not available
                in the static demo. */}
            {!IS_DEMO && (
              <button
                className="btn-primary"
                onClick={() => launcherRef.current?.open()}
              >
                {t.btnImport}
              </button>
            )}
          </div>
        </div>

        <div className="charts-row-category">
          <SpendingByCategory
            data={byCategoryQuery.data ?? []}
            categories={categories}
            loading={byCategoryQuery.isPending}
            error={byCategoryQuery.error ? errorMessage(byCategoryQuery.error, t) : null}
            selectedCategoryId={filters.category_id}
            onCategoryClick={(id) => setFilters(f => ({ ...f, category_id: f.category_id === id ? undefined : id }))}
          />
          <TopMerchants
            globalFilters={filters}
            selectedMerchant={filters.merchant}
            onMerchantClick={m => setFilters(f => ({ ...f, merchant: f.merchant === m ? undefined : m }))}
            periodTotalExpense={overviewQuery.data?.total_expense ?? null}
          />
        </div>

        {/* Full-width: spending heatmap */}
        <div className="charts-row-full">
          <SpendingHeatmap
            globalFilters={filters}
            onSelectPeriod={handleSelectPeriod}
            onResetPeriod={preZoomFilters ? handleResetPeriod : undefined}
          />
        </div>

        {/* Active drill-down filter chips */}
        {(filters.category_id || filters.merchant || filters.day || preZoomFilters) && (
          <div className="charts-row-full">
            <div className="drill-down-chips">
              <span className="drill-down-label">{t.drillDownActiveFilters}:</span>

              {filters.category_id !== undefined && (() => {
                const cat = categories.find(c => c.id === filters.category_id)
                const label = `${t.tableColCategory}: ${cat ? categoryLabel(cat.name, lang, dynamicEs) : filters.category_id}`
                return (
                  <span className="filter-chip">
                    {label}
                    <button
                      type="button"
                      className="filter-chip-remove"
                      onClick={() => setFilters(f => ({ ...f, category_id: undefined }))}
                      aria-label={t.tagChipRemoveNamed(label)}
                    ><IconClose size={13} /></button>
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
                    aria-label={t.tagChipRemoveNamed(`${t.colMerchant}: ${filters.merchant}`)}
                  ><IconClose size={13} /></button>
                </span>
              )}

              {preZoomFilters && (() => {
                const label = filters.from === filters.to
                  ? `${t.filterChipDay}: ${formatDate(filters.from || '', lang)}`
                  : `${formatDate(filters.from || '', lang)} – ${formatDate(filters.to || '', lang)}`
                return (
                  <span className="filter-chip">
                    {label}
                    <button
                      type="button"
                      className="filter-chip-remove"
                      onClick={handleResetPeriod}
                      aria-label={t.tagChipRemoveNamed(label)}
                    ><IconClose size={13} /></button>
                  </span>
                )
              })()}

              {filters.day && !preZoomFilters && (
                <span className="filter-chip">
                  {t.filterChipDay}: {formatDate(filters.day, lang)}
                  <button
                    type="button"
                    className="filter-chip-remove"
                    onClick={() => setFilters(f => ({ ...f, day: undefined }))}
                    aria-label={t.tagChipRemoveNamed(`${t.filterChipDay}: ${formatDate(filters.day, lang)}`)}
                  ><IconClose size={13} /></button>
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
            onEditSuccess={() => void queryClient.invalidateQueries({
              // The table has already patched the edited row; refetching it could drop that row from under the cursor.
              predicate: query => query.queryKey[0] !== queryKeys.transactionsAll[0],
            })}
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

    </>
  )
}
