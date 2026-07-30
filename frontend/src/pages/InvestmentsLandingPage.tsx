import { useState, useEffect } from 'react'
import { Link } from 'react-router'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'
import type { CombinedOverview } from '../api/types'
import { getCombinedOverview } from '../api/client'
import { getPluginLogo, pluginInitial } from '../investments/registry'
import { useT } from '../i18n'
import { IconLoading, IconChartBar, IconChartPie, IconChevronRight } from '../components/icons'

const PROVIDER_COLORS: Record<string, string> = {
  indexa:   '#2563eb',
  fidelity: '#f59e0b',
}

const ASSET_CLASS_COLORS: Record<string, string> = {
  equity:       '#2563eb',
  fixed_income: '#22c55e',
  espp_stock:   '#f59e0b',
  cash:         '#94a3b8',
  other:        '#8b5cf6',
}

const FALLBACK_PALETTE = [
  '#3b82f6', '#f97316', '#8b5cf6', '#eab308', '#10b981',
  '#ef4444', '#ec4899', '#06b6d4',
]

function sliceColor(map: Record<string, string>, key: string, idx: number): string {
  return map[key] ?? FALLBACK_PALETTE[idx % FALLBACK_PALETTE.length]
}

function formatEurLocale(n: number): string {
  return new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR' }).format(n)
}

function signedEur(n: number): string {
  return `${n >= 0 ? '+' : ''}${formatEurLocale(n)}`
}

