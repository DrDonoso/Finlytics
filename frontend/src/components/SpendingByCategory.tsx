import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
} from 'recharts'
import { useMemo } from 'react'
import type { CategorySummary, Category } from '../api/types'
import { useT, categoryLabel } from '../i18n'

const FALLBACK_COLORS = [
  '#2563eb', '#ef4444', '#22c55e', '#f59e0b', '#8b5cf6',
  '#ec4899', '#06b6d4', '#84cc16', '#f97316', '#64748b',
]

interface Props {
  data: CategorySummary[]
  categories: Category[]
  loading: boolean
  error: string | null
  selectedCategoryId?: number
  onCategoryClick: (id: number | undefined) => void
}

export default function SpendingByCategory({ data, categories, loading, error, selectedCategoryId, onCategoryClick }: Props) {
  const { t, lang, formatCurrency } = useT()

  const dynamicEs = useMemo(
    () => Object.fromEntries(categories.filter(c => c.name_es).map(c => [c.name, c.name_es!])),
    [categories],
  )

  const sorted = [...data].sort((a, b) => b.amount - a.amount)
  const total = sorted.reduce((sum, d) => sum + d.amount, 0)
  const hasSelection = selectedCategoryId !== undefined

  const catColorMap: Record<number, string> = {}
  for (const cat of categories) catColorMap[cat.id] = cat.color

  function getColor(categoryId: number, index: number): string {
    return catColorMap[categoryId] || FALLBACK_COLORS[index % FALLBACK_COLORS.length]
  }

  const chartData = sorted.map((d, i) => ({
    name: d.category,
    value: d.amount,
    category_id: d.category_id,
    color: getColor(d.category_id, i),
  }))

  return (
    <div className="card cat-card">
      <div className="card-title">{t.chartByCategory}</div>

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
          <span className="icon">🍩</span>
          <span>{t.noDataPeriod}</span>
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
                    const clickedId = (entry as any).category_id as number
                    onCategoryClick(selectedCategoryId === clickedId ? undefined : clickedId)
                  }}
                >
                  {chartData.map((entry, i) => {
                    const isSelected = selectedCategoryId === entry.category_id
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
                  formatter={(value, name) => [
                    formatCurrency(Number(value)),
                    categoryLabel(String(name), lang, dynamicEs),
                  ]}
                />
              </PieChart>
            </ResponsiveContainer>
            {/* Center overlay */}
            <div className="cat-donut-center">
              <span className="cat-donut-label">{t.catCenterLabel}</span>
              <span className="cat-donut-total">{formatCurrency(total)}</span>
            </div>
          </div>

          {/* ── Table ── */}
          <div className="cat-table-wrap">
            <table className="cat-table">
              <thead>
                <tr>
                  <th className="cat-th-name">
                    {t.catColCategories}&nbsp;·&nbsp;{sorted.length}
                  </th>
                  <th className="cat-th-num">{t.catColValue}</th>
                  <th className="cat-th-num">{t.catColWeight}</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((item, i) => {
                  const color = getColor(item.category_id, i)
                  const weight = total > 0 ? (item.amount / total * 100).toFixed(1) : '0.0'
                  const isSelected = selectedCategoryId === item.category_id
                  const isDimmed = hasSelection && !isSelected
                  return (
                    <tr
                      key={item.category_id}
                      className={`cat-row${isSelected ? ' cat-row-selected' : ''}`}
                      style={{ opacity: isDimmed ? 0.38 : 1 }}
                      onClick={() => onCategoryClick(isSelected ? undefined : item.category_id)}
                    >
                      <td className="cat-td-name">
                        <div className="cat-td-name-inner">
                          <span className="cat-swatch" style={{ background: color }} />
                          <span className="cat-td-label">{categoryLabel(item.category, lang, dynamicEs)}</span>
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
