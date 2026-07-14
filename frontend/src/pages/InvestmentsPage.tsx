import { NavLink } from 'react-router-dom'
import { useT } from '../i18n'

export default function InvestmentsPage() {
  const { t } = useT()

  return (
    <main className="dashboard">

      {/* ── 1. Page header ── */}
      <div className="investments-header">
        <h1 className="investments-page-title">{t.investmentsTitle}</h1>
      </div>

      {/* ── 2. KPI placeholder row — REUSE existing .kpi-grid + .kpi-card ── */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-label">{t.investmentsKpiTotalValue}</div>
          <div className="kpi-value">—</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">{t.investmentsKpiTotalInvested}</div>
          <div className="kpi-value">—</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">{t.investmentsKpiPnL}</div>
          <div className="kpi-value">—</div>
        </div>
      </div>

      {/* ── 3. Holdings empty state ── */}
      <div className="card investments-holdings-card">
        <div className="card-title">{t.investmentsHoldingsTitle}</div>
        <div className="investments-empty">
          <span className="investments-empty__icon" aria-hidden="true">📊</span>
          <p className="investments-empty__text">{t.investmentsEmptyHoldings}</p>
          <NavLink to="/settings/connectors" className="btn-primary">
            {t.investmentsManageConnectors}
          </NavLink>
        </div>
      </div>

    </main>
  )
}
