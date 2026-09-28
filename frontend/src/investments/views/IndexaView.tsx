import { useState, useMemo } from 'react'
import { createPortal } from 'react-dom'
import { NavLink } from 'react-router'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts'
import { useInvestmentPortfolio, useConnections } from '../../api/queries'
import { errorMessage } from '../../api/errors'
import { useT, langLocale } from '../../i18n'
import type { Dict } from '../../i18n'
import { IconLoading, IconAlert, IconChartPie, IconChartLine, IconReceipt, IconBanknote, IconLink, IconChevronRight } from '../../components/icons'
import SortableTh from '../../components/SortableTh'
import Money, { Percent, Private } from '../../components/Money'
import CardHeader from '../../components/CardHeader'

const ASSET_CLASS_COLORS: Record<string, string> = {
  equity:       '#2563eb',
  fixed_income: '#22c55e',
  cash:         '#94a3b8',
  other:        '#8b5cf6',
}

const INSTRUMENT_PALETTE = [
  '#3b82f6', '#22c55e', '#f59e0b', '#ec4899', '#8b5cf6',
  '#06b6d4', '#f97316', '#64748b', '#84cc16', '#e11d48',
  '#0ea5e9', '#d946ef',
] as const

function formatRelativeTime(iso: string, lang: string): string {
  try {
    const diffMs = Date.now() - new Date(iso).getTime()
    const mins = Math.round(diffMs / 60000)
    if (mins < 2) return lang === 'es' ? 'ahora mismo' : 'just now'
    if (mins < 60) return lang === 'es' ? `hace ${mins} min` : `${mins} min ago`
    const hrs = Math.round(mins / 60)
    if (hrs < 24) return lang === 'es' ? `hace ${hrs} h` : `${hrs}h ago`
    const days = Math.round(hrs / 24)
    return lang === 'es' ? `hace ${days} día${days !== 1 ? 's' : ''}` : `${days} day${days !== 1 ? 's' : ''} ago`
  } catch {
    return iso
  }
}

function assetLabel(assetClass: string, t: Dict): string {
  const map: Record<string, string> = {
    equity:       t.invAssetEquity,
    fixed_income: t.invAssetFixed_income,
    cash:         t.invAssetCash,
    other:        t.invAssetOther,
  }
  return map[assetClass] ?? assetClass
}

function formatDDMMYYYY(isoDate: string): string {
  try {
    const parts = isoDate.split('-')
    if (parts.length < 3) return isoDate
    return `${parts[2]}/${parts[1]}/${parts[0]}`
  } catch {
    return isoDate
  }
}

function niceStep(range: number, isEur: boolean): number {
  if (!isEur) return 0.5
  if (range > 50000) return 5000
  if (range > 10000) return 1000
  if (range > 5000)  return 500
  if (range > 1000)  return 200
  if (range > 500)   return 100
  return 50
}

function niceFloor(value: number, step: number): number {
  return Math.floor(value / step) * step
}

function niceCeil(value: number, step: number): number {
  return Math.ceil(value / step) * step
}

type EvolutionPeriod = string
type EvolutionMode   = 'eur' | 'pct'
type MatrixMode      = 'pct' | 'eur'

