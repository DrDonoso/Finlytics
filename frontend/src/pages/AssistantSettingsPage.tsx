/**
 * Assistant settings: custom instructions, token usage and spend guards.
 *
 * The core system prompt is deliberately NOT editable here. It carries the
 * rules that stop the model inventing figures about the user's money — get
 * numbers from the tools, never do compound interest yourself, treat statement
 * text as data, never reveal account numbers. A box that can delete those is a
 * box that eventually will, and the failure is invisible because the output
 * still reads like a confident answer. What the user writes here is appended as
 * preferences instead.
 */
import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { putAssistantSettings } from '../api/client'
import { queryKeys, useAssistantSettings, useAssistantUsage } from '../api/queries'
import type { AssistantSettingsPayload } from '../api/types'
import { useT } from '../i18n'
import { IconSparkles } from '../components/icons'

/** Blank means "no override"; the backend reads null as "use the env default". */
function toNullableInt(raw: string): number | null {
  const trimmed = raw.trim()
  if (trimmed === '') return null
  const n = Number(trimmed)
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : null
}

function formatInt(value: number, lang: string): string {
  return new Intl.NumberFormat(lang === 'es' ? 'es-ES' : 'en-GB').format(value)
}

export default function AssistantSettingsPage() {
  const { t, lang } = useT()
  const queryClient = useQueryClient()

  const settingsQuery = useAssistantSettings()
  const usageQuery = useAssistantUsage()

  const [instructions, setInstructions] = useState('')
  const [rateMessages, setRateMessages] = useState('')
  const [rateWindow, setRateWindow] = useState('')
  const [budget, setBudget] = useState('')
  const [saved, setSaved] = useState(false)

  // Seeded from the server once it answers. A blank input means "inherit",
  // which is why the effective values are shown as placeholders instead of
  // being written into the fields — pre-filling them would silently turn an
  // inherited value into a saved override on the next save.
  useEffect(() => {
    const data = settingsQuery.data
    if (!data) return
    setInstructions(data.custom_instructions ?? '')
    setRateMessages(data.rate_limit_messages?.toString() ?? '')
    setRateWindow(data.rate_limit_window_seconds?.toString() ?? '')
    setBudget(data.monthly_token_budget?.toString() ?? '')
  }, [settingsQuery.data])

  const save = useMutation({
    mutationFn: (body: AssistantSettingsPayload) => putAssistantSettings(body),
    onSuccess: async () => {
      setSaved(true)
      window.setTimeout(() => setSaved(false), 2500)
      await queryClient.invalidateQueries({ queryKey: queryKeys.assistantSettings })
      await queryClient.invalidateQueries({ queryKey: queryKeys.assistantUsage })
    },
  })

  function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    save.mutate({
      custom_instructions: instructions.trim() === '' ? null : instructions.trim(),
      rate_limit_messages: toNullableInt(rateMessages),
      rate_limit_window_seconds: toNullableInt(rateWindow),
      monthly_token_budget: toNullableInt(budget),
    })
  }

  const settings = settingsQuery.data
  const usage = usageQuery.data
  const maxChars = settings?.max_custom_instructions_chars ?? 2000
  const overLimit = instructions.length > maxChars

  return (
    <div className="card settings-card">
      <h2 className="settings-section-title">
        <IconSparkles size={16} /> {t.assistantSettingsTitle}
      </h2>

      {/* ── Usage ─────────────────────────────────────────────── */}
      <div className="appearance-section">
        <div>
          <p className="appearance-label">{t.assistantUsageTitle}</p>
          <p className="appearance-hint">{t.assistantUsageHint}</p>
        </div>

        {usageQuery.isPending && <p className="appearance-hint">{t.loading}</p>}

        {usage && !usage.usage_available && (
          <p className="assistant-usage-unknown">{t.assistantUsageUnavailable}</p>
        )}

        {usage && usage.usage_available && (
          <>
            <div className="assistant-usage-grid">
              <div className="assistant-usage-stat">
                <span className="assistant-usage-value">
                  {formatInt(usage.this_month.total_tokens, lang)}
                </span>
                <span className="assistant-usage-label">{t.assistantUsageThisMonth}</span>
              </div>
              <div className="assistant-usage-stat">
                <span className="assistant-usage-value">
                  {formatInt(usage.this_month.messages, lang)}
                </span>
                <span className="assistant-usage-label">{t.assistantUsageMessages}</span>
              </div>
              <div className="assistant-usage-stat">
                <span className="assistant-usage-value">
                  {formatInt(usage.all_time.total_tokens, lang)}
                </span>
                <span className="assistant-usage-label">{t.assistantUsageAllTime}</span>
              </div>
            </div>

            {usage.monthly_token_budget !== null && (
              <div className="assistant-budget-bar-wrap">
                <div
                  className="assistant-budget-bar"
                  role="progressbar"
                  aria-valuemin={0}
                  aria-valuemax={usage.monthly_token_budget}
                  aria-valuenow={usage.this_month.total_tokens}
                  aria-label={t.assistantBudgetLabel}
                >
                  <div
                    className="assistant-budget-fill"
                    style={{
                      width: `${Math.min(
                        100,
                        (usage.this_month.total_tokens / usage.monthly_token_budget) * 100,
                      )}%`,
                    }}
                  />
                </div>
                <p className="appearance-hint">
                  {t.assistantBudgetUsed(
                    formatInt(usage.this_month.total_tokens, lang),
                    formatInt(usage.monthly_token_budget, lang),
                  )}
                </p>
              </div>
            )}
          </>
        )}
      </div>

      <form onSubmit={onSubmit}>
        {/* ── Custom instructions ─────────────────────────────── */}
        <div className="appearance-section">
          <div>
            <p className="appearance-label">{t.assistantInstructionsLabel}</p>
            <p className="appearance-hint">{t.assistantInstructionsHint}</p>
          </div>
          <textarea
            className="assistant-settings-textarea"
            value={instructions}
            onChange={e => setInstructions(e.target.value)}
            placeholder={t.assistantInstructionsPlaceholder}
            rows={6}
            aria-label={t.assistantInstructionsLabel}
          />
          <p className={`assistant-char-count${overLimit ? ' over' : ''}`}>
            {instructions.length} / {maxChars}
          </p>
          <p className="appearance-hint assistant-core-note">
            {t.assistantInstructionsCoreNote}
          </p>
        </div>

        {/* ── Limits ──────────────────────────────────────────── */}
        <div className="appearance-section">
          <div>
            <p className="appearance-label">{t.assistantLimitsLabel}</p>
            <p className="appearance-hint">{t.assistantLimitsHint}</p>
          </div>

          <div className="assistant-limits-grid">
            <label className="assistant-field">
              <span className="assistant-field-label">{t.assistantLimitMessages}</span>
              <input
                type="number"
                min={1}
                className="assistant-settings-input"
                value={rateMessages}
                onChange={e => setRateMessages(e.target.value)}
                placeholder={settings ? String(settings.effective_rate_limit_messages) : ''}
              />
            </label>

            <label className="assistant-field">
              <span className="assistant-field-label">{t.assistantLimitWindow}</span>
              <input
                type="number"
                min={60}
                className="assistant-settings-input"
                value={rateWindow}
                onChange={e => setRateWindow(e.target.value)}
                placeholder={
                  settings ? String(settings.effective_rate_limit_window_seconds) : ''
                }
              />
            </label>

            <label className="assistant-field">
              <span className="assistant-field-label">{t.assistantBudgetField}</span>
              <input
                type="number"
                min={1000}
                step={1000}
                className="assistant-settings-input"
                value={budget}
                onChange={e => setBudget(e.target.value)}
                placeholder={t.assistantBudgetNone}
              />
            </label>
          </div>

          <p className="appearance-hint">{t.assistantLimitsInheritHint}</p>
          <p className="appearance-hint assistant-budget-note">{t.assistantBudgetNote}</p>
        </div>

        <div className="assistant-settings-actions">
          <button
            type="submit"
            className="btn-primary"
            disabled={save.isPending || overLimit}
          >
            {save.isPending ? t.loading : t.assistantSettingsSave}
          </button>
          {saved && <span className="assistant-saved">{t.assistantSettingsSaved}</span>}
          {save.isError && (
            <span className="assistant-save-error" role="alert">
              {save.error instanceof Error ? save.error.message : t.assistantErrorGeneric}
            </span>
          )}
        </div>
      </form>
    </div>
  )
}
