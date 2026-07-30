import type { Overview } from '../api/types'
import { useT, categoryLabel } from '../i18n'
import { computeDelta, savingsRate, type DeltaResult } from '../utils/comparison'
import { IconAlert, TrendArrow } from './icons'

interface Props {
  overview: Overview | null
  loading: boolean
  error: string | null
  compact?: boolean
  previousOverview?: Overview | null
  /** All-time unfiltered net shown as a constant anchor (compact header only). */
  constantOverview?: Overview | null
}

interface KpiDef {
  label: string
  value: string
  sub?: string
  cls?: string
  /** undefined = no delta badge; DeltaResult = show badge */
  delta?: DeltaResult
  /** true = ↑ is bad (expense semantics); false/absent = ↑ is good */
  invertDelta?: boolean
}

/** Delta badge for compact KPI items. */
function DeltaBadge({ delta, invert }: { delta?: DeltaResult; invert?: boolean }) {
  const { t } = useT()
  if (!delta) return null

  if (delta.isNew) {
    return <div className="header-kpi-delta header-kpi-delta-neutral">{t.deltaBadgeNew}</div>
  }
  if (delta.pct === null) return null   // prev=0, curr=0 — no meaningful change to show

  const isUp = delta.abs > 0
  const isGood = invert ? !isUp : isUp
  const cls = delta.abs === 0
    ? 'header-kpi-delta-neutral'
    : isGood ? 'header-kpi-delta-good' : 'header-kpi-delta-bad'
  const sign = isUp ? '+' : ''

  return (
    <div className={`header-kpi-delta ${cls}`}>
      <TrendArrow value={delta.abs} /> {sign}{delta.pct.toFixed(1)}%
    </div>
  )
}

export default function KpiCards({ overview, loading, error, compact, previousOverview, constantOverview }: Props) {
  const { t, lang, formatCurrency } = useT()

  function buildKpis(o: Overview, prev: Overview | null | undefined): KpiDef[] {
    const netCls = o.net >= 0 ? 'net-pos' : 'net-neg'
    const rate    = savingsRate(o)
    const prevRate = prev ? savingsRate(prev) : null

    return [
      {
        label: t.kpiTotalExpense,
        value: formatCurrency(o.total_expense),
        cls: 'expense',
        delta: prev ? (computeDelta(o.total_expense, prev.total_expense) ?? undefined) : undefined,
        invertDelta: true,
      },
      {
        label: t.kpiTotalIncome,
        value: formatCurrency(o.total_income),
        cls: 'income',
        delta: prev ? (computeDelta(o.total_income, prev.total_income) ?? undefined) : undefined,
      },
      {
        label: t.kpiNet,
        value: formatCurrency(o.net),
        cls: netCls,
        delta: prev ? (computeDelta(o.net, prev.net) ?? undefined) : undefined,
      },
      {
        label: t.kpiSavingsRate,
        value: rate !== null ? `${rate.toFixed(1)}%` : '—',
        // Only compute savings-rate delta when both periods have valid rates
        delta: (rate !== null && prevRate !== null)
          ? (computeDelta(rate, prevRate) ?? undefined)
          : undefined,
      },
      { label: t.kpiTransactions, value: String(o.num_transactions) },
      {
        label: t.kpiTopCategory,
        value: o.top_category ? categoryLabel(o.top_category.name, lang) : '—',
        sub:   o.top_category ? formatCurrency(o.top_category.amount) : undefined,
      },
    ]
  }

  // ── Compact variant: horizontal inline group for the dashboard header ─────
  if (compact) {
    if (error) {
      return <div className="header-kpis"><span style={{ color: 'var(--expense)', fontSize: 12, display: 'inline-flex', alignItems: 'center', gap: 4 }}><IconAlert size={13} /> KPI</span></div>
    }
    if (loading || !overview) {
      return (
        <div className="header-kpis">
          {constantOverview != null && (
            <>
              <div className="header-kpi-item">
                <div className="header-kpi-label">{t.kpiCurrentNet}</div>
                <div className={`header-kpi-value ${constantOverview.net >= 0 ? 'net-pos' : 'net-neg'}`}>
                  {formatCurrency(constantOverview.net)}
                </div>
              </div>
              <div className="header-kpi-divider" aria-hidden="true" />
            </>
          )}
          {[0, 1, 2, 3, 4, 5].map(i => (
            <div key={i} className="header-kpi-item">
              <div className="skeleton" style={{ width: 60, height: 11, marginBottom: 3 }} />
              <div className="skeleton" style={{ width: 72, height: 16 }} />
            </div>
          ))}
        </div>
      )
    }
    const kpis = buildKpis(overview, previousOverview)
    return (
      <div className="header-kpis">
        {constantOverview != null && (
          <>
            <div className="header-kpi-item">
              <div className="header-kpi-label">{t.kpiCurrentNet}</div>
              <div className={`header-kpi-value ${constantOverview.net >= 0 ? 'net-pos' : 'net-neg'}`}>
                {formatCurrency(constantOverview.net)}
              </div>
            </div>
            <div className="header-kpi-divider" aria-hidden="true" />
          </>
        )}
        {kpis.map(k => (
          <div key={k.label} className="header-kpi-item">
            <div className="header-kpi-label">{k.label}</div>
            <div className={`header-kpi-value ${k.cls ?? ''}`}>{k.value}</div>
            <DeltaBadge delta={k.delta} invert={k.invertDelta} />
            {k.sub && <div className="header-kpi-sub">{k.sub}</div>}
          </div>
        ))}
      </div>
    )
  }

  // ── Full-size variant (kept for potential future reuse) ───────────────────
  if (error) {
    return (
      <div className="kpi-grid">
        <div className="kpi-card">
          <p style={{ color: 'var(--expense)', fontSize: 13 }}>{t.kpiErrorLoading}{error}</p>
        </div>
      </div>
    )
  }

  if (loading || !overview) {
    return (
      <div className="kpi-grid">
        {[0, 1, 2, 3, 4, 5].map(i => (
          <div key={i} className="kpi-card">
            <div className="skeleton" style={{ width: '60%', marginBottom: 12 }} />
            <div className="skeleton" style={{ height: 32 }} />
          </div>
        ))}
      </div>
    )
  }

  const kpis = buildKpis(overview, previousOverview)

  return (
    <div className="kpi-grid">
      {kpis.map(k => (
        <div key={k.label} className="kpi-card">
          <div className="kpi-label">{k.label}</div>
          <div className={`kpi-value ${k.cls ?? ''}`}>{k.value}</div>
          <DeltaBadge delta={k.delta} invert={k.invertDelta} />
          {k.sub && <div className="kpi-sub">{k.sub}</div>}
        </div>
      ))}
    </div>
  )
}
