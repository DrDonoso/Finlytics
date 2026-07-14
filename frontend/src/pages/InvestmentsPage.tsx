import { useState, useEffect, useMemo } from 'react'
import { NavLink } from 'react-router-dom'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts'
import type { InvestmentPortfolio, InvestmentConnection } from '../api/types'
import { getInvestmentPortfolio, getConnections } from '../api/client'
import { useT, langLocale } from '../i18n'
import type { Dict } from '../i18n'

const ASSET_CLASS_COLORS: Record<string, string> = {
  equity:       '#2563eb',
  fixed_income: '#22c55e',
  cash:         '#94a3b8',
  other:        '#8b5cf6',
}

function parseYYYYMMDD(s: string): Date {
  const y = parseInt(s.slice(0, 4), 10)
  const m = parseInt(s.slice(4, 6), 10) - 1
  const d = parseInt(s.slice(6, 8), 10)
  return new Date(y, m, d)
}

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

export default function InvestmentsPage() {
  const { t, lang, formatCurrency } = useT()
  const locale = langLocale(lang)

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [portfolio, setPortfolio] = useState<InvestmentPortfolio | null>(null)
  const [connections, setConnections] = useState<InvestmentConnection[]>([])

  useEffect(() => {
    setLoading(true)
    setError(null)
    Promise.all([getInvestmentPortfolio(), getConnections()])
      .then(([portData, connData]) => {
        setPortfolio(portData)
        setConnections(connData)
        setLoading(false)
      })
      .catch(err => {
        setError(err instanceof Error ? err.message : String(err))
        setLoading(false)
      })
  }, [])

  const chartData = useMemo(() => {
    if (!portfolio) return []
    return portfolio.value_series.map(pt => ({
      date: parseYYYYMMDD(pt.date).toLocaleDateString(locale, { month: 'short', year: '2-digit' }),
      value: pt.value,
    }))
  }, [portfolio, locale])

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

  const activeConnection = connections.find(
    c => c.plugin_id === 'indexa-capital' && c.status === 'active',
  )

  if (loading) {
    return (
      <main className="dashboard">
        <div className="investments-header">
          <h1 className="investments-page-title">{t.investmentsTitle}</h1>
        </div>
        <div className="card">
          <div className="state-box">
            <span className="icon">⏳</span>
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
            <span className="icon">⚠️</span>
            <span>{t.invErrorLoading}: {error}</span>
          </div>
        </div>
      </main>
    )
  }

  const isConnected = portfolio !== null && portfolio.plugins_connected > 0

  return (
    <main className="dashboard">

      {/* 1. Page header */}
      <div className="investments-header">
        <h1 className="investments-page-title">{t.investmentsTitle}</h1>
      </div>

      {!isConnected ? (

        /* ── Empty state ── */
        <div className="card investments-holdings-card">
          <div className="card-title">{t.investmentsHoldingsTitle}</div>
          <div className="investments-empty">
            <span className="investments-empty__icon" aria-hidden="true">📊</span>
            <p className="investments-empty__text">{t.investmentsEmptyHoldings}</p>
            <NavLink to="/settings/connectors" className="btn-primary">
              {t.investmentsManageConnectors}
            </NavLink>
          </div>
        </div>

      ) : (
        <>
          {/* 2. Connected account header strip */}
          {activeConnection && (
            <div className="inv-account-header">
              <div className="inv-account-header__left">
                <span className="inv-account-header__icon" aria-hidden="true">🔗</span>
                <span className="inv-account-header__label">{activeConnection.account_label_masked}</span>
                {activeConnection.last_synced_at && (
                  <span className="inv-account-header__updated">
                    {t.invAccountUpdated(formatRelativeTime(activeConnection.last_synced_at, lang))}
                  </span>
                )}
              </div>
            </div>
          )}

          {/* 3. KPI row */}
          <div className="kpi-grid">
            <div className="kpi-card">
              <div className="kpi-label">{t.investmentsKpiTotalValue}</div>
              <div className="kpi-value">{formatCurrency(portfolio!.total_value)}</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-label">{t.investmentsKpiTotalInvested}</div>
              <div className="kpi-value">
                {formatCurrency(portfolio!.returns?.invested ?? portfolio!.total_invested ?? 0)}
              </div>
            </div>
            <div className="kpi-card">
              <div className="kpi-label">{t.investmentsKpiPnL}</div>
              <div className={`kpi-value ${(portfolio!.total_gain_loss ?? 0) >= 0 ? 'income' : 'expense'}`}>
                {portfolio!.total_gain_loss != null ? formatCurrency(portfolio!.total_gain_loss) : '—'}
              </div>
              {portfolio!.total_gain_loss_pct != null && (
                <div className="kpi-sub">
                  {portfolio!.total_gain_loss_pct >= 0 ? '+' : ''}
                  {(portfolio!.total_gain_loss_pct * 100).toFixed(2)}%
                </div>
              )}
            </div>
            <div className="kpi-card">
              <div className="kpi-label">{t.invKpiTwr}</div>
              <div className={`kpi-value ${(portfolio!.returns?.twr_annual ?? 0) >= 0 ? 'income' : 'expense'}`}>
                {portfolio!.returns?.twr_annual != null
                  ? `${(portfolio!.returns.twr_annual * 100).toFixed(2)}%`
                  : '—'}
              </div>
            </div>
            <div className="kpi-card">
              <div className="kpi-label">{t.invKpiXirr}</div>
              <div className={`kpi-value ${(portfolio!.returns?.xirr ?? 0) >= 0 ? 'income' : 'expense'}`}>
                {portfolio!.returns?.xirr != null
                  ? `${(portfolio!.returns.xirr * 100).toFixed(2)}%`
                  : '—'}
              </div>
            </div>
          </div>

          {/* 4. Charts row */}
          <div className="inv-charts-row">

            {/* 4a. Value over time */}
            <div className="card inv-chart-card inv-chart-card--value">
              <div className="card-title">{t.invChartValueTitle}</div>
              {chartData.length === 0 ? (
                <div className="state-box">
                  <span className="icon">📈</span>
                  <span>{t.noDataPeriod}</span>
                </div>
              ) : (
                <div className="inv-value-chart-wrap">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartData} margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
                      <defs>
                        <linearGradient id="invValueGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%"  stopColor="var(--primary)" stopOpacity={0.22} />
                          <stop offset="95%" stopColor="var(--primary)" stopOpacity={0.02} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                      <XAxis
                        dataKey="date"
                        tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                        tickLine={false}
                        axisLine={false}
                        interval="preserveStartEnd"
                      />
                      <YAxis
                        tickFormatter={v => `${((v as number) / 1000).toFixed(0)}k€`}
                        tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                        axisLine={false}
                        tickLine={false}
                        width={52}
                      />
                      <Tooltip
                        contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }}
                        labelStyle={{ color: 'var(--text)' }}
                        itemStyle={{ color: 'var(--text)' }}
                        formatter={(value: number) => [formatCurrency(value), t.investmentsKpiTotalValue]}
                      />
                      <Area
                        type="monotone"
                        dataKey="value"
                        stroke="var(--primary)"
                        strokeWidth={2}
                        fill="url(#invValueGrad)"
                        dot={false}
                        activeDot={{ r: 4, fill: 'var(--primary)' }}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>

            {/* 4b. Allocation donut */}
            <div className="card inv-chart-card inv-chart-card--allocation">
              <div className="card-title">{t.invChartAllocationTitle}</div>
              {allocationData.length === 0 ? (
                <div className="state-box">
                  <span className="icon">🍩</span>
                  <span>{t.noDataPeriod}</span>
                </div>
              ) : (
                <div className="cat-chart-layout">
                  <div className="cat-donut-wrap">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={allocationData}
                          cx="50%"
                          cy="50%"
                          innerRadius={72}
                          outerRadius={100}
                          dataKey="value"
                          paddingAngle={2}
                        >
                          {allocationData.map((entry, i) => (
                            <Cell key={i} fill={entry.color} opacity={0.9} />
                          ))}
                        </Pie>
                        <Tooltip
                          contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }}
                          labelStyle={{ color: 'var(--text)' }}
                          itemStyle={{ color: 'var(--text)' }}
                          formatter={(value: number, name: string) => [formatCurrency(value), assetLabel(name, t)]}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="cat-donut-center">
                      <span className="cat-donut-label">{t.invChartAllocationTitle}</span>
                      <span className="cat-donut-total">{formatCurrency(portfolio!.total_value)}</span>
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
                            <td className="cat-td-num">{formatCurrency(item.value)}</td>
                            <td className="cat-td-num cat-td-weight">
                              {portfolio!.total_value > 0
                                ? (item.value / portfolio!.total_value * 100).toFixed(1)
                                : '0.0'}%
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>

          </div>

          {/* 5. Holdings table */}
          <div className="card inv-holdings-card">
            <div className="card-title card-title--has-action">
              <span>{t.investmentsHoldingsTitle}</span>
              <span className="kpi-sub">{portfolio!.holdings.length} {t.invHoldingsCount}</span>
            </div>
            {portfolio!.holdings.length === 0 ? (
              <div className="state-box">
                <span className="icon">📋</span>
                <span>{t.invHoldingsEmpty}</span>
              </div>
            ) : (
              <div className="inv-holdings-table-wrap">
                <table className="inv-holdings-table">
                  <thead>
                    <tr>
                      <th className="inv-th-sortable">{t.invColName}</th>
                      <th>{t.invColISIN}</th>
                      <th>{t.invColClass}</th>
                      <th className="inv-th-num inv-th-sortable inv-th-sort-active">{t.invColValue}</th>
                      <th className="inv-th-num">{t.invColWeight}</th>
                      <th className="inv-th-num">{t.invColCost}</th>
                      <th className="inv-th-num inv-th-sortable">{t.invColPnL}</th>
                      <th className="inv-th-num">{t.invColPnLPct}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {portfolio!.holdings.map(h => {
                      const weight = portfolio!.total_value > 0
                        ? (h.current_value / portfolio!.total_value * 100).toFixed(1)
                        : '0.0'
                      const isPos = h.gain_loss >= 0
                      return (
                        <tr key={h.ticker}>
                          <td className="inv-td-name" title={h.name}>{h.name}</td>
                          <td className="inv-td-isin">{h.ticker}</td>
                          <td>
                            <span className={`inv-asset-class-badge inv-asset-class-badge--${h.asset_class.replace(/_/g, '-')}`}>
                              {assetLabel(h.asset_class, t)}
                            </span>
                          </td>
                          <td className="inv-td-num">{formatCurrency(h.current_value)}</td>
                          <td className="inv-td-weight">{weight}%</td>
                          <td className="inv-td-num">{formatCurrency(h.cost_basis)}</td>
                          <td className={`inv-td-num ${isPos ? 'inv-pnl--pos' : 'inv-pnl--neg'}`}>
                            {isPos ? '+' : ''}{formatCurrency(h.gain_loss)}
                          </td>
                          <td className={`inv-td-num ${isPos ? 'inv-pnl--pos' : 'inv-pnl--neg'}`}>
                            {isPos ? '+' : ''}{(h.gain_loss_pct * 100).toFixed(2)}%
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

    </main>
  )
}

