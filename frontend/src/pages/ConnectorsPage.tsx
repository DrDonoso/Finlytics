import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router'
import type { InvestmentPlugin, InvestmentConnection, NotificationChannelOut } from '../api/types'
import { getInvestmentPlugins, getConnections, disconnectConnection, getNotificationChannels, deleteNotificationChannel } from '../api/client'
import { useT } from '../i18n'
import type { Dict } from '../i18n'
import IndexaWizard from '../components/IndexaWizard'
import TelegramWizard from '../components/TelegramWizard'
import { getPluginLogo, pluginInitial } from '../investments/registry'

// Map plugin.id → i18n key for localized descriptions (fallback: backend description)
const PLUGIN_DESC_KEYS: Partial<Record<string, keyof Dict>> = {
  'indexa-capital': 'invPluginDescIndexa',
  'fidelity-espp':  'invPluginDescFidelity',
}

export default function ConnectorsPage() {
  const { t } = useT()

  function renderPluginIcon(plugin: InvestmentPlugin) {
    const logo = getPluginLogo(plugin.id)
    if (logo) return <img src={logo} alt={plugin.name} className="plugin-card__icon plugin-logo" />
    return <span className="plugin-card__icon plugin-logo-fallback" aria-label={plugin.name}>{pluginInitial(plugin.name)}</span>
  }

  function pluginDesc(plugin: InvestmentPlugin): string {
    const key = PLUGIN_DESC_KEYS[plugin.id]
    return key ? (t[key] as string) : plugin.description
  }

  // ── Investment connectors state ──────────────────────────────────────────
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

  // ── Notification connectors state ────────────────────────────────────────
  const [notifLoading, setNotifLoading] = useState(true)
  const [notifError, setNotifError] = useState<string | null>(null)
  const [channels, setChannels] = useState<NotificationChannelOut[]>([])
  const [telegramWizardOpen, setTelegramWizardOpen] = useState(false)
  const [deletingChannel, setDeletingChannel] = useState(false)

  const fetchChannels = useCallback(() => {
    setNotifLoading(true)
    setNotifError(null)
    getNotificationChannels()
      .then(data => { setChannels(data); setNotifLoading(false) })
      .catch(err => { setNotifError(err instanceof Error ? err.message : String(err)); setNotifLoading(false) })
  }, [])

  useEffect(() => { fetchChannels() }, [fetchChannels])

  function handleDeleteChannel(ch: NotificationChannelOut) {
    if (!window.confirm(t.notifSettingsDeleteConfirm)) return
    setDeletingChannel(true)
    deleteNotificationChannel(ch.id)
      .then(() => { setDeletingChannel(false); fetchChannels() })
      .catch(() => setDeletingChannel(false))
  }

  // ── Investment card renderers ─────────────────────────────────────────────
  function renderFidelityEsppCard(plugin: InvestmentPlugin) {
    const conn = connections.find(c => c.plugin_id === 'fidelity-espp' && c.status === 'active')

    if (conn) {
      return (
        <div className="plugin-card connector-card--connected" key={plugin.id}>
          {renderPluginIcon(plugin)}
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
        {renderPluginIcon(plugin)}
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
          {renderPluginIcon(plugin)}
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
          {renderPluginIcon(plugin)}
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
        {renderPluginIcon(plugin)}
        <span className="plugin-card__name">{plugin.name}</span>
        <p className="plugin-card__description">{pluginDesc(plugin)}</p>
        <button className="btn-primary" onClick={() => setWizardOpen(true)}>
          {t.investmentsConnect}
        </button>
      </div>
    )
  }

  // ── Telegram card renderer ────────────────────────────────────────────────
  function renderTelegramCard() {
    const ch = channels.find(c => c.channel === 'telegram')

    if (ch) {
      return (
        <div className="plugin-card connector-card--connected">
          <span className="plugin-card__icon" aria-hidden="true">✈️</span>
          <span className="plugin-card__name">{t.notifSettingsTelegramLabel}</span>
          <p className="plugin-card__description">
            {ch.label ? `${ch.label}` : t.notifSettingsEnabled}
          </p>
          <span className="connected-badge">✓ {t.notifSettingsEnabled}</span>
          <button
            type="button"
            className="btn-primary"
            onClick={() => setTelegramWizardOpen(true)}
          >
            {t.notifSettingsEditBtn}
          </button>
          <button
            type="button"
            className="btn-disconnect"
            onClick={() => handleDeleteChannel(ch)}
            disabled={deletingChannel}
          >
            {t.notifSettingsDeleteBtn}
          </button>
        </div>
      )
    }

    return (
      <div className="plugin-card">
        <span className="plugin-card__icon" aria-hidden="true">✈️</span>
        <span className="plugin-card__name">{t.notifSettingsTelegramLabel}</span>
        <p className="plugin-card__description">{t.notifSettingsNoChannels}</p>
        <button
          type="button"
          className="btn-primary"
          onClick={() => setTelegramWizardOpen(true)}
        >
          {t.notifSettingsConnectBtn}
        </button>
      </div>
    )
  }

  return (
    <>
      {/* ── Inversiones ───────────────────────────────────────── */}
      <div className="card settings-card">
        <h2 className="settings-section-title">{t.connectorsInvestmentsTitle}</h2>
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
                  {renderPluginIcon(plugin)}
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

      {/* ── Notificaciones ────────────────────────────────────── */}
      <div className="card settings-card">
        <h2 className="settings-section-title">{t.connectorsNotificationsTitle}</h2>
        {notifLoading ? (
          <div className="state-box">
            <span className="icon">⏳</span>
            <span>{t.loading}</span>
          </div>
        ) : notifError ? (
          <div className="state-box error">
            <span className="icon">⚠️</span>
            <span>{notifError}</span>
          </div>
        ) : (
          <div className="plugin-catalog">
            {renderTelegramCard()}
          </div>
        )}
      </div>

      {wizardOpen && (
        <IndexaWizard
          onClose={() => setWizardOpen(false)}
          onConnected={fetchData}
        />
      )}

      {telegramWizardOpen && (
        <TelegramWizard
          onClose={() => setTelegramWizardOpen(false)}
          onConnected={() => { setTelegramWizardOpen(false); fetchChannels() }}
        />
      )}
    </>
  )
}
