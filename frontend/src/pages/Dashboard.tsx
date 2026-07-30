import { useState, useEffect } from 'react'
import type { MouseEvent, ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Link, useNavigate } from 'react-router'
import type { Account, AccountSummary, CombinedOverview, Overview, StatementReminder } from '../api/types'
import {
  getAccounts, getOverview, getOverviewMonths, getByAccount,
  getCombinedOverview, getStatementReminder,
} from '../api/client'
import InvestmentSnapshotCard from '../components/InvestmentSnapshotCard'
import { useT } from '../i18n'
import type { Lang } from '../i18n'
import { useNotifications } from '../contexts/NotificationsContext'
import { savingsRate } from '../utils/comparison'
import {
  IconInfo, IconAlert, IconLoading, IconArrowUpRight, IconArrowDownRight,
} from '../components/icons'

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

/** Rango `from`/`to` de un mes "YYYY-MM" completo, para filtrar el resumen. */
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
 * Variación en puntos porcentuales entre dos tasas.
 *
 * Se muestra en `pp` y no en `%` a propósito: la variación relativa entre dos
 * porcentajes se malinterpreta con facilidad (pasar del 10 % al 12 % es +2 pp,
 * no «+20 %»).
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

  const [accounts, setAccounts] = useState<AsyncState<Account[]>>(idle())
  const [overview, setOverview] = useState<AsyncState<Overview>>(idle())
  const [investmentsOverview, setInvestmentsOverview] = useState<AsyncState<CombinedOverview>>(idle())
  const [byAccount, setByAccount] = useState<AsyncState<AccountSummary[]>>(idle())
  const [months, setMonths] = useState<AsyncState<string[]>>(idle())
  /** Variación de la tasa de ahorro (en pp) del último mes con datos frente al anterior. */
  const [savingsRateShift, setSavingsRateShift] = useState<number | null>(null)
  const [refreshKey] = useState(0)
  const [statementReminder, setStatementReminder] = useState<StatementReminder | null>(null)

  useEffect(() => {
    getAccounts()
      .then(d => setAccounts({ loading: false, error: null, data: d }))
      .catch(e => setAccounts({ loading: false, error: String(e), data: null }))
    getStatementReminder().then(setStatementReminder).catch(() => setStatementReminder(null))
  }, [])

  // Fetch available months once for global monthly averages.
  useEffect(() => {
    setMonths(idle())
    getOverviewMonths()
      .then(({ months: list }) => setMonths({ loading: false, error: null, data: list }))
      .catch(e => setMonths({ loading: false, error: String(e), data: null }))
  }, [refreshKey])

  // Compara la tasa de ahorro de los dos últimos meses con datos.
  // Son datos reales del backend, no una estimación: si sólo hay un mes, no se
  // muestra variación en vez de inventar una referencia.
  const monthList = months.data
  useEffect(() => {
    if (!monthList || monthList.length < 2) { setSavingsRateShift(null); return }

    const [previous, current] = monthList.slice(-2)
    let cancelled = false

    Promise.all([getOverview(monthRange(current)), getOverview(monthRange(previous))])
      .then(([currentOverview, previousOverview]) => {
        if (cancelled) return
        const currentRate = savingsRate(currentOverview)
        const previousRate = savingsRate(previousOverview)
        if (currentRate === null || previousRate === null) { setSavingsRateShift(null); return }
        setSavingsRateShift(currentRate - previousRate)
      })
      .catch(() => { if (!cancelled) setSavingsRateShift(null) })

    // Evita que una respuesta lenta pise el estado tras cambiar de mes.
    return () => { cancelled = true }
  }, [monthList])

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

  const monthsCount = months.data?.length ?? null
  const allTimeSavingsRate = overview.data ? savingsRate(overview.data) : null

  const averageMonthlyNet = overview.data && monthsCount && monthsCount > 0
    ? overview.data.net / monthsCount
    : null

  const averageMonthlyNetClass = averageMonthlyNet == null ? '' : averageMonthlyNet >= 0 ? 'inv-kpi-card__value--pos' : 'inv-kpi-card__value--neg'

  const accountByName = new Map((accounts.data ?? []).map(account => [accountKey(account.name), account]))
  const accountNetTotal = byAccount.data?.reduce((sum, row) => sum + row.net, 0) ?? 0
  const investmentsValue = investmentsOverview.data?.total_value_eur ?? 0

  // Degradación parcial: un fallo al leer las inversiones no debe ocultar el
  // neto de las cuentas, que sí está disponible.  Antes cualquiera de los dos
  // errores dejaba el patrimonio en «—» y se perdía información que sí se tenía.
  const investmentsFailed = Boolean(investmentsOverview.error)
  const accountsPending = byAccount.loading || Boolean(byAccount.error)
  const netWorthPending = accountsPending || investmentsOverview.loading
  const totalNetWorth = accountNetTotal + (investmentsFailed ? 0 : investmentsValue)
  const missingStatementAccountIds = statementReminder?.year != null && statementReminder.month != null
    ? new Set(statementReminder.missing_account_ids)
    : new Set<number>()
  const statementReminderMonthLabel = statementReminder?.year != null && statementReminder.month != null
    ? formatMonthLabel(`${statementReminder.year}-${String(statementReminder.month).padStart(2, '0')}`, lang)
    : null

  return (
    <main className="dashboard">
      <div className="inv-kpi-strip dashboard-kpi-strip">
        {/* Patrimonio total lleva el degradado de marca: es la cifra que resume
            toda la aplicación, así que deja de ser una tarjeta más entre tres. */}
        <div className="inv-kpi-card dashboard-kpi-hero">
          <div className="inv-kpi-card__label">{t.dashboardKpiTotalNet}</div>
          <div className="inv-kpi-card__value">
            {netWorthPending ? '—' : formatEur(totalNetWorth)}
          </div>
          {!netWorthPending && (
            <div className="dashboard-kpi-breakdown">
              <span>
                <span className="dashboard-kpi-breakdown__label">{t.dashboardNetWorthAccounts}</span>
                {formatEur(accountNetTotal)}
              </span>
              <span>
                <span className="dashboard-kpi-breakdown__label">{t.dashboardNetWorthInvestments}</span>
                {investmentsFailed
                  ? <span className="dashboard-kpi-breakdown__missing">{t.dashboardNetWorthUnavailable}</span>
                  : formatEur(investmentsValue)}
              </span>
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
            {overview.loading ? '—' : overview.error ? '—' : signedPercent(allTimeSavingsRate)}
          </div>
          <DeltaPill points={savingsRateShift} label={t.dashboardSavingsRateVsPrevMonth} />
        </div>
        <div className="inv-kpi-card">
          <div className="inv-kpi-card__label dashboard-kpi-label">
            <span>{t.dashboardKpiAverageMonthlyNet}</span>
            <InfoTooltip text={t.dashboardKpiAverageMonthlyNetInfo} />
          </div>
          <div className={`inv-kpi-card__value ${averageMonthlyNetClass}`}>
            {overview.loading || months.loading || overview.error || months.error
              ? '—'
              : averageMonthlyNet === null
                ? '—'
                : `${signedCurrency(averageMonthlyNet)} ${t.dashboardPerMonthSuffix}`}
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
        {accounts.loading || byAccount.loading ? (
          <div className="state-box">
            <IconLoading size={18} />
            <span>{t.loading}</span>
          </div>
        ) : accounts.error || byAccount.error ? (
          <div className="state-box error">
            <IconAlert size={18} />
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
                      <td className={`cat-td-num dashboard-account-net ${netCls}`}>{formatEur(row.net)}</td>
                      <td className="cat-td-num cat-td-weight">
                        {months.loading || months.error ? '—' : formatEur(averageMonthlyExpense)}
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