export default function InvestmentsLandingPage() {
  const { t } = useT()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [overview, setOverview] = useState<CombinedOverview | null>(null)

  useEffect(() => {
    getCombinedOverview()
      .then(data => { setOverview(data); setLoading(false) })
      .catch(e => { setError(String(e)); setLoading(false) })
  }, [])

  if (loading) {
    return (
      <main className="dashboard">
        <div className="investments-header">
          <h1 className="investments-page-title">{t.invCombinedTitle}</h1>
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

  if (error || !overview || overview.providers.length === 0) {
    return (
      <main className="dashboard">
        <div className="investments-header">
          <h1 className="investments-page-title">{t.invCombinedTitle}</h1>
        </div>
        <div className="card investments-holdings-card">
          <div className="investments-empty">
            <IconChartBar size={28} className="investments-empty__icon" />
            <p className="investments-empty__text">{t.invLandingEmpty}</p>
            <Link to="/settings/connectors" className="btn-primary">
              {t.investmentsManageConnectors} <IconChevronRight size={14} />
            </Link>
          </div>
        </div>
      </main>
    )
  }

  const gainLossCls = overview.total_gain_loss_eur == null
    ? ''
    : overview.total_gain_loss_eur >= 0
      ? 'inv-kpi-card__value--pos'
      : 'inv-kpi-card__value--neg'

  const providerDonutData = overview.by_provider.map((item, i) => ({
    name: item.provider,
    label: item.label,
    value: item.value_eur,
    color: sliceColor(PROVIDER_COLORS, item.provider, i),
  }))

  const assetDonutData = overview.by_asset_class.map((item, i) => ({
    name: item.asset_class,
    label: item.label,
    value: item.value_eur,
    color: sliceColor(ASSET_CLASS_COLORS, item.asset_class, i),
  }))

  return (
    <main className="dashboard">
      <div className="investments-header">
        <h1 className="investments-page-title">{t.invCombinedTitle}</h1>
      </div>

      {/* KPI strip */}
      <div className="inv-kpi-strip">
        <div className="inv-kpi-card">
          <div className="inv-kpi-card__label">{t.invCombinedTotalValue}</div>
          <div className="inv-kpi-card__value">{formatEurLocale(overview.total_value_eur)}</div>
        </div>
        <div className="inv-kpi-card">
          <div className="inv-kpi-card__label">{t.invSummaryAportaciones}</div>
          <div className="inv-kpi-card__value">{overview.total_invested_eur == null ? '—' : formatEurLocale(overview.total_invested_eur)}</div>
        </div>
        <div className="inv-kpi-card">
          <div className="inv-kpi-card__label">{t.invCombinedTotalGain}</div>
          <div className={`inv-kpi-card__value ${gainLossCls}`}>
            {overview.total_gain_loss_eur == null ? '—' : signedEur(overview.total_gain_loss_eur)}
          </div>
          <div className={`inv-kpi-card__sub ${gainLossCls}`}>
            {overview.total_gain_loss_pct == null
              ? '—'
              : `${overview.total_gain_loss_pct >= 0 ? '+' : ''}${overview.total_gain_loss_pct.toFixed(1)} %`}
          </div>
        </div>
      </div>

      {/* Donuts row */}
      <div className="inv-donuts-row">
        {/* Donut 1 — By provider */}
        <div className="card">
          <h3 className="card-title">{t.invCombinedByProvider}</h3>
          {providerDonutData.length === 0 ? (
            <div className="state-box"><IconChartPie size={18} /><span>{t.noDataPeriod}</span></div>
          ) : (
            <div className="cat-chart-layout">
              <div className="cat-donut-wrap">
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    <Pie
                      data={providerDonutData}
                      cx="50%" cy="50%"
                      innerRadius={72} outerRadius={100}
                      dataKey="value"
                      paddingAngle={2}
                    >
                      {providerDonutData.map((entry, i) => (
                        <Cell key={i} fill={entry.color} opacity={0.9} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }}
                      labelStyle={{ color: 'var(--text)' }}
                      itemStyle={{ color: 'var(--text)' }}
                      formatter={(value, name) => {
                        const item = providerDonutData.find(d => d.name === name)
                        return [formatEurLocale(Number(value)), item?.label ?? String(name)]
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
                <div className="cat-donut-center">
                  <span className="cat-donut-label">{t.invCombinedByProvider}</span>
                  <span className="cat-donut-total">{formatEurLocale(overview.total_value_eur)}</span>
                </div>
              </div>
              <div className="cat-table-wrap">
                <table className="cat-table">
                  <thead>
                    <tr>
                      <th className="cat-th-name">{t.invCombinedByProvider}</th>
                      <th className="cat-th-num">{t.catColValue}</th>
                      <th className="cat-th-num">{t.catColWeight}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {providerDonutData.map(item => (
                      <tr key={item.name} className="cat-row">
                        <td className="cat-td-name">
                          <div className="cat-td-name-inner">
                            <span className="cat-swatch" style={{ background: item.color }} />
                            <span className="cat-td-label">{item.label}</span>
                          </div>
                        </td>
                        <td className="cat-td-num">{formatEurLocale(item.value)}</td>
                        <td className="cat-td-num cat-td-weight">
                          {overview.total_value_eur > 0
                            ? `${(item.value / overview.total_value_eur * 100).toFixed(1)} %`
                            : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* Donut 2 — By asset class */}
        <div className="card">
          <h3 className="card-title">{t.invCombinedByAssetClass}</h3>
          {assetDonutData.length === 0 ? (
            <div className="state-box"><IconChartPie size={18} /><span>{t.noDataPeriod}</span></div>
          ) : (
            <div className="cat-chart-layout">
              <div className="cat-donut-wrap">
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    <Pie
                      data={assetDonutData}
                      cx="50%" cy="50%"
                      innerRadius={72} outerRadius={100}
                      dataKey="value"
                      paddingAngle={2}
                    >
                      {assetDonutData.map((entry, i) => (
                        <Cell key={i} fill={entry.color} opacity={0.9} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }}
                      labelStyle={{ color: 'var(--text)' }}
                      itemStyle={{ color: 'var(--text)' }}
                      formatter={(value, name) => {
                        const item = assetDonutData.find(d => d.name === name)
                        return [formatEurLocale(Number(value)), item?.label ?? String(name)]
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
                <div className="cat-donut-center">
                  <span className="cat-donut-label">{t.invCombinedByAssetClass}</span>
                  <span className="cat-donut-total">{formatEurLocale(overview.total_value_eur)}</span>
                </div>
              </div>
              <div className="cat-table-wrap">
                <table className="cat-table">
                  <thead>
                    <tr>
                      <th className="cat-th-name">{t.invCombinedByAssetClass}</th>
                      <th className="cat-th-num">{t.catColValue}</th>
                      <th className="cat-th-num">{t.catColWeight}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {assetDonutData.map(item => (
                      <tr key={item.name} className="cat-row">
                        <td className="cat-td-name">
                          <div className="cat-td-name-inner">
                            <span className="cat-swatch" style={{ background: item.color }} />
                            <span className="cat-td-label">{item.label}</span>
                          </div>
                        </td>
                        <td className="cat-td-num">{formatEurLocale(item.value)}</td>
                        <td className="cat-td-num cat-td-weight">
                          {overview.total_value_eur > 0
                            ? `${(item.value / overview.total_value_eur * 100).toFixed(1)} %`
                            : '—'}
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

      {/* Provider cards */}
      <div className="inv-provider-cards">
        {overview.providers.map(provider => {
          const gainCls = provider.gain_loss_eur == null
            ? ''
            : provider.gain_loss_eur >= 0
              ? 'inv-provider-card__gain--positive'
              : 'inv-provider-card__gain--negative'
          return (
            <Link
              key={provider.id}
              to={provider.route}
              className="card inv-provider-card"
            >
              <div className="inv-provider-card__header">
                {getPluginLogo(provider.id) ? (
                  <img src={getPluginLogo(provider.id) ?? ''} alt={provider.name} className="plugin-logo inv-provider-card__icon" />
                ) : (
                  <span className="plugin-logo-fallback inv-provider-card__icon" aria-label={provider.name}>{pluginInitial(provider.name)}</span>
                )}
                <span className="inv-provider-card__name">{provider.name}</span>
              </div>
              <div className="inv-provider-card__value">{provider.value_eur == null ? '—' : formatEurLocale(provider.value_eur)}</div>
              <div className={`inv-provider-card__gain ${gainCls}`}>
                {provider.gain_loss_eur == null || provider.gain_loss_pct == null
                  ? '—'
                  : <>
                      {signedEur(provider.gain_loss_eur)}
                      {' '}
                      ({`${provider.gain_loss_pct >= 0 ? '+' : ''}${provider.gain_loss_pct.toFixed(1)} %`})
                    </>
                }
              </div>
              <span className="inv-provider-card__cta">
                {t.invProviderCta} <IconChevronRight size={13} />
              </span>
            </Link>
          )
        })}
      </div>
    </main>
  )
}
