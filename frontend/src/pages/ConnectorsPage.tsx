import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import type { InvestmentPlugin, InvestmentConnection } from '../api/types'
import { getInvestmentPlugins, getConnections, disconnectConnection } from '../api/client'
import { useT } from '../i18n'
import type { Dict } from '../i18n'
import IndexaWizard from '../components/IndexaWizard'

// Map plugin.id → i18n key for localized descriptions (fallback: backend description)
const PLUGIN_DESC_KEYS: Partial<Record<string, keyof Dict>> = {
  'indexa-capital': 'invPluginDescIndexa',
  'fidelity-espp':  'invPluginDescFidelity',
}

export default function ConnectorsPage() {
  const { t } = useT()

  function pluginDesc(plugin: InvestmentPlugin): string {
    const key = PLUGIN_DESC_KEYS[plugin.id]
    return key ? (t[key] as string) : plugin.description
  }
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [plugins, setPlugins] = useState<InvestmentPlugin[]>([])
  const [connections, setConnections] = useState<InvestmentConnection[]>([])
  const [wizardOpen, setWizardOpen] = useState(false)
  const [disconnecting, setDisconnecting] = useState(false)

  const fetchData = useCallback(() => {
    setLoading(true)
    setError(null)
    Promise.all([getInvestmentPlugins(), getConnections()])
      .then(([pluginData, connData]) => {
        setPlugins(pluginData)
        setConnections(connData)
        setLoading(false)
      })
      .catch(err => {
        setError(err instanceof Error ? err.message : String(err))
        setLoading(false)
      })
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  function handleDisconnect(conn: InvestmentConnection) {
    if (!window.confirm(`${t.connectorDisconnect}?`)) return
    setDisconnecting(true)
    disconnectConnection(conn.id)
      .then(() => { setDisconnecting(false); fetchData() })
      .catch(() => { setDisconnecting(false) })
  }

  function renderFidelityEsppCard(plugin: InvestmentPlugin) {
    const conn = connections.find(c => c.plugin_id === 'fidelity-espp' && c.status === 'active')

    if (conn) {
      return (
        <div className="plugin-card connector-card--connected" key={plugin.id}>
          <span className="plugin-card__icon" aria-hidden="true">{plugin.icon}</span>
          <span className="plugin-card__name">{plugin.name}</span>
          <p className="plugin-card__description">{pluginDesc(plugin)}</p>
          <span className="connected-badge">✓ {t.connectorConnected}</span>
          <button
            className="btn-disconnect"
            onClick={() => handleDisconnect(conn)}
            disabled={disconnecting}
          >
            {t.connectorDisconnect}
          </button>
        </div>
      )
    }

    return (
      <div className="plugin-card" key={plugin.id}>
        <span className="plugin-card__icon" aria-hidden="true">{plugin.icon}</span>
        <span className="plugin-card__name">{plugin.name}</span>
        <p className="plugin-card__description">{pluginDesc(plugin)}</p>
        <Link className="btn-primary" to="/investments/fidelity-espp">
          {t.fidelityImportCta}
        </Link>
      </div>
    )
  }

  function renderIndexaCard(plugin: InvestmentPlugin) {
    const conn = connections.find(c => c.plugin_id === 'indexa-capital')
    const connStatus = conn?.status

    if (connStatus === 'active') {
      return (
        <div className="plugin-card connector-card--connected" key={plugin.id}>
          <span className="plugin-card__icon" aria-hidden="true">{plugin.icon}</span>
          <span className="plugin-card__name">{plugin.name}</span>
          <p className="plugin-card__description">{pluginDesc(plugin)}</p>
          <span className="connected-badge">✓ {t.connectorConnected}</span>
          <button
            className="btn-disconnect"
            onClick={() => conn && handleDisconnect(conn)}
            disabled={disconnecting}
          >
            {t.connectorDisconnect}
          </button>
        </div>
      )
    }

    if (connStatus === 'error') {
      return (
        <div className="plugin-card connector-card--error" key={plugin.id}>
          <span className="plugin-card__icon" aria-hidden="true">{plugin.icon}</span>
          <span className="plugin-card__name">{plugin.name}</span>
          <p className="plugin-card__description">{pluginDesc(plugin)}</p>
          <span className="error-badge">⚠ {t.connectorError}</span>
          <button className="btn-primary" onClick={() => setWizardOpen(true)}>
            {t.connectorErrorRetry}
          </button>
        </div>
      )
    }

    return (
      <div className="plugin-card" key={plugin.id}>
        <span className="plugin-card__icon" aria-hidden="true">{plugin.icon}</span>
        <span className="plugin-card__name">{plugin.name}</span>
        <p className="plugin-card__description">{pluginDesc(plugin)}</p>
        <button className="btn-primary" onClick={() => setWizardOpen(true)}>
          {t.investmentsConnect}
        </button>
      </div>
    )
  }

  return (
    <>
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
            {plugins.map(plugin => {
              if (plugin.id === 'indexa-capital') return renderIndexaCard(plugin)
              if (plugin.id === 'fidelity-espp') return renderFidelityEsppCard(plugin)
              return (
                <div className="plugin-card" key={plugin.id}>
                  <span className="plugin-card__icon" aria-hidden="true">{plugin.icon}</span>
                  <span className="plugin-card__name">{plugin.name}</span>
                  <p className="plugin-card__description">{pluginDesc(plugin)}</p>
                  <span className="coming-soon-badge">{t.investmentsComingSoon}</span>
                  <button className="btn-primary" disabled aria-disabled="true">
                    {t.investmentsConnect}
                  </button>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {wizardOpen && (
        <IndexaWizard
          onClose={() => setWizardOpen(false)}
          onConnected={fetchData}
        />
      )}
    </>
  )
}

