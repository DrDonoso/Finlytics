import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import type { AccountSummary } from '../api/types'
import { useT } from '../i18n'

interface Props {
  data: AccountSummary[]
  loading: boolean
  error: string | null
  selectedFlow?: 'expense' | 'income'
  onFlowClick: (flow: 'expense' | 'income' | undefined) => void
}

export default function SpendingByAccount({ data, loading, error, selectedFlow, onFlowClick }: Props) {
  const { t, formatCurrency } = useT()

  function handleBarClick(flow: 'expense' | 'income') {
    onFlowClick(selectedFlow === flow ? undefined : flow)
  }

  return (
    <div className="card byaccount-card">
      <div className="card-title">{t.chartByAccount}</div>

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

      {!error && !loading && data.length === 0 && (
        <div className="state-box">
          <span className="icon">🏦</span>
          <span>{t.noDataPeriod}</span>
        </div>
      )}

      {!error && !loading && data.length > 0 && (
        <ResponsiveContainer width="100%" height={220}>
          <BarChart
            data={data}
            layout="vertical"
            margin={{ top: 4, right: 32, left: 8, bottom: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
            <XAxis
              type="number"
              tickFormatter={v => `${(v / 1000).toFixed(0)}k€`}
              tick={{ fontSize: 12, fill: 'var(--text-muted)' as string }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              type="category"
              dataKey="account"
              width={130}
              tick={{ fontSize: 13, fill: 'var(--text-muted)' as string }}
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
              radius={[0, 4, 4, 0]}
              maxBarSize={32}
              cursor="pointer"
              fillOpacity={selectedFlow === 'income' ? 0.3 : 1}
              onClick={() => handleBarClick('expense')}
            />
            <Bar
              dataKey="income"
              fill="var(--income)"
              radius={[0, 4, 4, 0]}
              maxBarSize={32}
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
