import { AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import type { MortgageBalancePoint, MortgageScheduleYear } from '../api/types'
import { formatEur } from '../api/client'
import { useT } from '../i18n'

const AXIS_TICK = { fontSize: 11 }
const TOOLTIP_STYLE = {
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 8,
}

function thousands(value: number): string {
  return `${Math.round(value / 1000)}k`
}

/**
 * Outstanding-balance curve.
 *
 * Real instalments and projected ones are drawn as two separate areas so the
 * estimated tail is visually distinct from settled history.
 */
export function MortgageBalanceChart({ points }: { points: MortgageBalancePoint[] }) {
  const { t } = useT()
  if (points.length === 0) {
    return <div className="state-box"><span>{t.noDataPeriod}</span></div>
  }

  // Duplicate the boundary point in both series so the two areas join seamlessly.
  const firstProjected = points.findIndex(p => p.projected)
  const data = points.map((p, i) => ({
    date: p.date,
    real: !p.projected || (firstProjected > 0 && i === firstProjected) ? p.balance : null,
    projected: p.projected ? p.balance : null,
  }))

  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={data}>
        <defs>
          <linearGradient id="mortgageBalanceFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--primary)" stopOpacity={0.35} />
            <stop offset="100%" stopColor="var(--primary)" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="date" tick={AXIS_TICK} minTickGap={48} />
        <YAxis tick={AXIS_TICK} width={64} tickFormatter={thousands} />
        <Tooltip contentStyle={TOOLTIP_STYLE} formatter={value => formatEur(Number(value))} />
        <Area
          type="monotone"
          dataKey="real"
          name={t.mortgageSeriesBalance}
          stroke="var(--primary)"
          strokeWidth={2}
          fill="url(#mortgageBalanceFill)"
          connectNulls
        />
        <Area
          type="monotone"
          dataKey="projected"
          name={t.mortgageSeriesProjected}
          stroke="var(--primary)"
          strokeWidth={2}
          strokeDasharray="5 4"
          fill="url(#mortgageBalanceFill)"
          fillOpacity={0.4}
          connectNulls
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}

/** Stacked principal-vs-interest split per year — shows how the mix flips over time. */
export function MortgageCompositionChart({ years }: { years: MortgageScheduleYear[] }) {
  const { t } = useT()
  if (years.length === 0) {
    return <div className="state-box"><span>{t.noDataPeriod}</span></div>
  }

  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={years}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="year" tick={AXIS_TICK} minTickGap={16} />
        <YAxis tick={AXIS_TICK} width={64} tickFormatter={thousands} />
        <Tooltip contentStyle={TOOLTIP_STYLE} formatter={value => formatEur(Number(value))} />
        <Legend />
        <Bar dataKey="interest" name={t.mortgageSeriesInterest} stackId="a" fill="#f59e0b" />
        <Bar dataKey="principal" name={t.mortgageSeriesPrincipal} stackId="a" fill="var(--primary)" />
      </BarChart>
    </ResponsiveContainer>
  )
}