export default function IndexaView() {
  const { t, lang, formatCurrency, formatPercent } = useT()
  const locale = langLocale(lang)

  const portfolioQuery = useInvestmentPortfolio()
  const connQuery = useConnections()
  const portfolio = portfolioQuery.data ?? null
  const connections = connQuery.data ?? []
  const loading = portfolioQuery.isPending || connQuery.isPending
  const queryError = portfolioQuery.error ?? connQuery.error
  const error = queryError ? errorMessage(queryError, t) : null

  const [evPeriod, setEvPeriod] = useState<EvolutionPeriod>('All')
  const [evMode,   setEvMode]   = useState<EvolutionMode>('eur')
  const [matrixMode, setMatrixMode] = useState<MatrixMode>('pct')

  type HoldingsSortCol = 'name' | 'isin' | 'class' | 'units' | 'value' | 'weight' | 'cost' | 'pnl' | 'pnlpct'
  const [sortCol, setSortCol] = useState<HoldingsSortCol>('value')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [openTip, setOpenTip] = useState<{ text: string; x: number; y: number } | null>(null)


  const evolutionYears = useMemo((): string[] => {
    if (!portfolio?.value_series?.length) return []
    const firstYear = parseInt(portfolio.value_series[0].date.slice(0, 4), 10)
    const lastYear  = new Date().getFullYear()
    return Array.from({ length: lastYear - firstYear + 1 }, (_, i) => String(firstYear + i))
  }, [portfolio])

  const evolutionData = useMemo(() => {
    if (!portfolio?.value_series?.length) return []

    const contribMap = new Map(
      (portfolio.contributions_series ?? []).map(pt => [pt.date, pt.value])
    )

    const now = new Date()
    const cutoff: Date | null = (() => {
      if (evPeriod === '1M') return new Date(now.getFullYear(), now.getMonth() - 1, now.getDate())
      if (evPeriod === '3M') return new Date(now.getFullYear(), now.getMonth() - 3, now.getDate())
      if (evPeriod === '6M') return new Date(now.getFullYear(), now.getMonth() - 6, now.getDate())
      if (evPeriod === '1A') return new Date(now.getFullYear() - 1, now.getMonth(), now.getDate())
      return null
    })()

    const filtered = portfolio.value_series.filter(pt => {
      if (evPeriod !== 'All' && evPeriod.length === 4) return pt.date.startsWith(evPeriod)
      if (cutoff) return new Date(pt.date) >= cutoff
      return true
    })

    if (evMode === 'pct') {
      const base  = filtered[0]?.value ?? 1
      const baseC = contribMap.get(filtered[0]?.date) ?? 1
      return filtered.map(pt => ({
        date:          pt.date,
        value:         base > 0 ? +((pt.value / base - 1) * 100).toFixed(2) : 0,
        contributions: (() => {
          const c = contribMap.get(pt.date)
          return c != null && baseC > 0 ? +((c / baseC - 1) * 100).toFixed(2) : null
        })(),
      }))
    }

    return filtered.map(pt => ({
      date:          pt.date,
      value:         pt.value,
      contributions: contribMap.get(pt.date) ?? null,
    }))
  }, [portfolio, evPeriod, evMode])

  const evolutionDomain = useMemo((): [number, number] => {
    if (evolutionData.length === 0) return [0, 100]
    const values: number[] = []
    for (const pt of evolutionData) {
      values.push(pt.value)
      if (pt.contributions != null) values.push(pt.contributions)
    }
    const minVal = Math.min(...values)
    const maxVal = Math.max(...values)
    const pad = minVal === maxVal
      ? Math.abs(minVal) * 0.1 || (evMode === 'eur' ? 500 : 1)
      : (maxVal - minVal) * 0.08
    const step = niceStep(maxVal - minVal + pad * 2, evMode === 'eur')
    return [niceFloor(minVal - pad, step), niceCeil(maxVal + pad, step)]
  }, [evolutionData, evMode])

  const allocationData = useMemo(() => {
    if (!portfolio) return []
    const map: Record<string, number> = {}
    for (const h of portfolio.holdings) {
      map[h.asset_class] = (map[h.asset_class] ?? 0) + h.current_value
    }
    return Object.entries(map)
      .filter(([, v]) => v > 0)
      .map(([name, value]) => ({ name, value, color: ASSET_CLASS_COLORS[name] ?? '#64748b' }))
  }, [portfolio])

  const instrumentSlices = useMemo(() => {
    if (!portfolio) return []
    // Several accounts can hold the same fund; the chart is by instrument, not by account.
    const byName = new Map<string, number>()
    for (const h of portfolio.holdings ?? []) {
      if (h.current_value > 0) byName.set(h.name, (byName.get(h.name) ?? 0) + h.current_value)
    }
    return [...byName]
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value)
  }, [portfolio])

  const sortedHoldings = useMemo(() => {
    if (!portfolio) return []
    const totalVal = portfolio.total_value
    const holdings = [...portfolio.holdings]
    const dir = sortDir === 'asc' ? 1 : -1
    holdings.sort((a, b) => {
      switch (sortCol) {
        case 'name':   return dir * a.name.localeCompare(b.name, locale)
        case 'isin':   return dir * a.ticker.localeCompare(b.ticker, locale)
        case 'class':  return dir * assetLabel(a.asset_class, t).localeCompare(assetLabel(b.asset_class, t), locale)
        case 'units':  return dir * (a.units - b.units)
        case 'value':  return dir * (a.current_value - b.current_value)
        case 'weight': return dir * (a.current_value - b.current_value)
        case 'cost':   return dir * (a.cost_basis - b.cost_basis)
        case 'pnl':    return dir * (a.gain_loss - b.gain_loss)
        case 'pnlpct': return dir * (a.gain_loss_pct - b.gain_loss_pct)
        default:       return 0
      }
    })
    void totalVal
    return holdings
  }, [portfolio, sortCol, sortDir, t, locale])

  function handleSortClick(col: HoldingsSortCol) {
    if (col === sortCol) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortCol(col)
      setSortDir(col === 'name' || col === 'isin' || col === 'class' ? 'asc' : 'desc')
    }
  }

  function holdingsHeader(col: HoldingsSortCol, label: string, info?: string) {
    const showTip = (el: HTMLElement) => {
      if (!info) return
      const r = el.getBoundingClientRect()
      setOpenTip({ text: info, x: r.left + r.width / 2, y: r.top })
    }
    return (
      <SortableTh
        label={label}
        active={col === sortCol}
        direction={sortDir}
        onSort={() => handleSortClick(col)}
        className={col === 'name' || col === 'isin' || col === 'class' ? undefined : 'inv-th-num'}
      >
        {info && (
          <>
            {' '}
            <button
              className="inv-info-tip"
              type="button"
              aria-label={info}
              onMouseEnter={e => showTip(e.currentTarget)}
              onFocus={e => showTip(e.currentTarget)}
              onMouseLeave={() => setOpenTip(null)}
              onBlur={() => setOpenTip(null)}
            >
              ?
            </button>
          </>
        )}
      </SortableTh>
    )
  }

  const activeConnection = connections.find(
    c => c.plugin_id === 'indexa-capital' && c.status === 'active',
  )

  const FIXED_PERIODS: Array<{ id: EvolutionPeriod; label: string }> = [
    { id: '1M', label: t.invPeriod1M },
    { id: '3M', label: t.invPeriod3M },
    { id: '6M', label: t.invPeriod6M },
    { id: '1A', label: t.invPeriod1A },
  ]

  if (loading) {
    return (
      <main className="dashboard">
        <div className="investments-header">
          <h1 className="investments-page-title">{t.investmentsTitle}</h1>
        </div>
        <div className="card">
          <div className="state-box">
            <IconLoading size={18} />
            <span>{t.loading}</span>
          </div>
        </div>
      </main>
    )
  }

  if (error) {
    return (
      <main className="dashboard">
        <div className="investments-header">
          <h1 className="investments-page-title">{t.investmentsTitle}</h1>
        </div>
        <div className="card">
          <div className="state-box error">
            <IconAlert size={18} />
            <span>{t.invErrorLoading}: {error}</span>
          </div>
        </div>
      </main>
    )
  }

  const isConnected = portfolio !== null && portfolio.plugins_connected > 0
  // Accounts exist but none could be read: zeros here would read as an empty portfolio.
  const unreadable = portfolio !== null && portfolio.accounts_unavailable > 0 && portfolio.last_updated == null

  const returnsMatrixCard = (() => {
    if (!portfolio?.monthly_returns || portfolio.monthly_returns.length === 0) return null
    const MONTHS = [
      t.invMonthENE, t.invMonthFEB, t.invMonthMAR, t.invMonthABR,
      t.invMonthMAY, t.invMonthJUN, t.invMonthJUL, t.invMonthAGO,
      t.invMonthSEP, t.invMonthOCT, t.invMonthNOV, t.invMonthDIC,
    ]
    const fmtCell = (v: number | null, mode: MatrixMode): string => {
      if (v == null) return ''
      if (mode === 'pct') return formatPercent(v, { unit: 'fraction', decimals: 2, signed: true })
      return v >= 0 ? `+${formatCurrency(v)}` : formatCurrency(v)
    }
    const cellCls = (v: number | null, extra = ''): string => {
      const base = `returns-matrix-cell${extra ? ` ${extra}` : ''}`
      if (v == null) return `${base} returns-matrix-cell--empty`
      if (v > 0)    return `${base} returns-matrix-cell--pos`
      if (v < 0)    return `${base} returns-matrix-cell--neg`
      return base
    }
    const sortedRows = [...portfolio.monthly_returns].sort((a, b) => a.year - b.year)
    return (
      <div className="card returns-matrix-card">
        <CardHeader
          className="returns-matrix-header"
          title={t.invMatrixTitle}
          action={
            <div className="inv-toggle">
              <button
                type="button"
                className={`inv-toggle-btn${matrixMode === 'pct' ? ' inv-toggle-btn--active' : ''}`}
                aria-pressed={matrixMode === 'pct'}
                onClick={() => setMatrixMode('pct')}
              >{t.invTogglePct}</button>
              <button
                type="button"
                className={`inv-toggle-btn${matrixMode === 'eur' ? ' inv-toggle-btn--active' : ''}`}
                aria-pressed={matrixMode === 'eur'}
                onClick={() => setMatrixMode('eur')}
              >{t.invToggleEur}</button>
            </div>
          }
        />
        {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- it scrolls, so keyboard users must be able to focus it */}
        <section className="returns-matrix-wrap" tabIndex={0} aria-label={t.invMatrixTitle}>
          <table className="returns-matrix">
            <thead>
              <tr>
                <th><span className="sr-only">{t.tableColYear}</span></th>
                {MONTHS.map(m => <th key={m}>{m}</th>)}
                <th className="returns-matrix-cell--total">{t.invMatrixTotal}</th>
                <th className="returns-matrix-cell--bench">{t.invMatrixBenchmark}</th>
              </tr>
            </thead>
            <tbody>
              {sortedRows.map(row => {
                const tot   = matrixMode === 'pct' ? row.total_pct : row.total_eur
                const bench = row.benchmark_pct
                return (
                  <tr key={row.year}>
                    <td className="returns-matrix-year">{row.year}</td>
                    {Array.from({ length: 12 }, (_, i) => {
                      const mk = String(i + 1)
                      const v  = matrixMode === 'pct'
                        ? (row.months_pct[mk] ?? null)
                        : (row.months_eur[mk] ?? null)
                      return <td key={i} className={cellCls(v, matrixMode === 'eur' ? 'private' : '')}>{fmtCell(v, matrixMode)}</td>
                    })}
                    <td className={cellCls(tot, matrixMode === 'eur' ? 'returns-matrix-cell--total private' : 'returns-matrix-cell--total')}>
                      {fmtCell(tot, matrixMode)}
                    </td>
                    <td className={cellCls(bench, 'returns-matrix-cell--bench')}>
                      {bench != null ? fmtCell(bench, 'pct') : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </section>
        {portfolio.drawdown && (
          <p className="inv-drawdown-note">
            {(() => {
              const eur = formatCurrency(Math.abs(portfolio.drawdown.max_drawdown_eur))
              const note = t.invDrawdownNote(
                formatPercent(Math.abs(portfolio.drawdown.max_drawdown), { unit: 'fraction' }),
                eur,
                new Date(portfolio.drawdown.start_date).toLocaleDateString(locale, { day: '2-digit', month: '2-digit', year: 'numeric' }),
                new Date(portfolio.drawdown.end_date).toLocaleDateString(locale, { day: '2-digit', month: '2-digit', year: 'numeric' }),
              )
              // Split on the rendered amount itself: if a translation stops
              // interpolating it there is nothing to hide and the sentence
              // still renders whole.
              const at = note.indexOf(eur)
              if (at === -1) return note
              return <>
                {note.slice(0, at)}
                <Private>{eur}</Private>
                {note.slice(at + eur.length)}
              </>
            })()}
          </p>
        )}
      </div>
    )
  })()

  return (
    <main className="dashboard">

      {/* 1. Page header */}
      <div className="investments-header">
        <h1 className="investments-page-title">{t.investmentsTitle}</h1>
      </div>

      {unreadable ? (

        <div className="card investments-holdings-card">
          <div className="investments-empty">
            <IconAlert size={30} className="investments-empty__icon" />
            <p className="investments-empty__text">{t.invAccountsUnreadable}</p>
            <NavLink to="/settings/connectors" className="btn-primary">
              {t.investmentsManageConnectors} <IconChevronRight size={14} />
            </NavLink>
          </div>
        </div>

      ) : !isConnected ? (

        /* ── Empty state ── */
        <div className="card investments-holdings-card">
          <h2 className="card-title">{t.investmentsHoldingsTitle}</h2>
          <div className="investments-empty">
            <IconChartPie size={30} className="investments-empty__icon" />
            <p className="investments-empty__text">{t.investmentsEmptyHoldings}</p>
            <NavLink to="/settings/connectors" className="btn-primary">
              {t.investmentsManageConnectors} <IconChevronRight size={14} />
            </NavLink>
          </div>
        </div>

      ) : (
        <>
          {/* 2. Connected account header strip */}
          {activeConnection && (
            <div className="inv-account-header">
              <div className="inv-account-header__left">
                <IconLink size={15} className="inv-account-header__icon" />
                <span className="inv-account-header__label">{activeConnection.account_label_masked}</span>
                {activeConnection.last_synced_at && (
                  <span className="inv-account-header__updated">
                    {t.invAccountUpdated(formatRelativeTime(activeConnection.last_synced_at, lang))}
                  </span>
                )}
              </div>
            </div>
          )}

          {portfolio!.accounts_unavailable > 0 && (
            <div className="inv-partial-banner" role="status">
              <IconAlert size={16} />
              <span>
                {t.invAccountsUnavailable(portfolio!.accounts_unavailable)}
                <NavLink to="/settings/connectors" className="inv-partial-banner__link">
                  {t.investmentsManageConnectors}
                </NavLink>
              </span>
            </div>
          )}

          {/* 3. Block 1 + allocation donut — new top row */}
          <div className="inv-top-row">

            {/* LEFT column: summary card + returns matrix */}
            <div className="inv-left-col">

            {/* Block 1 — "Valor total" summary card */}
            <div className="card inv-summary-card">

              <div className="inv-summary-row inv-summary-row--total">
                <span className="inv-summary-label">{t.invSummaryValorTotal}</span>
                <span className="inv-summary-value inv-summary-value--big">
                  <Money value={portfolio!.total_value} />
                </span>
              </div>

              <div className="inv-summary-row">
                <span className="inv-summary-label">{t.invSummaryRentabilidad}</span>
                <span className={`inv-summary-value ${
                  (portfolio!.returns?.pl ?? 0) >= 0 ? 'inv-summary-value--pos' : 'inv-summary-value--neg'
                }`}>
                  {portfolio!.returns?.pl != null
                    ? <>
                        <Money value={portfolio!.returns.pl} signed />
                        {portfolio!.returns.money_return != null
                          ? ` (${formatPercent(portfolio!.returns.money_return, { unit: 'fraction', signed: true })})`
                          : ''}
                      </>
                    : '—'}
                </span>
              </div>

              <div className="inv-summary-row">
                <span className="inv-summary-label">{t.invSummaryAportaciones}</span>
                <span className="inv-summary-value">
                  {portfolio!.returns?.aportaciones != null
                    ? <Private>{`+${formatCurrency(portfolio!.returns.aportaciones)}`}</Private>
                    : '—'}
                </span>
              </div>

              <div className="inv-summary-row">
                <span className="inv-summary-label">{t.invSummaryRetenciones}</span>
                <span className={`inv-summary-value${portfolio!.returns?.retenciones ? ' inv-summary-value--neg' : ''}`}>
                  {portfolio!.returns?.retenciones != null
                    ? <Private>{formatCurrency(-Math.abs(portfolio!.returns.retenciones))}</Private>
                    : '—'}
                </span>
              </div>

              {/* Metrics strip: TWR / MWR / Volatility */}
              <div className="inv-metrics-strip">
                <div className="inv-metric">
                  <div className="inv-metric-header">
                    <span className="inv-metric-label">{t.invMetricTwr}</span>
                    <button className="inv-info-tip" type="button" aria-label={t.invMetricTwrInfo}>
                      ?<span className="inv-info-bubble">{t.invMetricTwrInfo}</span>
                    </button>
                  </div>
                  <span className="inv-metric-sublabel">{t.invMetricSubAnnual}</span>
                  <span className={`inv-metric-value ${
                    (portfolio!.returns?.twr_annual ?? 0) >= 0
                      ? 'inv-metric-value--pos'
                      : 'inv-metric-value--neg'
                  }`}>
                    {portfolio!.returns?.twr_annual != null
                      ? formatPercent(portfolio!.returns.twr_annual, { unit: 'fraction', signed: true })
                      : '—'}
                  </span>
                </div>
                <div className="inv-metric">
                  <div className="inv-metric-header">
                    <span className="inv-metric-label">{t.invMetricMwr}</span>
                    <button className="inv-info-tip" type="button" aria-label={t.invMetricMwrInfo}>
                      ?<span className="inv-info-bubble">{t.invMetricMwrInfo}</span>
                    </button>
                  </div>
                  <span className="inv-metric-sublabel">{t.invMetricSubXirr}</span>
                  <span className={`inv-metric-value ${
                    (portfolio!.returns?.xirr ?? 0) >= 0
                      ? 'inv-metric-value--pos'
                      : 'inv-metric-value--neg'
                  }`}>
                    {portfolio!.returns?.xirr != null
                      ? formatPercent(portfolio!.returns.xirr, { unit: 'fraction', signed: true })
                      : '—'}
                  </span>
                </div>
                <div className="inv-metric">
                  <div className="inv-metric-header">
                    <span className="inv-metric-label">{t.invMetricVolatility}</span>
                    <button className="inv-info-tip" type="button" aria-label={t.invMetricVolInfo}>
                      ?<span className="inv-info-bubble">{t.invMetricVolInfo}</span>
                    </button>
                  </div>
                  <span className="inv-metric-sublabel">{t.invMetricSubAnnual}</span>
                  <span className="inv-metric-value inv-metric-value--neutral">
                    {portfolio!.returns?.volatility != null
                      ? formatPercent(portfolio!.returns.volatility, { unit: 'fraction' })
                      : '—'}
                  </span>
                </div>
              </div>

            </div>

            {returnsMatrixCard}

            </div>{/* end .inv-left-col */}

            {/* Two donuts: asset class + instrument */}
            <div className="inv-donuts-row">

              {/* Donut 1 — Allocation by asset class */}
              <div className="card">
                <h2 className="card-title">{t.invDonutAssetTitle}</h2>
                {allocationData.length === 0 ? (
                  <div className="state-box">
                    <IconChartPie size={18} />
                    <span>{t.noDataPeriod}</span>
                  </div>
                ) : (
                  <div className="cat-chart-layout">
                    <div className="cat-donut-wrap">
                      <ResponsiveContainer width="100%" height={220}>
                        <PieChart>
                          <Pie
                            data={allocationData}
                            cx="50%"
                            cy="50%"
                            innerRadius="58%"
                            outerRadius="80%"
                            dataKey="value"
                            paddingAngle={2}
                          >
                            {allocationData.map(entry => (
                              <Cell key={entry.name} fill={entry.color} opacity={0.9} />
                            ))}
                          </Pie>
                          <Tooltip
                            contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }}
                            labelStyle={{ color: 'var(--text)' }}
                            itemStyle={{ color: 'var(--text)' }}
                            formatter={(value, name) => [formatCurrency(Number(value)), assetLabel(String(name), t)]}
                          />
                        </PieChart>
                      </ResponsiveContainer>
                      <div className="cat-donut-center">
                        <span className="cat-donut-label">{t.invDonutAssetTitle}</span>
                        <span className="cat-donut-total"><Money value={portfolio!.total_value} /></span>
                      </div>
                    </div>
                    <div className="cat-table-wrap">
                      <table className="cat-table">
                        <thead>
                          <tr>
                            <th className="cat-th-name">{t.invColClass}</th>
                            <th className="cat-th-num">{t.catColValue}</th>
                            <th className="cat-th-num">{t.catColWeight}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {allocationData.map(item => (
                            <tr key={item.name} className="cat-row">
                              <td className="cat-td-name">
                                <div className="cat-td-name-inner">
                                  <span className="cat-swatch" style={{ background: item.color }} />
                                  <span className="cat-td-label">{assetLabel(item.name, t)}</span>
                                </div>
                              </td>
                              <td className="cat-td-num"><Money value={item.value} /></td>
                              <td className="cat-td-num cat-td-weight">
                                {formatPercent(portfolio!.total_value > 0 ? item.value / portfolio!.total_value : 0, { unit: 'fraction' })}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>

              {/* Donut 2 — Allocation by instrument */}
              <div className="card">
                <h2 className="card-title">{t.invDonutInstrumentTitle}</h2>
                {instrumentSlices.length === 0 ? (
                  <div className="state-box">
                    <IconChartPie size={18} />
                    <span>{t.noDataPeriod}</span>
                  </div>
                ) : (
                  <div className="cat-chart-layout">
                    <div className="cat-donut-wrap">
                      <ResponsiveContainer width="100%" height={220}>
                        <PieChart>
                          <Pie
                            data={instrumentSlices}
                            cx="50%"
                            cy="50%"
                            innerRadius="58%"
                            outerRadius="80%"
                            dataKey="value"
                            strokeWidth={1}
                            stroke="var(--surface)"
                          >
                            {instrumentSlices.map((slice, i) => (
                              <Cell key={slice.name} fill={INSTRUMENT_PALETTE[i % INSTRUMENT_PALETTE.length]} />
                            ))}
                          </Pie>
                        </PieChart>
                      </ResponsiveContainer>
                      <div className="cat-donut-center">
                        <span className="cat-donut-label">{t.invDonutInstrumentTitle}</span>
                        <span className="cat-donut-total"><Money value={portfolio!.total_value} /></span>
                      </div>
                    </div>
                    <div className="inv-donut-compact-legend">
                      {instrumentSlices.map((item, i) => (
                        <div key={item.name} className="inv-donut-legend-item">
                          <span
                            className="inv-donut-legend-swatch"
                            style={{ backgroundColor: INSTRUMENT_PALETTE[i % INSTRUMENT_PALETTE.length] }}
                          />
                          <span className="inv-donut-legend-name" title={item.name}>{item.name}</span>
                          <span className="inv-donut-legend-pct">
                            {portfolio!.total_value > 0
                              ? formatPercent(item.value / portfolio!.total_value, { unit: 'fraction' })
                              : '—'}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

            </div>

          </div>

          {/* 4. Block 2 — account evolution chart ("Evolución de la cuenta" in Indexa's own UI) */}
          <div className="card inv-evolution-card">

            <CardHeader
              className="inv-evolution-header"
              title={t.invEvolutionTitle}
              action={
                <div className="inv-evolution-controls">
                  <div className="inv-period-selector">
                    {FIXED_PERIODS.map(p => (
                      <button
                        key={p.id}
                        type="button"
                        className={`inv-period-btn${evPeriod === p.id ? ' inv-period-btn--active' : ''}`}
                        aria-pressed={evPeriod === p.id}
                        onClick={() => setEvPeriod(p.id)}
                      >{p.label}</button>
                    ))}
                    {evolutionYears.map(y => (
                      <button
                        key={y}
                        type="button"
                        className={`inv-period-btn${evPeriod === y ? ' inv-period-btn--active' : ''}`}
                        aria-pressed={evPeriod === y}
                        onClick={() => setEvPeriod(y)}
                      >{y}</button>
                    ))}
                    <button
                      type="button"
                      className={`inv-period-btn${evPeriod === 'All' ? ' inv-period-btn--active' : ''}`}
                      aria-pressed={evPeriod === 'All'}
                      onClick={() => setEvPeriod('All')}
                    >{t.invPeriodAll}</button>
                  </div>

                  <div className="inv-toggle">
                    <button
                      type="button"
                      className={`inv-toggle-btn${evMode === 'eur' ? ' inv-toggle-btn--active' : ''}`}
                      aria-pressed={evMode === 'eur'}
                      onClick={() => setEvMode('eur')}
                    >{t.invToggleEur}</button>
                    <button
                      type="button"
                      className={`inv-toggle-btn${evMode === 'pct' ? ' inv-toggle-btn--active' : ''}`}
                      aria-pressed={evMode === 'pct'}
                      onClick={() => setEvMode('pct')}
                    >{t.invTogglePct}</button>
                  </div>
                </div>
              }
            />

            {evolutionData.length === 0 ? (
              <div className="state-box">
                <IconChartLine size={18} />
                <span>{t.noDataPeriod}</span>
              </div>
            ) : (
              <>
                <div className="inv-evolution-chart-wrap">
                  <ResponsiveContainer width="100%" height={360}>
                    <LineChart data={evolutionData} margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                      <XAxis
                        dataKey="date"
                        tickFormatter={(isoDate: string) =>
                          new Date(isoDate).toLocaleDateString(locale, { month: 'short', year: '2-digit' })
                        }
                        tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                        tickLine={false}
                        axisLine={false}
                        interval="preserveStartEnd"
                      />
                      <YAxis
                        domain={evolutionDomain}
                        tickFormatter={evMode === 'eur'
                          ? (v: number) => `${(v / 1000).toFixed(0)}k€`
                          : (v: number) => formatPercent(v)}
                        tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                        axisLine={false}
                        tickLine={false}
                        width={52}
                      />
                      <Tooltip
                        contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }}
                        labelStyle={{ color: 'var(--text)' }}
                        itemStyle={{ color: 'var(--text)' }}
                        labelFormatter={(label) => formatDDMMYYYY(String(label))}
                        formatter={(value, name) => [
                          evMode === 'eur' ? formatCurrency(Number(value)) : formatPercent(Number(value), { decimals: 2 }),
                          name === 'value' ? t.invLegendPortfolio : t.invLegendContributions,
                        ]}
                      />
                      {/* Tu cartera — primary colour, solid */}
                      <Line
                        type="monotone"
                        dataKey="value"
                        stroke="var(--primary)"
                        strokeWidth={2}
                        dot={false}
                        activeDot={{ r: 4, fill: 'var(--primary)' }}
                        connectNulls
                      />
                      {/* Aportaciones — muted, dashed step-line */}
                      <Line
                        type="stepAfter"
                        dataKey="contributions"
                        stroke="var(--text-muted)"
                        strokeWidth={1.5}
                        strokeDasharray="5 3"
                        dot={false}
                        activeDot={false}
                        connectNulls
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>

                {/* Legend */}
                <div className="inv-chart-legend">
                  <span className="inv-chart-legend-item">
                    <span className="inv-chart-legend-swatch" style={{ background: 'var(--primary)' }} />
                    <span>{t.invLegendPortfolio}</span>
                  </span>
                  <span className="inv-chart-legend-item">
                    <span className="inv-chart-legend-swatch"
                      style={{ background: 'var(--text-muted)', backgroundImage: 'repeating-linear-gradient(90deg, var(--text-muted) 0 5px, transparent 5px 8px)' }} />
                    <span>{t.invLegendContributions}</span>
                  </span>
                </div>
              </>
            )}

          </div>

          {/* 6. Holdings table */}
          <div className="card inv-holdings-card">
            <CardHeader
              title={t.investmentsHoldingsTitle}
              action={<span className="kpi-sub">{portfolio!.holdings.length} {t.invHoldingsCount}</span>}
            />
            {portfolio!.holdings.length === 0 ? (
              <div className="state-box">
                <IconReceipt size={18} />
                <span>{t.invHoldingsEmpty}</span>
              </div>
            ) : (
              <div className="inv-holdings-table-wrap">
                <table className="inv-holdings-table">
                  <thead>
                    <tr>
                      {holdingsHeader('name', t.invColName)}
                      {holdingsHeader('isin', t.invColISIN)}
                      {holdingsHeader('class', t.invColClass)}
                      {holdingsHeader('units', t.invColUnits)}
                      {holdingsHeader('value', t.invColValue)}
                      {holdingsHeader('weight', t.invColWeight)}
                      {holdingsHeader('cost', t.invColCost)}
                      {holdingsHeader('pnl', t.invColPnL, t.invColPnLInfo)}
                      {holdingsHeader('pnlpct', t.invColPnLPct, t.invColPnLPctInfo)}
                    </tr>
                  </thead>
                  <tbody>
                    {sortedHoldings.map(h => {
                      const weight = formatPercent(
                        portfolio!.total_value > 0 ? h.current_value / portfolio!.total_value : 0,
                        { unit: 'fraction' },
                      )
                      const isPos = h.gain_loss >= 0
                      const fmtUnits = new Intl.NumberFormat(locale, {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 4,
                      }).format(h.units)
                      return (
                        <tr key={h.ticker}>
                          <td className="inv-td-name" title={h.name}>{h.name}</td>
                          <td className="inv-td-isin">{h.ticker}</td>
                          <td>
                            <span className={`inv-asset-class-badge inv-asset-class-badge--${h.asset_class.replace(/_/g, '-')}`}>
                              {assetLabel(h.asset_class, t)}
                            </span>
                          </td>
                          <td className="inv-td-num"><Private>{fmtUnits}</Private></td>
                          <td className="inv-td-num"><Money value={h.current_value} /></td>
                          <td className="inv-td-weight">{weight}</td>
                          <td className="inv-td-num"><Money value={h.cost_basis} /></td>
                          <td className={`inv-td-num ${isPos ? 'inv-pnl--pos' : 'inv-pnl--neg'}`}>
                            <Money value={h.gain_loss} signed />
                          </td>
                          <td className={`inv-td-num ${isPos ? 'inv-pnl--pos' : 'inv-pnl--neg'}`}>
                            <Percent value={h.gain_loss_pct} unit="fraction" signed decimals={2} />
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          {/* 7. Contributions & withdrawals table */}
          {(() => {
            const events = [...(portfolio?.contribution_events ?? [])].reverse()
            return (
              <div className="card inv-holdings-card">
                <h2 className="card-title">{t.invContribTableTitle}</h2>
                {events.length === 0 ? (
                  <div className="state-box">
                    <IconBanknote size={18} />
                    <span>{t.invContribEmpty}</span>
                  </div>
                ) : (
                  // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- it scrolls, so keyboard users must be able to focus it
                  <section className="inv-holdings-table-wrap" tabIndex={0} aria-label={t.invContribTableTitle}>
                    <table className="inv-holdings-table">
                      <thead>
                        <tr>
                          <th>{t.invContribColDate}</th>
                          <th className="inv-th-num">{t.invContribColAmount}</th>
                          <th className="inv-th-num">{t.invContribColCumulative}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {events.map(ev => {
                          const isPos = ev.amount >= 0
                          return (
                            <tr key={ev.date}>
                              <td>
                                <span className="inv-td-isin">{formatDDMMYYYY(ev.date)}</span>
                                {' '}
                                <span className={`inv-asset-class-badge inv-asset-class-badge--${ev.type === 'contribution' ? 'equity' : 'cash'}`}>
                                  {ev.type === 'contribution' ? t.invContribTypeContribution : t.invContribTypeWithdrawal}
                                </span>
                              </td>
                              <td className={`inv-td-num ${isPos ? 'inv-pnl--pos' : 'inv-pnl--neg'}`}>
                                <Money value={ev.amount} signed />
                              </td>
                              <td className="inv-td-num"><Money value={ev.cumulative} /></td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </section>
                )}
              </div>
            )
          })()}
        </>
      )}

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

    </main>
  )
}
