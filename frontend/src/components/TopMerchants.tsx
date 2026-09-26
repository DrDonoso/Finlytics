import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
} from 'recharts'
import { useMemo } from 'react'
import type { GlobalFilters } from '../api/types'
import { useByMerchant } from '../api/queries'
import { errorMessage } from '../api/errors'
import { useT } from '../i18n'
import { IconAlert, IconLoading, IconStore } from './icons'

const FALLBACK_COLORS = [
  '#2563eb', '#ef4444', '#22c55e', '#f59e0b', '#8b5cf6',
  '#ec4899', '#06b6d4', '#84cc16', '#f97316', '#64748b',
]

interface Props {
  globalFilters: GlobalFilters
  selectedMerchant?: string
  onMerchantClick: (m: string | undefined) => void
  periodTotalExpense?: number | null
}

export default function TopMerchants({ globalFilters, selectedMerchant, onMerchantClick, periodTotalExpense }: Props) {
  const { t, formatCurrency } = useT()

  // byMerchant: pass category_id + day (+ from/to/account_id/tags/flow). Do NOT pass merchant.
  const params = useMemo(() => ({
    from:        globalFilters.from  || undefined,
    to:          globalFilters.to    || undefined,
    account_id:  globalFilters.account_id,
    category_id: globalFilters.category_id,
    tags:        globalFilters.tags.length > 0 ? globalFilters.tags : undefined,
    flow:        'expense' as const,
    day:         globalFilters.day,
  }), [globalFilters])

  const query = useByMerchant(params)
  const loading = query.isPending
  const error = query.error ? errorMessage(query.error, t) : null
  const data = useMemo(() => (query.data ?? []).slice(0, 8), [query.data])

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
          <IconAlert size={18} />
          <span>{error}</span>
        </div>
      )}

      {!error && loading && (
        <div className="state-box">
          <IconLoading size={18} />
          <span>{t.loading}</span>
        </div>
      )}

      {!error && !loading && sorted.length === 0 && (
        <div className="state-box">
          <IconStore size={18} />
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
                  formatter={(value) => [formatCurrency(Number(value))]}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="cat-donut-center">
              <span className="cat-donut-label">{t.topMerchantsCenterLabel}</span>
              <span className="cat-donut-total private">{formatCurrency(total)}</span>
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
                      <td className="cat-td-num private">{formatCurrency(item.amount)}</td>
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
