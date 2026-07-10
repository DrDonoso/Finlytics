import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import type { MonthSummary } from '../api/types'
import { useT, langLocale } from '../i18n'

interface Props {
  data: MonthSummary[]
  loading: boolean
  error: string | null
  selectedFlow?: 'expense' | 'income'
  onFlowClick: (flow: 'expense' | 'income' | undefined) => void
}

function shortMonth(ym: string, locale: string): string {
  const [year, month] = ym.split('-')
  const date = new Date(Number(year), Number(month) - 1, 1)
  return date.toLocaleDateString(locale, { month: 'short', year: '2-digit' })
}

export default function SpendingOverTime({ data, loading, error, selectedFlow, onFlowClick }: Props) {
  const { t, lang, formatCurrency } = useT()
  const locale = langLocale(lang)
  const chartData = data.map(d => ({ ...d, month: shortMonth(d.month, locale) }))

  function handleBarClick(flow: 'expense' | 'income') {
    onFlowClick(selectedFlow === flow ? undefined : flow)
  }

  return (
    <div className="card overtime-card">
      <div className="card-title">{t.chartOverTime}</div>

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

      {!error && !loading && chartData.length === 0 && (
        <div className="state-box">
          <span className="icon">📊</span>
          <span>{t.noDataPeriod}</span>
        </div>
      )}

      {!error && !loading && chartData.length > 0 && (
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={chartData} margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
            <XAxis
              dataKey="month"
              tick={{ fontSize: 12, fill: 'var(--text-muted)' as string }}
            />
            <YAxis
              tickFormatter={v => `${(v / 1000).toFixed(0)}k€`}
              tick={{ fontSize: 12, fill: 'var(--text-muted)' as string }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }}
              labelStyle={{ color: 'var(--text)' }}
              itemStyle={{ color: 'var(--text)' }}
              formatter={(value: number, name: string) => [
                formatCurrency(value),
                name === 'expense' ? t.legendExpense : t.legendIncome,
              ]}
            />
            <Legend
              formatter={(value: string) => (
                <span style={{ fontSize: 12 }}>
                  {value === 'expense' ? t.legendExpense : t.legendIncome}
                </span>
              )}
            />
            <Bar
              dataKey="expense"
              fill="var(--expense)"
              radius={[4, 4, 0, 0]}
              maxBarSize={60}
              cursor="pointer"
              fillOpacity={selectedFlow === 'income' ? 0.3 : 1}
              onClick={() => handleBarClick('expense')}
            />
            <Bar
              dataKey="income"
              fill="var(--income)"
              radius={[4, 4, 0, 0]}
              maxBarSize={60}
              cursor="pointer"
              fillOpacity={selectedFlow === 'expense' ? 0.3 : 1}
              onClick={() => handleBarClick('income')}
            />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
