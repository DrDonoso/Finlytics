import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import type { AccountSummary } from '../api/types'
import { useT } from '../i18n'
import { IconAlert, IconLoading, IconBank } from './icons'

interface Props {
  data: AccountSummary[]
  loading: boolean
  error: string | null
  selectedFlow?: 'expense' | 'income'
  onFlowClick: (flow: 'expense' | 'income' | undefined) => void
}

export default function SpendingByAccount({ data, loading, error, selectedFlow, onFlowClick }: Props) {
  const { t, formatCurrency, formatCompactCurrency } = useT()

  function handleBarClick(flow: 'expense' | 'income') {
    onFlowClick(selectedFlow === flow ? undefined : flow)
  }

  return (
    <div className="card byaccount-card">
      <h2 className="card-title">{t.chartByAccount}</h2>

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

      {!error && !loading && data.length === 0 && (
        <div className="state-box">
          <IconBank size={18} />
          <span>{t.noDataPeriod}</span>
        </div>
      )}

      {!error && !loading && data.length > 0 && (
        <ResponsiveContainer width="100%" height={220} className="chart-value-x">
          <BarChart
            data={data}
            layout="vertical"
            margin={{ top: 4, right: 32, left: 8, bottom: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
            <XAxis
              type="number"
              tickFormatter={v => formatCompactCurrency(Number(v))}
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
              formatter={value => formatCurrency(Number(value))}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar
              dataKey="expense"
              name={t.legendExpense}
              fill="var(--expense-fill)"
              radius={[0, 4, 4, 0]}
              maxBarSize={32}
              cursor="pointer"
              fillOpacity={selectedFlow === 'income' ? 0.3 : 1}
              onClick={() => handleBarClick('expense')}
            />
            <Bar
              dataKey="income"
              name={t.legendIncome}
              fill="var(--income-fill)"
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
