import { useMemo } from 'react'
import type { CategorySummary, Category } from '../api/types'
import { useT, categoryLabel } from '../i18n'
import { selectTopMovers, type MoverRow } from '../utils/comparison'

interface Props {
  current: CategorySummary[]
  previous: CategorySummary[]
  categories: Category[]
  loading: boolean
  prevLoading: boolean
  error: string | null
}

function DeltaCell({ row }: { row: MoverRow }) {
  const { t, formatCurrency } = useT()
  if (!row.delta) return <span className="movers-delta movers-delta-dash">—</span>

  if (row.delta.isNew) {
    return <span className="movers-delta movers-delta-neutral">{t.deltaBadgeNew}</span>
  }
  if (row.delta.pct === null) return <span className="movers-delta movers-delta-dash">—</span>

  const isUp = row.delta.abs > 0
  // Expense semantics: categories track spending, so ↑ = more expense = bad
  const cls = isUp ? 'movers-delta-up' : 'movers-delta-down'
  const arrow = isUp ? '↑' : '↓'
  const sign = isUp ? '+' : ''

  return (
    <span className={`movers-delta ${cls}`}>
      {arrow} {sign}{formatCurrency(row.delta.abs)} ({sign}{row.delta.pct.toFixed(1)}%)
    </span>
  )
}

export default function CategoryMovers({
  current, previous, categories, loading, prevLoading, error,
}: Props) {
  const { t, lang, formatCurrency } = useT()

  const dynamicEs = useMemo(
    () => Object.fromEntries(categories.filter(c => c.name_es).map(c => [c.name, c.name_es!])),
    [categories],
  )

  const rows = useMemo(() => selectTopMovers(current, previous, 5), [current, previous])

  const isLoading = loading || prevLoading

  return (
    <div className="card movers-card">
      <div className="card-title">{t.moversTitle}</div>

      {error && (
        <div className="state-box error">
          <span className="icon">⚠</span>
          <span>{error}</span>
        </div>
      )}

      {!error && isLoading && (
        <div className="state-box">
          <span className="icon">⏳</span>
          <span>{t.loading}</span>
        </div>
      )}

      {!error && !isLoading && previous.length === 0 && (
        <div className="state-box">
          <span className="icon">📊</span>
          <span>{t.moversNoPrevious}</span>
        </div>
      )}

      {!error && !isLoading && previous.length > 0 && rows.length === 0 && (
        <div className="state-box">
          <span className="icon">📊</span>
          <span>{t.noDataPeriod}</span>
        </div>
      )}

      {!error && !isLoading && rows.length > 0 && (
        <table className="movers-table">
          <thead>
            <tr>
              <th className="movers-th movers-th-name">{t.moversColCategory}</th>
              <th className="movers-th movers-th-num">{t.moversColCurrent}</th>
              <th className="movers-th movers-th-num">{t.moversColPrevious}</th>
              <th className="movers-th movers-th-change">{t.moversColChange}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(row => (
              <tr key={row.category_id} className="movers-row">
                <td className="movers-td movers-td-name">
                  {categoryLabel(row.category, lang, dynamicEs)}
                </td>
                <td className="movers-td movers-td-num">{formatCurrency(row.current)}</td>
                <td className="movers-td movers-td-num movers-td-prev">
                  {row.previous !== null ? formatCurrency(row.previous) : '—'}
                </td>
                <td className="movers-td movers-td-change">
                  <DeltaCell row={row} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
