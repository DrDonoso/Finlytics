import type { Overview } from '../api/types'
import { useT, categoryLabel } from '../i18n'

interface Props {
  overview: Overview | null
  loading: boolean
  error: string | null
  compact?: boolean
}

interface KpiDef {
  label: string
  value: string
  sub?: string
  cls?: string
}

export default function KpiCards({ overview, loading, error, compact }: Props) {
  const { t, lang, formatCurrency } = useT()

  function buildKpis(o: Overview): KpiDef[] {
    const netCls = o.net >= 0 ? 'net-pos' : 'net-neg'
    return [
      { label: t.kpiTotalExpense, value: formatCurrency(o.total_expense), cls: 'expense' },
      { label: t.kpiTotalIncome,  value: formatCurrency(o.total_income),  cls: 'income'  },
      { label: t.kpiNet,          value: formatCurrency(o.net),           cls: netCls    },
      { label: t.kpiTransactions, value: String(o.num_transactions)                      },
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
      return <div className="header-kpis"><span style={{ color: 'var(--expense)', fontSize: 12 }}>⚠ KPI</span></div>
    }
    if (loading || !overview) {
      return (
        <div className="header-kpis">
          {[0, 1, 2, 3, 4].map(i => (
            <div key={i} className="header-kpi-item">
              <div className="skeleton" style={{ width: 60, height: 11, marginBottom: 3 }} />
              <div className="skeleton" style={{ width: 72, height: 16 }} />
            </div>
          ))}
        </div>
      )
    }
    const kpis = buildKpis(overview)
    return (
      <div className="header-kpis">
        {kpis.map(k => (
          <div key={k.label} className="header-kpi-item">
            <div className="header-kpi-label">{k.label}</div>
            <div className={`header-kpi-value ${k.cls ?? ''}`}>{k.value}</div>
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
        {[0, 1, 2, 3, 4].map(i => (
          <div key={i} className="kpi-card">
            <div className="skeleton" style={{ width: '60%', marginBottom: 12 }} />
            <div className="skeleton" style={{ height: 32 }} />
          </div>
        ))}
      </div>
    )
  }

  const kpis = buildKpis(overview)

  return (
    <div className="kpi-grid">
      {kpis.map(k => (
        <div key={k.label} className="kpi-card">
          <div className="kpi-label">{k.label}</div>
          <div className={`kpi-value ${k.cls ?? ''}`}>{k.value}</div>
          {k.sub && <div className="kpi-sub">{k.sub}</div>}
        </div>
      ))}
    </div>
  )
}
