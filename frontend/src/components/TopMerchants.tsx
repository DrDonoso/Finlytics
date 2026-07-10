import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
} from 'recharts'
import { useState, useEffect } from 'react'
import type { MerchantSummary, GlobalFilters } from '../api/types'
import { getByMerchant } from '../api/client'
import { useT } from '../i18n'

const FALLBACK_COLORS = [
  '#2563eb', '#ef4444', '#22c55e', '#f59e0b', '#8b5cf6',
  '#ec4899', '#06b6d4', '#84cc16', '#f97316', '#64748b',
]

interface Props {
  globalFilters: GlobalFilters
  selectedMerchant?: string
  onMerchantClick: (m: string | undefined) => void
  refreshKey?: number
  periodTotalExpense?: number | null
}

export default function TopMerchants({ globalFilters, selectedMerchant, onMerchantClick, refreshKey = 0, periodTotalExpense }: Props) {
  const { t, formatCurrency } = useT()
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)
  const [data, setData]       = useState<MerchantSummary[]>([])

  useEffect(() => {
    setLoading(true)
    setError(null)
    // byMerchant: pass category_id + day (+ from/to/account_id/tags/flow). Do NOT pass merchant.
    getByMerchant({
      from:        globalFilters.from  || undefined,
      to:          globalFilters.to    || undefined,
      account_id:  globalFilters.account_id,
      category_id: globalFilters.category_id,
      tags:        globalFilters.tags.length > 0 ? globalFilters.tags : undefined,
      flow:        'expense',
      day:         globalFilters.day,
    })
      .then(rows => { setData(rows.slice(0, 8)); setLoading(false) })
      .catch(e   => { setError(String(e));       setLoading(false) })
  }, [globalFilters, refreshKey])

  const sorted = [...data].sort((a, b) => b.amount - a.amount)
  const total  = sorted.reduce((sum, d) => sum + d.amount, 0)
  const hasSelection = selectedMerchant !== undefined

  const chartData = sorted.map((d, i) => ({
    name:  d.merchant,
    value: d.amount,
    color: FALLBACK_COLORS[i % FALLBACK_COLORS.length],
  }))

  return (
    <div className="card merchants-card">
      <div className="card-title">{t.topMerchantsTitle}</div>

      {error && (
        <div className="state-box error">
          <span className="icon">⚠</span>
          <span>{error}</span>
        </div>
      )}

      {!error && loading && (
        <div className="state-box">
          <span className="icon">⏳</span>
          <span>{t.loading}</span>
        </div>
      )}

      {!error && !loading && sorted.length === 0 && (
        <div className="state-box">
          <span className="icon">🏪</span>
          <span>{t.topMerchantsEmpty}</span>
        </div>
      )}

      {!error && !loading && sorted.length > 0 && (
        <div className="cat-chart-layout">

          {/* ── Donut ── */}
          <div className="cat-donut-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={chartData}
                  cx="50%"
                  cy="50%"
                  innerRadius={84}
                  outerRadius={116}
                  dataKey="value"
                  paddingAngle={2}
                  cursor="pointer"
                  onClick={(entry) => {
                    const clicked = (entry as any).name as string
                    onMerchantClick(selectedMerchant === clicked ? undefined : clicked)
                  }}
                >
                  {chartData.map((entry, i) => {
                    const isSelected = selectedMerchant === entry.name
                    const dimmed = hasSelection && !isSelected
                    return (
                      <Cell
                        key={i}
                        fill={entry.color}
                        opacity={dimmed ? 0.28 : 0.92}
                        stroke={isSelected ? entry.color : 'transparent'}
                        strokeWidth={isSelected ? 3 : 0}
                      />
                    )
                  })}
                </Pie>
                <Tooltip
                  contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }}
                  labelStyle={{ color: 'var(--text)' }}
                  itemStyle={{ color: 'var(--text)' }}
                  formatter={(value: number) => [formatCurrency(value)]}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="cat-donut-center">
              <span className="cat-donut-label">{t.topMerchantsCenterLabel}</span>
              <span className="cat-donut-total">{formatCurrency(total)}</span>
              {!selectedMerchant && periodTotalExpense != null && periodTotalExpense > 0 && (
                <span className="cat-donut-coverage">
                  {t.merchantCoverage(Math.max(0, Math.min(100, Math.round(total / periodTotalExpense * 100))))}
                </span>
              )}
            </div>
          </div>

          {/* ── Table ── */}
          <div className="cat-table-wrap">
            <table className="cat-table">
              <thead>
                <tr>
                  <th className="cat-th-name">
                    {t.topMerchantsTitle}&nbsp;·&nbsp;{sorted.length}
                  </th>
                  <th className="cat-th-num">{t.catColValue}</th>
                  <th className="cat-th-num">{t.catColWeight}</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((item, i) => {
                  const color = FALLBACK_COLORS[i % FALLBACK_COLORS.length]
                  const weight = total > 0 ? (item.amount / total * 100).toFixed(1) : '0.0'
                  const isSelected = selectedMerchant === item.merchant
                  const isDimmed = hasSelection && !isSelected
                  return (
                    <tr
                      key={item.merchant}
                      className={`cat-row${isSelected ? ' cat-row-selected' : ''}`}
                      style={{ opacity: isDimmed ? 0.38 : 1 }}
                      onClick={() => onMerchantClick(isSelected ? undefined : item.merchant)}
                    >
                      <td className="cat-td-name">
                        <div className="cat-td-name-inner">
                          <span className="cat-swatch" style={{ background: color }} />
                          <span className="cat-td-label">{item.merchant}</span>
                        </div>
                      </td>
                      <td className="cat-td-num">{formatCurrency(item.amount)}</td>
                      <td className="cat-td-num cat-td-weight">{weight}%</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

        </div>
      )}
    </div>
  )
}
