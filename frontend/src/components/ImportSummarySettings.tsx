import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { putImportSummarySettings, retryImportSummary } from '../api/client'
import { errorMessage } from '../api/errors'
import { queryKeys, useImportSummaries, useImportSummarySettings } from '../api/queries'
import type { ImportSummaryJob, ImportSummarySettings as Settings, NotificationChannelOut } from '../api/types'
import { useT } from '../i18n'

interface Props {
  channels: NotificationChannelOut[]
  onConnect: () => void
}

export default function ImportSummarySettings({ channels, onConnect }: Props) {
  const { t } = useT()
  const queryClient = useQueryClient()
  const settings = useImportSummarySettings()
  const jobs = useImportSummaries()
  const [saved, setSaved] = useState(false)
  const retry = useMutation({
    mutationFn: ({ id, uncertain }: { id: number; uncertain: boolean }) => retryImportSummary(id, uncertain),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.importSummaries })
      await queryClient.invalidateQueries({ queryKey: queryKeys.assistantUsage })
    },
  })

  function retryJob(job: ImportSummaryJob) {
    const uncertain = job.status === 'uncertain'
    if (uncertain && !window.confirm(t.importSummaryUncertainConfirm)) return
    retry.mutate({ id: job.id, uncertain })
  }

  return (
    <section id="import-summaries" className="import-summary-settings" aria-labelledby="import-summary-title">
      <h3 id="import-summary-title" className="appearance-label">{t.importSummaryTitle}</h3>
      <p className="appearance-hint">{t.importSummaryDescription}</p>
      <p className="appearance-hint">{t.importSummaryDisclosure}</p>
      {settings.isPending ? <p>{t.loading}</p> : settings.error ? (
        <p role="alert" className="assistant-save-error">{errorMessage(settings.error, t)}</p>
      ) : settings.data && (
        <SummaryForm
          key={`${settings.data.enabled}:${settings.data.channel_id}:${settings.data.language}`}
          settings={settings.data}
          channels={channels}
          onConnect={onConnect}
          onSaved={setSaved}
        />
      )}
      {saved && <p role="status">{t.assistantSettingsSaved}</p>}
      <h3 className="appearance-label">{t.importSummaryRecent}</h3>
      {jobs.isPending && <p>{t.loading}</p>}
      {jobs.error && <p role="alert" className="assistant-save-error">{errorMessage(jobs.error, t)}</p>}
      {retry.error && <p role="alert" className="assistant-save-error">{errorMessage(retry.error, t)}</p>}
      {jobs.data?.length === 0 && <p className="appearance-hint">{t.importSummaryEmpty}</p>}
      {jobs.data && jobs.data.length > 0 && (
        <ul className="import-summary-jobs">
          {jobs.data.map(job => (
            <li key={job.id}>
              <strong>{job.account_name}</strong>
              <span>{job.from_date} - {job.to_date}</span>
              <span>{t.importSummaryStatuses[job.status]}</span>
              {job.error && <p className="appearance-hint">{t.importSummaryErrors[job.error] ?? t.importSummaryError}</p>}
              {['failed', 'blocked', 'uncertain'].includes(job.status) && (
                <button type="button" className="btn-secondary" disabled={retry.isPending || !settings.data?.enabled}
                  onClick={() => retryJob(job)}>
                  {t.importSummaryRetry}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

interface FormProps extends Props {
  settings: Settings
  onSaved: (saved: boolean) => void
}

function SummaryForm({ settings, channels, onConnect, onSaved }: FormProps) {
  const { t, lang } = useT()
  const queryClient = useQueryClient()
  const [enabled, setEnabled] = useState(settings.enabled)
  const [channelId, setChannelId] = useState(settings.channel_id?.toString() ?? '')
  const available = channels.filter(channel => channel.enabled && channel.channel === 'telegram')
  const selected = available.find(channel => String(channel.id) === channelId)
  const save = useMutation({
    mutationFn: putImportSummarySettings,
    onSuccess: async stored => {
      queryClient.setQueryData(queryKeys.importSummarySettings, stored)
      onSaved(true)
      await queryClient.invalidateQueries({ queryKey: queryKeys.importSummaries })
    },
  })

  function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    onSaved(false)
    save.mutate({ enabled, channel_id: selected?.id ?? null, language: lang })
  }

  return (
    <form onSubmit={onSubmit} className="import-summary-form">
      <label htmlFor="import-summary-enabled" className="import-summary-toggle">
        <input id="import-summary-enabled" type="checkbox" checked={enabled}
          disabled={save.isPending || (!settings.ai_available && !enabled)}
          onChange={event => { setEnabled(event.target.checked); onSaved(false) }} />
        {t.importSummaryEnable}
      </label>
      {!settings.ai_available && <p className="appearance-hint">{t.importSummaryNoAI}</p>}
      {available.length === 0 ? (
        <>
          <p className="appearance-hint">{t.importSummaryNoChannels}</p>
          <button className="btn-secondary" type="button" onClick={onConnect}>{t.notifSettingsConnectBtn}</button>
        </>
      ) : (
        <>
          <label htmlFor="import-summary-channel">{t.importSummaryChannel}</label>
          <select id="import-summary-channel" className="form-input" value={selected ? channelId : ''}
            disabled={save.isPending || !enabled}
            onChange={event => { setChannelId(event.target.value); onSaved(false) }}>
            <option value="">{t.importSummarySelectChannel}</option>
            {available.map(channel => <option key={channel.id} value={channel.id}>{channel.label ?? channel.channel}</option>)}
          </select>
        </>
      )}
      <p className="appearance-hint">{t.importSummaryLanguage(settings.language.toUpperCase())}</p>
      {save.error && <p role="alert" className="assistant-save-error">{errorMessage(save.error, t)}</p>}
      <button className="btn-primary" type="submit"
        disabled={save.isPending || (enabled && (!selected || !settings.ai_available))}>
        {t.assistantSettingsSave}
      </button>
    </form>
  )
}
