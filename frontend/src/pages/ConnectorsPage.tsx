import { useState, useEffect } from 'react'
import type { InvestmentPlugin } from '../api/types'
import { getInvestmentPlugins } from '../api/client'
import { useT } from '../i18n'

export default function ConnectorsPage() {
  const { t } = useT()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [plugins, setPlugins] = useState<InvestmentPlugin[]>([])

  useEffect(() => {
    setLoading(true)
    setError(null)
    getInvestmentPlugins()
      .then(data => { setPlugins(data); setLoading(false) })
      .catch(err => { setError(err instanceof Error ? err.message : String(err)); setLoading(false) })
  }, [])

  return (
    <div className="card settings-card">
      <h2 className="settings-section-title">{t.investmentsCatalogTitle}</h2>
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
      ) : (
        <div className="plugin-catalog">
          {plugins.map(plugin => (
            <div className="plugin-card" key={plugin.id}>
              <span className="plugin-card__icon" aria-hidden="true">{plugin.icon}</span>
              <span className="plugin-card__name">{plugin.name}</span>
              <p className="plugin-card__description">{plugin.description}</p>
              <span className="coming-soon-badge">{t.investmentsComingSoon}</span>
              <button
                className="btn-primary"
                disabled
                aria-disabled="true"
              >
                {t.investmentsConnect}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
