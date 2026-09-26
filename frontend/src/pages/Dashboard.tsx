import { useMemo, useState } from 'react'
import type { MouseEvent, ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Link, useNavigate } from 'react-router'
import {
  useAccounts, useByAccount, useCombinedOverview, useMortgageNetWorth,
  useOverview, useOverviewMonths, useStatementReminder,
} from '../api/queries'
import { errorMessage } from '../api/errors'
import InvestmentSnapshotCard from '../components/InvestmentSnapshotCard'
import MortgageSnapshotCard from '../components/MortgageSnapshotCard'
import { Private } from '../components/Money'
import { useT } from '../i18n'
import type { Lang } from '../i18n'
import { useNotifications } from '../contexts/NotificationsContext'
import { savingsRate } from '../utils/comparison'
import {
  IconInfo, IconAlert, IconLoading, IconArrowUpRight, IconArrowDownRight,
} from '../components/icons'

function formatEur(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return value.toLocaleString('es-ES', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
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

/** Full `from`/`to` range for a "YYYY-MM" month, used to filter the summary. */
function monthRange(ym: string): { from: string; to: string } {
  const [year, month] = ym.split('-').map(Number)
  const lastDay = new Date(year, month, 0).getDate()
  return { from: `${ym}-01`, to: `${ym}-${String(lastDay).padStart(2, '0')}` }
}

function formatMonthLabel(ym: string, lang: Lang): string {
  const [year, month] = ym.split('-').map(Number)
  const locale = lang === 'es' ? 'es-ES' : 'en-GB'
  const monthLabel = new Intl.DateTimeFormat(locale, { month: 'long' }).format(
    new Date(year, month - 1, 1),
  )
  return `${monthLabel.charAt(0).toLocaleUpperCase(locale)}${monthLabel.slice(1)} ${year}`
}

function PortalTooltipButton({
  text,
  className,
  children,
  ariaLabel,
  onClick,
}: {
  text: string
  className: string
  children: ReactNode
  ariaLabel?: string
  onClick?: (event: MouseEvent<HTMLButtonElement>) => void
}) {
  const [openTip, setOpenTip] = useState<{ text: string; x: number; y: number } | null>(null)

  const open = (target: HTMLElement) => {
    const r = target.getBoundingClientRect()
    setOpenTip({ text, x: r.left + r.width / 2, y: r.top })
  }

  return (
    <>
      <button
        className={className}
        type="button"
        aria-label={ariaLabel ?? text}
        onClick={onClick}
        onKeyDown={event => event.stopPropagation()}
        onMouseEnter={e => open(e.currentTarget)}
        onFocus={e => open(e.currentTarget)}
        onMouseLeave={() => setOpenTip(null)}
        onBlur={() => setOpenTip(null)}
      >
        {children}
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

function InfoTooltip({ text }: { text: string }) {
  return (
    <PortalTooltipButton text={text} className="inv-info-tip dashboard-info-tip">
      <IconInfo size={13} />
    </PortalTooltipButton>
  )
}

function StatementWarning({ label, text }: { label: string; text: string }) {
  return (
    <PortalTooltipButton
      text={text}
      ariaLabel={label}
      className="dashboard-statement-warning"
      onClick={event => event.stopPropagation()}
    >
      <IconAlert size={14} />
    </PortalTooltipButton>
  )
}

/**
 * Change in percentage points between two rates.
 *
 * Displayed as `pp` rather than `%` intentionally: the relative change between
 * two percentages is easily misread (going from 10% to 12% is +2 pp, not "+20%").
 */
function DeltaPill({ points, label }: { points: number | null; label: string }) {
  if (points === null) return null
  const rounded = Number(points.toFixed(1))
  const tone = rounded > 0 ? 'is-good' : rounded < 0 ? 'is-bad' : 'is-flat'
  const Arrow = rounded > 0 ? IconArrowUpRight : rounded < 0 ? IconArrowDownRight : null
  return (
    <div className={`dashboard-kpi-delta ${tone}`}>
      {Arrow && <Arrow size={12} />}
      <span>{rounded > 0 ? '+' : ''}{rounded.toFixed(1)} pp</span>
      <span className="dashboard-kpi-delta__label">{label}</span>
    </div>
  )
}

export default function Dashboard() {
  const { t, lang } = useT()
  const navigate = useNavigate()
  const { notifications } = useNotifications()

  // Stable empty array: `?? []` inline creates a new reference each render and would invalidate downstream deps.
  const EMPTY: never[] = useMemo(() => [], [])

  const accountsQuery = useAccounts()
  const overviewQuery = useOverview()
  const investmentsQuery = useCombinedOverview()
  const byAccountQuery = useByAccount()
  const monthsQuery = useOverviewMonths()
  const reminderQuery = useStatementReminder()
  const mortgageQuery = useMortgageNetWorth()

  const accounts = accountsQuery.data ?? EMPTY
  const byAccount = byAccountQuery.data ?? EMPTY
  const overview = overviewQuery.data ?? null
  const monthList = monthsQuery.data?.months ?? EMPTY
  const statementReminder = reminderQuery.data ?? null

  const accountsError = accountsQuery.error ? errorMessage(accountsQuery.error, t) : null
  const byAccountError = byAccountQuery.error ? errorMessage(byAccountQuery.error, t) : null

  // Compares the savings rate of the two most recent months that have data.
  // These are real backend figures, not estimates: if only one month exists
  // we show no delta rather than fabricating a baseline.
  const hasTwoMonths = monthList.length >= 2
  const prevMonth = hasTwoMonths ? monthList[monthList.length - 2] : null
  const curMonth = hasTwoMonths ? monthList[monthList.length - 1] : null
  const curRange = useMemo(() => (curMonth ? monthRange(curMonth) : undefined), [curMonth])
  const prevRange = useMemo(() => (prevMonth ? monthRange(prevMonth) : undefined), [prevMonth])
  const curSavingsQuery = useOverview(curRange, { enabled: hasTwoMonths })
  const prevSavingsQuery = useOverview(prevRange, { enabled: hasTwoMonths })

  /** Savings-rate shift (in pp) from the previous month to the most recent month with data. */
  const savingsRateShift = useMemo(() => {
    if (!hasTwoMonths || !curSavingsQuery.data || !prevSavingsQuery.data) return null
    const current = savingsRate(curSavingsQuery.data)
    const previous = savingsRate(prevSavingsQuery.data)
    if (current === null || previous === null) return null
    return current - previous
  }, [hasTwoMonths, curSavingsQuery.data, prevSavingsQuery.data])

  const monthsCount = monthList.length > 0 ? monthList.length : null
  const allTimeSavingsRate = overview ? savingsRate(overview) : null

  const averageMonthlyNet = overview && monthsCount && monthsCount > 0
    ? overview.net / monthsCount
    : null

  const averageMonthlyNetClass = averageMonthlyNet == null ? '' : averageMonthlyNet >= 0 ? 'inv-kpi-card__value--pos' : 'inv-kpi-card__value--neg'

  const accountByName = new Map(accounts.map(account => [accountKey(account.name), account]))
  const accountNetTotal = byAccount.reduce((sum, row) => sum + row.net, 0)
  const investmentsValue = investmentsQuery.data?.total_value_eur ?? 0

  // Partial degradation: an investments connector failure must not hide the
  // account net, which is still available. Previously either error would leave
  // net worth as "—" and discard data that was actually present.
  const investmentsFailed = Boolean(investmentsQuery.error)
  const accountsPending = byAccountQuery.isPending || Boolean(byAccountQuery.error)
  const netWorthPending = accountsPending || investmentsQuery.isPending
  // Mortgages only contribute when the user left them included; the endpoint
  // already filters, and it degrades to zeros so a failure never blanks the KPI.
  const mortgageNetWorth = mortgageQuery.data
  const mortgageContribution = mortgageNetWorth?.net_contribution ?? 0
  const hasMortgage = (mortgageNetWorth?.count ?? 0) > 0
  const totalNetWorth =
    accountNetTotal + (investmentsFailed ? 0 : investmentsValue) + mortgageContribution
  const missingStatementAccountIds = statementReminder?.year != null && statementReminder.month != null
    ? new Set(statementReminder.missing_account_ids)
    : new Set<number>()
  const statementReminderMonthLabel = statementReminder?.year != null && statementReminder.month != null
    ? formatMonthLabel(`${statementReminder.year}-${String(statementReminder.month).padStart(2, '0')}`, lang)
    : null

  return (
    <main className="dashboard">
      <div className="inv-kpi-strip dashboard-kpi-strip">
        {/* Net worth gets the brand gradient — it is the headline figure for the whole app. */}
        <div className="inv-kpi-card dashboard-kpi-hero">
          <div className="inv-kpi-card__label">{t.dashboardKpiTotalNet}</div>
          <div className="inv-kpi-card__value">
            {netWorthPending ? '—' : <Private>{formatEur(totalNetWorth)}</Private>}
          </div>
          {!netWorthPending && (
            <div className="dashboard-kpi-breakdown">
              <span>
                <span className="dashboard-kpi-breakdown__label">{t.dashboardNetWorthAccounts}</span>
                <Private>{formatEur(accountNetTotal)}</Private>
              </span>
              <span>
                <span className="dashboard-kpi-breakdown__label">{t.dashboardNetWorthInvestments}</span>
                {investmentsFailed
                  ? <span className="dashboard-kpi-breakdown__missing">{t.dashboardNetWorthUnavailable}</span>
                  : <Private>{formatEur(investmentsValue)}</Private>}
              </span>
              {hasMortgage && (
                <span>
                  <span className="dashboard-kpi-breakdown__label">{t.dashboardNetWorthMortgage}</span>
                  <Private>{formatEur(mortgageContribution)}</Private>
                </span>
              )}
            </div>
          )}
          {!netWorthPending && investmentsFailed && (
            <div className="dashboard-kpi-hero__notice">
              <IconAlert size={13} />
              <span>{t.dashboardNetWorthPartial}</span>
            </div>
          )}
        </div>
        <div className="inv-kpi-card">
          <div className="inv-kpi-card__label dashboard-kpi-label">
            <span>{t.dashboardKpiSavingsRate}</span>
            <InfoTooltip text={t.dashboardKpiSavingsRateInfo} />
          </div>
          <div className="inv-kpi-card__value">
            {overviewQuery.isPending ? '—' : overviewQuery.error ? '—' : signedPercent(allTimeSavingsRate)}
          </div>
          <DeltaPill points={savingsRateShift} label={t.dashboardSavingsRateVsPrevMonth} />
        </div>
        <div className="inv-kpi-card">
          <div className="inv-kpi-card__label dashboard-kpi-label">
            <span>{t.dashboardKpiAverageMonthlyNet}</span>
            <InfoTooltip text={t.dashboardKpiAverageMonthlyNetInfo} />
          </div>
          <div className={`inv-kpi-card__value ${averageMonthlyNetClass}`}>
            {overviewQuery.isPending || monthsQuery.isPending || overviewQuery.error || monthsQuery.error
              ? '—'
              : averageMonthlyNet === null
                ? '—'
                : <><Private>{signedCurrency(averageMonthlyNet)}</Private> {t.dashboardPerMonthSuffix}</>}
          </div>
          {monthsCount !== null && monthsCount > 0 && (
            <div className="dashboard-kpi-delta is-flat">
              <span className="dashboard-kpi-delta__label">{t.dashboardMonthsTracked(monthsCount)}</span>
            </div>
          )}
        </div>
      </div>

      <div className="card dashboard-accounts-card">
        <h3 className="card-title">{t.dashboardAccountsTitle}</h3>
        {accountsQuery.isPending || byAccountQuery.isPending ? (
          <div className="state-box">
            <IconLoading size={18} />
            <span>{t.loading}</span>
          </div>
        ) : accountsError || byAccountError ? (
          <div className="state-box error">
            <IconAlert size={18} />
            <span>{accountsError ?? byAccountError}</span>
          </div>
        ) : byAccount.length > 0 ? (
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
                {byAccount.map(row => {
                  const account = accountByName.get(accountKey(row.account))
                  const rowKey = account?.id ?? row.account
                  const netCls = row.net >= 0 ? 'inv-kpi-card__value--pos' : 'inv-kpi-card__value--neg'
                  const averageMonthlyExpense = monthsCount && monthsCount > 0 ? row.expense / monthsCount : null
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
                          <div className="dashboard-account-name-line">
                            <span className="dashboard-account-name">{account?.name ?? row.account}</span>
                            {account && statementReminderMonthLabel && missingStatementAccountIds.has(account.id) && (
                              <StatementWarning
                                label={t.dashboardStatementMissingLabel}
                                text={t.dashboardStatementMissingTooltip(statementReminderMonthLabel)}
                              />
                            )}
                          </div>
                          {account?.account_number_masked && (
                            <span className="dashboard-account-mask">{account.account_number_masked}</span>
                          )}
                        </div>
                      </td>
                      <td className={`cat-td-num dashboard-account-net private ${netCls}`}>{formatEur(row.net)}</td>
                      <td className="cat-td-num cat-td-weight">
                        {monthsQuery.isPending || monthsQuery.error ? '—' : <Private>{formatEur(averageMonthlyExpense)}</Private>}
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

      <MortgageSnapshotCard />

      {(() => {
        const activeEspp = notifications.find(n => n.source === 'espp')
        if (!activeEspp) return null
        const period = typeof activeEspp.title_args.period === 'string' ? activeEspp.title_args.period : null
        return (
          <div className="espp-reminder-banner" role="alert">
            <span className="espp-reminder-banner__text">
              <IconAlert size={16} />
              {t.esppReminderBanner(period)}
            </span>
            <Link to="/investments/fidelity-espp" className="espp-reminder-banner__link">
              {t.esppReminderAction}
            </Link>
          </div>
        )
      })()}
    </main>
  )
}
