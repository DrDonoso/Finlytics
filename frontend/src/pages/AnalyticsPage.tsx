import { useState, useEffect } from 'react'
import type {
  Account, Category, Tag, GlobalFilters,
  MonthSummary, AccountSummary, CashflowSummary,
} from '../api/types'
import {
  getAccounts, getCategories, getTags,
  getByMonth, getByAccount, getCashflow,
} from '../api/client'
import GlobalFilterBar from '../components/GlobalFilterBar'
import SpendingOverTime from '../components/SpendingOverTime'
import SpendingByAccount from '../components/SpendingByAccount'
import CashflowSankey from '../components/CashflowSankey'
import { useT } from '../i18n'
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

export default function AnalyticsPage() {
  const { t } = useT()
  const [filters, setFilters] = useState<GlobalFilters>(makeDefaultFilters)
  const [accounts,   setAccounts]   = useState<Account[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [allTags,    setAllTags]    = useState<Tag[]>([])

  const [byMonth,   setByMonth]   = useState<AsyncState<MonthSummary[]>>(idle())
  const [byAccount, setByAccount] = useState<AsyncState<AccountSummary[]>>(idle())
  const [cashflow,  setCashflow]  = useState<AsyncState<CashflowSummary>>(idle())

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

    setByMonth(idle())
    setByAccount(idle())
    setCashflow(idle())

    getByMonth(params)
      .then(d  => setByMonth({ loading: false, error: null,     data: d }))
      .catch(e => setByMonth({ loading: false, error: String(e), data: null }))

    // by-account: no account_id so chart shows all accounts, but apply category + tag + flow
    getByAccount({ from: params.from, to: params.to, category_id: params.category_id, tags: params.tags, flow: params.flow })
      .then(d  => setByAccount({ loading: false, error: null,     data: d }))
      .catch(e => setByAccount({ loading: false, error: String(e), data: null }))

    getCashflow(params)
      .then(d  => setCashflow({ loading: false, error: null,     data: d }))
      .catch(e => setCashflow({ loading: false, error: String(e), data: null }))
  }, [filters])

  function handleFlowClick(flow: 'expense' | 'income' | undefined) {
    setFilters(f => ({ ...f, flow }))
  }

  return (
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
        <h1 className="analytics-page-title">{t.analyticsTitle}</h1>
      </div>

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
  )
}
