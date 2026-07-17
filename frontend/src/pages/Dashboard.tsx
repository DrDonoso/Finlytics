import { useState, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { Link, useNavigate } from 'react-router-dom'
import type { Account, AccountSummary, CombinedOverview, Overview, FidelityReminderResponse } from '../api/types'
import {
  getAccounts, getOverview, getOverviewMonths, getByAccount,
  getCombinedOverview, getFidelityReminder,
} from '../api/client'
import InvestmentSnapshotCard from '../components/InvestmentSnapshotCard'
import { useT } from '../i18n'

interface AsyncState<T> {
  loading: boolean
  error: string | null
  data: T | null
}

function idle<T>(): AsyncState<T> { return { loading: true, error: null, data: null } }

function formatEur(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return value.toLocaleString('es-ES', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
  })
}

function signedPercent(value: number | null): string {
  if (value === null) return '—'
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)} %`
}

function signedCurrency(value: number | null): string {
  if (value === null) return '—'
  return `${value >= 0 ? '+' : ''}${formatEur(value)}`
}

function accountKey(name: string): string {
  return name.trim().toLowerCase()
}

function InfoTooltip({ text }: { text: string }) {
  const [openTip, setOpenTip] = useState<{ text: string; x: number; y: number } | null>(null)

  const open = (target: HTMLElement) => {
    const r = target.getBoundingClientRect()
    setOpenTip({ text, x: r.left + r.width / 2, y: r.top })
  }

  return (
    <>
      <button
        className="inv-info-tip dashboard-info-tip"
        type="button"
        aria-label={text}
        onMouseEnter={e => open(e.currentTarget)}
        onFocus={e => open(e.currentTarget)}
        onMouseLeave={() => setOpenTip(null)}
        onBlur={() => setOpenTip(null)}
      >
        ⓘ
      </button>
      {openTip && createPortal(
        <div
          role="tooltip"
          style={{
            position: 'fixed',
            left: openTip.x,
            top: openTip.y - 10,
            transform: 'translate(-50%, -100%)',
            zIndex: 4000,
            pointerEvents: 'none',
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: '8px',
            boxShadow: '0 4px 16px rgba(0,0,0,0.16)',
            padding: '10px 12px',
            maxWidth: '240px',
            width: 'max-content',
            fontSize: '12px',
            lineHeight: 1.5,
            color: 'var(--text-muted)',
            textAlign: 'left',
            fontWeight: 400,
            whiteSpace: 'normal',
          }}
        >
          {openTip.text}
        </div>,
        document.body,
      )}
    </>
  )
}

export default function Dashboard() {
  const { t } = useT()
  const navigate = useNavigate()

  const [accounts, setAccounts] = useState<AsyncState<Account[]>>(idle())
  const [overview, setOverview] = useState<AsyncState<Overview>>(idle())
  const [investmentsOverview, setInvestmentsOverview] = useState<AsyncState<CombinedOverview>>(idle())
  const [byAccount, setByAccount] = useState<AsyncState<AccountSummary[]>>(idle())
  const [monthsCount, setMonthsCount] = useState<AsyncState<number>>(idle())
  const [refreshKey] = useState(0)

  // ESPP upload-reminder banner
  const [esppReminder, setEsppReminder] = useState<FidelityReminderResponse | null>(null)

  useEffect(() => {
    getAccounts()
      .then(d => setAccounts({ loading: false, error: null, data: d }))
      .catch(e => setAccounts({ loading: false, error: String(e), data: null }))
    getFidelityReminder().then(setEsppReminder).catch(() => {})
  }, [])

  // Fetch available months once for global monthly averages.
  useEffect(() => {
    setMonthsCount(idle())
    getOverviewMonths()
      .then(({ months }) => setMonthsCount({ loading: false, error: null, data: months.length }))
      .catch(e => setMonthsCount({ loading: false, error: String(e), data: null }))
  }, [refreshKey])

  // Fetch all-time account nets and investment value for the cross-domain KPI strip.
  useEffect(() => {
    setInvestmentsOverview(idle())
    setByAccount(idle())

    getByAccount()
      .then(d => setByAccount({ loading: false, error: null, data: d }))
      .catch(e => setByAccount({ loading: false, error: String(e), data: null }))

    getCombinedOverview()
      .then(d => setInvestmentsOverview({ loading: false, error: null, data: d }))
      .catch(e => setInvestmentsOverview({ loading: false, error: String(e), data: null }))
  }, [refreshKey])

  // Fetch all-time overview for historical/global KPIs.
  useEffect(() => {
    setOverview(idle())

    getOverview()
      .then(d => setOverview({ loading: false, error: null, data: d }))
      .catch(e => setOverview({ loading: false, error: String(e), data: null }))
  }, [refreshKey])

  const savingsRate = overview.data && overview.data.total_income > 0
    ? (overview.data.net / overview.data.total_income) * 100
    : null

  const averageMonthlyNet = overview.data && monthsCount.data && monthsCount.data > 0
    ? overview.data.net / monthsCount.data
    : null

  const averageMonthlyNetClass = averageMonthlyNet == null ? '' : averageMonthlyNet >= 0 ? 'inv-kpi-card__value--pos' : 'inv-kpi-card__value--neg'

  const accountByName = new Map((accounts.data ?? []).map(account => [accountKey(account.name), account]))
  const accountNetTotal = byAccount.data?.reduce((sum, row) => sum + row.net, 0) ?? 0
  const investmentsValue = investmentsOverview.data?.total_value_eur ?? 0
  const totalNetWorth = accountNetTotal + investmentsValue

  return (
    <main className="dashboard">
      <div className="inv-kpi-strip dashboard-kpi-strip">
        <div className="inv-kpi-card">
          <div className="inv-kpi-card__label">{t.dashboardKpiTotalNet}</div>
          <div className="inv-kpi-card__value">
            {byAccount.loading || investmentsOverview.loading || byAccount.error || investmentsOverview.error ? '—' : formatEur(totalNetWorth)}
          </div>
        </div>
        <div className="inv-kpi-card">
          <div className="inv-kpi-card__label dashboard-kpi-label">
            <span>{t.dashboardKpiSavingsRate}</span>
            <InfoTooltip text={t.dashboardKpiSavingsRateInfo} />
          </div>
          <div className="inv-kpi-card__value">
            {overview.loading ? '—' : overview.error ? '—' : signedPercent(savingsRate)}
          </div>
        </div>
        <div className="inv-kpi-card">
          <div className="inv-kpi-card__label dashboard-kpi-label">
            <span>{t.dashboardKpiAverageMonthlyNet}</span>
            <InfoTooltip text={t.dashboardKpiAverageMonthlyNetInfo} />
          </div>
          <div className={`inv-kpi-card__value ${averageMonthlyNetClass}`}>
            {overview.loading || monthsCount.loading || overview.error || monthsCount.error
              ? '—'
              : averageMonthlyNet === null
                ? '—'
                : `${signedCurrency(averageMonthlyNet)} ${t.dashboardPerMonthSuffix}`}
          </div>
        </div>
      </div>

      <div className="card dashboard-accounts-card">
        <h3 className="card-title">{t.dashboardAccountsTitle}</h3>
        {accounts.loading || byAccount.loading ? (
          <div className="state-box">
            <span className="icon">⏳</span>
            <span>{t.loading}</span>
          </div>
        ) : accounts.error || byAccount.error ? (
          <div className="state-box error">
            <span className="icon">⚠️</span>
            <span>{accounts.error ?? byAccount.error}</span>
          </div>
        ) : byAccount.data && byAccount.data.length > 0 ? (
          <div className="cat-table-wrap dashboard-accounts-table-wrap">
            <table className="cat-table dashboard-accounts-table">
              <thead>
                <tr>
                  <th className="cat-th-name">{t.dashboardAccountsAccount}</th>
                  <th className="cat-th-num">{t.dashboardAccountsNet}</th>
                  <th className="cat-th-num">{t.dashboardAccountsAvgMonthlyExpense}</th>
                </tr>
              </thead>
              <tbody>
                {byAccount.data.map(row => {
                  const account = accountByName.get(accountKey(row.account))
                  const rowKey = account?.id ?? row.account
                  const netCls = row.net >= 0 ? 'inv-kpi-card__value--pos' : 'inv-kpi-card__value--neg'
                  const averageMonthlyExpense = monthsCount.data && monthsCount.data > 0 ? row.expense / monthsCount.data : null
                  return (
                    <tr
                      key={rowKey}
                      className={`cat-row dashboard-account-row${account ? '' : ' dashboard-account-row--disabled'}`}
                      onClick={() => account && navigate(`/finances?account_id=${account.id}`)}
                      onKeyDown={event => {
                        if (account && (event.key === 'Enter' || event.key === ' ')) {
                          event.preventDefault()
                          navigate(`/finances?account_id=${account.id}`)
                        }
                      }}
                      role={account ? 'button' : undefined}
                      tabIndex={account ? 0 : undefined}
                    >
                      <td className="cat-td-name">
                        <div className="dashboard-account-name-cell">
                          <span className="dashboard-account-name">{account?.name ?? row.account}</span>
                          {account?.account_number_masked && (
                            <span className="dashboard-account-mask">{account.account_number_masked}</span>
                          )}
                        </div>
                      </td>
                      <td className={`cat-td-num dashboard-account-net ${netCls}`}>{formatEur(row.net)}</td>
                      <td className="cat-td-num cat-td-weight">
                        {monthsCount.loading || monthsCount.error ? '—' : formatEur(averageMonthlyExpense)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="state-box">
            <span>{t.dashboardAccountsEmpty}</span>
          </div>
        )}
      </div>

      <InvestmentSnapshotCard />

      {esppReminder?.overdue && (
        <div className="espp-reminder-banner" role="alert">
          <span>⚠ {t.esppReminderBanner(esppReminder.period_label)}</span>
          <Link to="/investments/fidelity-espp" className="espp-reminder-banner__link">
            {t.esppReminderAction}
          </Link>
        </div>
      )}
    </main>
  )
}
