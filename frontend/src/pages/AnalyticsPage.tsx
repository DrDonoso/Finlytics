import { useState, useMemo } from 'react'
import type { GlobalFilters, SummaryParams } from '../api/types'
import {
  useAccounts, useCategories, useTags,
  useByMonth, useByAccount, useCashflow,
} from '../api/queries'
import { errorMessage } from '../api/errors'
import GlobalFilterBar from '../components/GlobalFilterBar'
import SpendingOverTime from '../components/SpendingOverTime'
import SpendingByAccount from '../components/SpendingByAccount'
import CashflowSankey from '../components/CashflowSankey'
import { useT } from '../i18n'
import { defaultRange } from '../utils'

function makeDefaultFilters(): GlobalFilters {
  return { ...defaultRange(), tags: [] }
}

export default function AnalyticsPage() {
  const { t } = useT()
  const [filters, setFilters] = useState<GlobalFilters>(makeDefaultFilters)

  const EMPTY: never[] = useMemo(() => [], [])
  const accounts   = useAccounts().data   ?? EMPTY
  const categories = useCategories().data ?? EMPTY
  const allTags    = useTags().data       ?? EMPTY

  const params: SummaryParams = useMemo(() => ({
    from:        filters.from || undefined,
    to:          filters.to   || undefined,
    account_id:  filters.account_id,
    category_id: filters.category_id,
    tags:        filters.tags.length > 0 ? filters.tags : undefined,
    flow:        filters.flow,
  }), [filters])

  // by-account: no account_id so all accounts appear, but category + tags + flow still apply
  const byAccountParams: SummaryParams = useMemo(() => ({
    from:        params.from,
    to:          params.to,
    category_id: params.category_id,
    tags:        params.tags,
    flow:        params.flow,
  }), [params])

  const byMonth   = useByMonth(params)
  const byAccount = useByAccount(byAccountParams)
  const cashflow  = useCashflow(params)

  function handleFlowClick(flow: 'expense' | 'income' | undefined) {
    setFilters(f => ({ ...f, flow }))
  }

  return (
    <main className="dashboard">
      <div className="tx-page-header">
        <h1 className="tx-page-title">{t.analyticsTitle}</h1>
      </div>
      <GlobalFilterBar
        filters={filters}
        accounts={accounts}
        categories={categories}
        tags={allTags}
        onChange={setFilters}
        onClear={() => setFilters(makeDefaultFilters())}
      />

      <div className="charts-row">
        <SpendingByAccount
          data={byAccount.data ?? []}
          loading={byAccount.isPending}
          error={byAccount.error ? errorMessage(byAccount.error, t) : null}
          selectedFlow={filters.flow}
          onFlowClick={handleFlowClick}
        />
        <SpendingOverTime
          data={byMonth.data ?? []}
          loading={byMonth.isPending}
          error={byMonth.error ? errorMessage(byMonth.error, t) : null}
          selectedFlow={filters.flow}
          onFlowClick={handleFlowClick}
        />
      </div>

      <CashflowSankey
        data={cashflow.data ?? null}
        loading={cashflow.isPending}
        error={cashflow.error ? errorMessage(cashflow.error, t) : null}
        categories={categories}
        selectedCategoryId={filters.category_id}
        onCategoryClick={(id) => setFilters(f => ({ ...f, category_id: id }))}
      />
    </main>
  )
}
