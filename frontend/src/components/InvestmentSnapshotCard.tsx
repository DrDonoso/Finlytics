import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getCombinedOverview } from '../api/client'
import type { CombinedOverview } from '../api/types'
import { useT } from '../i18n'

function fmtEur(value: number | null): string {
  if (value === null || value === undefined) return '—'
  return value.toLocaleString('es-ES', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
  })
}

export default function InvestmentSnapshotCard() {
  const { t } = useT()
  const [loading, setLoading] = useState(true)
  const [error, setError]   = useState<string | null>(null)
  const [data, setData]     = useState<CombinedOverview | null>(null)

  useEffect(() => {
    getCombinedOverview()
      .then(d  => { setData(d);          setLoading(false) })
      .catch(e => { setError(String(e)); setLoading(false) })
  }, [])

  return (
    <div className="card inv-snapshot-card">
      <div className="inv-snapshot-header">
        <h3 className="inv-snapshot-title">{t.invSnapshotTitle}</h3>
        <Link to="/investments" className="inv-snapshot-link">{t.invSnapshotGoTo}</Link>
      </div>

      {loading ? (
        <div className="state-box">
          <span className="icon">⏳</span>
          <span>{t.loading}</span>
        </div>
      ) : error ? (
        <div className="state-box error">
          <span className="icon">⚠️</span>
          <span>{error}</span>
        </div>
      ) : data && data.providers.length > 0 ? (
        <div className="inv-snapshot-body">
          <div className="inv-snapshot-total">
            <span className="inv-snapshot-total-label">{t.invCombinedTotalValue}</span>
            <span className="inv-snapshot-total-value">{fmtEur(data.total_value_eur)}</span>
          </div>
          <div className="inv-snapshot-providers">
            {data.providers.map(p => (
              <div key={p.id} className="inv-snapshot-provider">
                <span className="inv-snapshot-provider-icon" aria-hidden="true">{p.icon}</span>
                <span className="inv-snapshot-provider-name">{p.name}</span>
                <span className="inv-snapshot-provider-value">{fmtEur(p.value_eur)}</span>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="state-box">
          <span>{t.invSnapshotNoConnections}</span>
          <Link to="/investments" className="btn-secondary inv-snapshot-cta">
            {t.invSnapshotGoTo}
          </Link>
        </div>
      )}
    </div>
  )
}
