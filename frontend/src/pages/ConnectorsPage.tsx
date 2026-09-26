import { useState } from 'react'
import { Link } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import type { InvestmentPlugin, InvestmentConnection, NotificationChannelOut } from '../api/types'
import { disconnectConnection, deleteNotificationChannel } from '../api/client'
import { queryKeys, useConnections, useInvestmentPlugins, useNotificationChannels } from '../api/queries'
import { useT } from '../i18n'
import type { Dict } from '../i18n'
import IndexaWizard from '../components/IndexaWizard'
import TelegramWizard from '../components/TelegramWizard'
import { getPluginLogo, pluginInitial } from '../investments/registry'
import { IconCheck, IconAlert, IconSend, IconLoading } from '../components/icons'

// Map plugin.id → i18n key for localized descriptions (fallback: backend description)
const PLUGIN_DESC_KEYS: Partial<Record<string, keyof Dict>> = {
  'indexa-capital': 'invPluginDescIndexa',
  'fidelity-espp':  'invPluginDescFidelity',
}

const NO_PLUGINS: InvestmentPlugin[] = []
const NO_CONNECTIONS: InvestmentConnection[] = []
const NO_CHANNELS: NotificationChannelOut[] = []

function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

export default function ConnectorsPage() {
  const { t } = useT()
  const queryClient = useQueryClient()

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
  const pluginsQuery = useInvestmentPlugins()
  const connectionsQuery = useConnections()
  const plugins = pluginsQuery.data ?? NO_PLUGINS
  const connections = connectionsQuery.data ?? NO_CONNECTIONS
  const loading = pluginsQuery.isPending || connectionsQuery.isPending
  const investmentError = pluginsQuery.error ?? connectionsQuery.error
  const error = investmentError ? messageOf(investmentError) : null
  const [wizardOpen, setWizardOpen] = useState(false)
  const [disconnecting, setDisconnecting] = useState(false)

  // A connection change also invalidates every figure derived from it.
  function refreshConnections() {
    void queryClient.invalidateQueries({ queryKey: queryKeys.connections })
    void queryClient.invalidateQueries({ queryKey: ['investments'] })
  }

  function handleDisconnect(conn: InvestmentConnection) {
    if (!window.confirm(`${t.connectorDisconnect}?`)) return
    setDisconnecting(true)
    disconnectConnection(conn.id)
      .then(() => { setDisconnecting(false); refreshConnections() })
      .catch(() => { setDisconnecting(false) })
  }

  // ── Notification connectors state ────────────────────────────────────────
  const channelsQuery = useNotificationChannels()
  const channels = channelsQuery.data ?? NO_CHANNELS
  const notifLoading = channelsQuery.isPending
  const notifError = channelsQuery.error ? messageOf(channelsQuery.error) : null
  const [telegramWizardOpen, setTelegramWizardOpen] = useState(false)
  const [deletingChannel, setDeletingChannel] = useState(false)

  function refreshChannels() {
    void queryClient.invalidateQueries({ queryKey: queryKeys.notificationChannels })
  }

  function handleDeleteChannel(ch: NotificationChannelOut) {
    if (!window.confirm(t.notifSettingsDeleteConfirm)) return
    setDeletingChannel(true)
    deleteNotificationChannel(ch.id)
      .then(() => { setDeletingChannel(false); refreshChannels() })
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
          <span className="connected-badge"><IconCheck size={13} /> {t.connectorConnected}</span>
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
          <span className="connected-badge"><IconCheck size={13} /> {t.connectorConnected}</span>
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
          <span className="error-badge"><IconAlert size={13} /> {t.connectorError}</span>
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
          <IconSend size={26} className="plugin-card__icon" />
          <span className="plugin-card__name">{t.notifSettingsTelegramLabel}</span>
          <p className="plugin-card__description">
            {ch.label ? `${ch.label}` : t.notifSettingsEnabled}
          </p>
          <span className="connected-badge"><IconCheck size={13} /> {t.notifSettingsEnabled}</span>
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
        <IconSend size={26} className="plugin-card__icon" />
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
      {/* ── Investment connectors ─────────────────────────────── */}
      <div className="card settings-card">
        <h2 className="settings-section-title">{t.connectorsInvestmentsTitle}</h2>
        {loading ? (
          <div className="state-box">
            <IconLoading size={18} />
            <span>{t.loading}</span>
          </div>
        ) : error ? (
          <div className="state-box error">
            <IconAlert size={18} />
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

      {/* ── Notification connectors ───────────────────────────── */}
      <div className="card settings-card">
        <h2 className="settings-section-title">{t.connectorsNotificationsTitle}</h2>
        {notifLoading ? (
          <div className="state-box">
            <IconLoading size={18} />
            <span>{t.loading}</span>
          </div>
        ) : notifError ? (
          <div className="state-box error">
            <IconAlert size={18} />
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
          onConnected={refreshConnections}
        />
      )}

      {telegramWizardOpen && (
        <TelegramWizard
          onClose={() => setTelegramWizardOpen(false)}
          onConnected={() => { setTelegramWizardOpen(false); refreshChannels() }}
        />
      )}
    </>
  )
}
