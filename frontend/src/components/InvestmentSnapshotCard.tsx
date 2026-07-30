import { useState, useEffect } from 'react'
import { Link } from 'react-router'
import { getCombinedOverview } from '../api/client'
import { errorMessage } from '../api/errors'
import type { CombinedOverview } from '../api/types'
import { getPluginLogo, pluginInitial } from '../investments/registry'
import { useT } from '../i18n'
import { IconAlert, IconLoading, IconChevronRight } from './icons'

function fmtEur(value: number | null): string {
  if (value === null || value === undefined) return '—'
  return value.toLocaleString('es-ES', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

export default function InvestmentSnapshotCard() {
  const { t } = useT()
  const [loading, setLoading] = useState(true)
  // Se guarda el error en crudo y se traduce al pintar, para que el mensaje
  // acompañe al cambio de idioma en vez de quedarse congelado.
  const [error, setError]   = useState<unknown>(null)
  const [data, setData]     = useState<CombinedOverview | null>(null)

  useEffect(() => {
    getCombinedOverview()
      .then(d  => { setData(d);      setLoading(false) })
      .catch(e => { setError(e);     setLoading(false) })
  }, [])

  return (
    <div className="card inv-snapshot-card">
      <div className="inv-snapshot-header">
        <h3 className="inv-snapshot-title">{t.invSnapshotTitle}</h3>
        <Link to="/investments" className="inv-snapshot-link">{t.invSnapshotGoTo} <IconChevronRight size={14} /></Link>
      </div>

      {loading ? (
        <div className="state-box">
          <IconLoading size={18} />
          <span>{t.loading}</span>
        </div>
      ) : error ? (
        <div className="state-box error">
          <IconAlert size={18} />
          <span>{errorMessage(error, t)}</span>
        </div>
      ) : data && data.providers.length > 0 ? (
        <div className="inv-snapshot-body">
          <div className="inv-snapshot-total">
            <span className="inv-snapshot-total-label">{t.invCombinedTotalValue}</span>
            <span className="inv-snapshot-total-value">{fmtEur(data.total_value_eur)}</span>
          </div>
          <div className="inv-snapshot-providers">
            {data.providers.map(p => (
              <Link key={p.id} to={p.route} className="inv-snapshot-provider">
                {getPluginLogo(p.id) ? (
                  <img src={getPluginLogo(p.id) ?? ''} alt={p.name} className="plugin-logo inv-snapshot-provider-logo" />
                ) : (
                  <span className="plugin-logo-fallback inv-snapshot-provider-logo" aria-label={p.name}>{pluginInitial(p.name)}</span>
                )}
                <span className="inv-snapshot-provider-name">{p.name}</span>
                <span className="inv-snapshot-provider-value">{fmtEur(p.value_eur)}</span>
              </Link>
            ))}
          </div>
        </div>
      ) : (
        <div className="state-box">
          <span>{t.invSnapshotNoConnections}</span>
          <Link to="/investments" className="btn-secondary inv-snapshot-cta">
            {t.invSnapshotGoTo} <IconChevronRight size={14} />
          </Link>
        </div>
      )}
    </div>
  )
}
