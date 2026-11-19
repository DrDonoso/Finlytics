import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { deleteNotificationChannel, patchNotificationPreference } from '../api/client'
import { errorMessage } from '../api/errors'
import { queryKeys, useNotificationChannels, useNotificationPreferences } from '../api/queries'
import type { NotificationChannelOut, PushTestResult } from '../api/types'
import ImportSummarySettings from '../components/ImportSummarySettings'
import TelegramWizard from '../components/TelegramWizard'
import { IconAlert, IconCheck, IconLoading, IconSend } from '../components/icons'
import { useToast } from '../contexts/ToastContext'
import { useT } from '../i18n'
import { usePush } from '../push/PushContext'

const NO_CHANNELS: NotificationChannelOut[] = []

/** This device's push notifications: the switch, a test, or why they cannot be turned on here. */
function PushSection() {
  const { t } = useT()
  const push = usePush()
  const showToast = useToast()
  const [testing, setTesting] = useState(false)
  if (!push) return null
  const { status, busy } = push

  async function toggle(on: boolean) {
    if (!push) return
    try {
      if (on) {
        if (await push.enable()) showToast(t.pushEnabled)
      } else {
        await push.disable()
      }
    } catch (error) {
      showToast(errorMessage(error, t))
    }
  }

  async function sendTest() {
    if (!push) return
    setTesting(true)
    try {
      const result: PushTestResult = await push.sendTest()
      showToast(result.ok ? t.pushTestSent : t.pushTestErrors[result.error ?? 'rejected'])
    } catch (error) {
      showToast(errorMessage(error, t))
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="card settings-card">
      <h2 className="settings-section-title">{t.pushTitle}</h2>
      <div className="appearance-section">
        <p className="appearance-hint">{t.pushHint}</p>
        {status === 'on' || status === 'off' ? (
          <div className="security-actions">
            <label htmlFor="push-enabled" className="import-summary-toggle">
              <input
                id="push-enabled"
                type="checkbox"
                checked={status === 'on'}
                disabled={busy}
                onChange={event => void toggle(event.target.checked)}
              />
              {t.pushSwitch}
            </label>
            {status === 'on' && (
              <button type="button" className="btn-secondary" disabled={busy || testing} onClick={() => void sendTest()}>
                {testing ? t.loading : t.pushTest}
              </button>
            )}
          </div>
        ) : status === 'pending' ? (
          <p className="appearance-hint">{t.loading}</p>
        ) : (
          <p className="notif-settings-notice">
            <IconAlert size={15} />
            <span>{t.pushStatus[status]}</span>
          </p>
        )}
      </div>
    </div>
  )
}

/** Which alert types push and Telegram send; each choice is saved at once. */
function AlertTypesSection() {
  const { t } = useT()
  const queryClient = useQueryClient()
  const preferences = useNotificationPreferences()
  const save = useMutation({
    mutationFn: patchNotificationPreference,
    onSuccess: saved => queryClient.setQueryData(queryKeys.notificationPreferences, saved),
  })

  return (
    <div className="card settings-card">
      <h2 className="settings-section-title">{t.notifTypesTitle}</h2>
      <div className="appearance-section">
        <p className="appearance-hint">{t.notifTypesHint}</p>
        {preferences.isPending ? (
          <p className="appearance-hint">{t.loading}</p>
        ) : preferences.error ? (
          <p role="alert" className="assistant-save-error">{errorMessage(preferences.error, t)}</p>
        ) : (
          <ul className="notif-types">
            {preferences.data.map(preference => {
              const id = `notif-type-${preference.source}`
              const known = t.notifTypes[preference.source]
              const saving = save.isPending && save.variables?.source === preference.source
              return (
                <li key={preference.source}>
                  <label htmlFor={id} className="import-summary-toggle">
                    <input
                      id={id}
                      type="checkbox"
                      checked={saving && save.variables ? save.variables.enabled : preference.enabled}
                      disabled={save.isPending}
                      aria-describedby={known ? `${id}-hint` : undefined}
                      onChange={event => save.mutate({ source: preference.source, enabled: event.target.checked })}
                    />
                    {known?.label ?? preference.source}
                  </label>
                  {known && <p id={`${id}-hint`} className="appearance-hint">{known.description}</p>}
                </li>
              )
            })}
          </ul>
        )}
        {save.error && <p role="alert" className="assistant-save-error">{errorMessage(save.error, t)}</p>}
      </div>
    </div>
  )
}

/** The Telegram bot that receives the alerts, and the post-import summaries it can send. */
function TelegramSection() {
  const { t } = useT()
  const queryClient = useQueryClient()
  const channelsQuery = useNotificationChannels()
  const channels = channelsQuery.data ?? NO_CHANNELS
  const [wizardOpen, setWizardOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [channelError, setChannelError] = useState<string | null>(null)

  function refreshChannels() {
    void queryClient.invalidateQueries({ queryKey: queryKeys.notificationChannels })
    void queryClient.invalidateQueries({ queryKey: queryKeys.importSummarySettings })
    void queryClient.invalidateQueries({ queryKey: queryKeys.importSummaries })
  }

  function handleDelete(channel: NotificationChannelOut) {
    if (!window.confirm(t.notifSettingsDeleteConfirm)) return
    setDeleting(true)
    setChannelError(null)
    deleteNotificationChannel(channel.id)
      .then(() => { setDeleting(false); refreshChannels() })
      .catch(err => { setDeleting(false); setChannelError(errorMessage(err, t)) })
  }

  function renderTelegramCard() {
    const channel = channels.find(c => c.channel === 'telegram')
    if (channel) {
      return (
        <div className="plugin-card connector-card--connected">
          <IconSend size={26} className="plugin-card__icon" />
          <span className="plugin-card__name">{t.notifSettingsTelegramLabel}</span>
          <p className="plugin-card__description">{channel.label ?? t.notifSettingsEnabled}</p>
          <span className="connected-badge"><IconCheck size={13} /> {t.notifSettingsEnabled}</span>
          <button type="button" className="btn-primary" onClick={() => setWizardOpen(true)}>
            {t.notifSettingsEditBtn}
          </button>
          <button
            type="button"
            className="btn-disconnect"
            onClick={() => handleDelete(channel)}
            disabled={deleting}
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
        <button type="button" className="btn-primary" onClick={() => setWizardOpen(true)}>
          {t.notifSettingsConnectBtn}
        </button>
      </div>
    )
  }

  return (
    <div className="card settings-card">
      <h2 className="settings-section-title">{t.notifSettingsTelegramLabel}</h2>
      {channelError && <p role="alert" className="assistant-save-error">{channelError}</p>}
      {channelsQuery.isPending ? (
        <div className="state-box">
          <IconLoading size={18} />
          <span>{t.loading}</span>
        </div>
      ) : channelsQuery.error ? (
        <div className="state-box error">
          <IconAlert size={18} />
          <span>{errorMessage(channelsQuery.error, t)}</span>
        </div>
      ) : (
        <>
          <div className="plugin-catalog">{renderTelegramCard()}</div>
          <ImportSummarySettings channels={channels} onConnect={() => setWizardOpen(true)} />
        </>
      )}
      {wizardOpen && (
        <TelegramWizard
          onClose={() => setWizardOpen(false)}
          onConnected={() => { setWizardOpen(false); refreshChannels() }}
        />
      )}
    </div>
  )
}

export default function NotificationsSettingsPage() {
  return (
    <>
      <PushSection />
      <AlertTypesSection />
      <TelegramSection />
    </>
  )
}
