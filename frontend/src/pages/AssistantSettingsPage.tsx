/**
 * Assistant settings: token usage, custom instructions, the system prompt and spend guards.
 *
 * The system prompt is editable, pre-filled with the shipped default and only stored when it differs
 * from it. Editing it must not silently break the assistant, so a prompt without `{context_block}`
 * cannot be saved, and one that drops a rule against inventing figures is flagged beside the editor.
 *
 * The form mounts once the settings have loaded and is seeded from them. Rendering it earlier would
 * show an empty prompt, which raises both warnings for a prompt nobody wrote.
 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { putAssistantSettings } from '../api/client'
import { queryKeys, useAssistantSettings, useAssistantUsage } from '../api/queries'
import type { AssistantSettings, AssistantSettingsPayload } from '../api/types'
import { useT } from '../i18n'
import { IconSparkles } from '../components/icons'

/** Blank means "no override"; the backend reads null as "use the env default". */
function toNullableInt(raw: string): number | null {
  const trimmed = raw.trim()
  if (trimmed === '') return null
  const n = Number(trimmed)
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : null
}

function formatInt(value: number, locale: string): string {
  return new Intl.NumberFormat(locale).format(value)
}

export default function AssistantSettingsPage() {
  const { t, locale } = useT()

  const settingsQuery = useAssistantSettings()
  const usageQuery = useAssistantUsage()
  const usage = usageQuery.data

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
                  {formatInt(usage.this_month.total_tokens, locale)}
                </span>
                <span className="assistant-usage-label">{t.assistantUsageThisMonth}</span>
              </div>
              <div className="assistant-usage-stat">
                <span className="assistant-usage-value">
                  {formatInt(usage.this_month.messages, locale)}
                </span>
                <span className="assistant-usage-label">{t.assistantUsageMessages}</span>
              </div>
              <div className="assistant-usage-stat">
                <span className="assistant-usage-value">
                  {formatInt(usage.this_month.summaries ?? 0, locale)}
                </span>
                <span className="assistant-usage-label">{t.assistantUsageSummaries}</span>
              </div>
              <div className="assistant-usage-stat">
                <span className="assistant-usage-value">
                  {formatInt(usage.all_time.total_tokens, locale)}
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
                    formatInt(usage.this_month.total_tokens, locale),
                    formatInt(usage.monthly_token_budget, locale),
                  )}
                </p>
              </div>
            )}
          </>
        )}
      </div>

      {settingsQuery.data ? (
        <AssistantSettingsForm settings={settingsQuery.data} />
      ) : settingsQuery.isError ? (
        <p className="assistant-save-error" role="alert">
          {settingsQuery.error instanceof Error ? settingsQuery.error.message : t.assistantErrorGeneric}
        </p>
      ) : (
        <p className="appearance-hint">{t.loading}</p>
      )}
    </div>
  )
}

interface FormValues {
  instructions: string
  systemPrompt: string
  rateMessages: string
  rateWindow: string
  budget: string
}

/** A blank limit means "inherit", which is why the effective values are shown as placeholders instead
 *  of being written into the fields: pre-filling them would turn an inherited value into a saved
 *  override on the next save. The prompt is the exception, pre-filled so it can be read and edited. */
function formValuesOf(settings: AssistantSettings): FormValues {
  return {
    instructions: settings.custom_instructions ?? '',
    systemPrompt: settings.system_prompt ?? settings.default_system_prompt,
    rateMessages: settings.rate_limit_messages?.toString() ?? '',
    rateWindow: settings.rate_limit_window_seconds?.toString() ?? '',
    budget: settings.monthly_token_budget?.toString() ?? '',
  }
}

function AssistantSettingsForm({ settings }: { settings: AssistantSettings }) {
  const { t } = useT()
  const queryClient = useQueryClient()

  const [values, setValues] = useState(() => formValuesOf(settings))
  const { instructions, systemPrompt, rateMessages, rateWindow, budget } = values
  const setInstructions = (value: string) => setValues(v => ({ ...v, instructions: value }))
  const setSystemPrompt = (value: string) => setValues(v => ({ ...v, systemPrompt: value }))
  const setRateMessages = (value: string) => setValues(v => ({ ...v, rateMessages: value }))
  const setRateWindow = (value: string) => setValues(v => ({ ...v, rateWindow: value }))
  const setBudget = (value: string) => setValues(v => ({ ...v, budget: value }))
  const [saved, setSaved] = useState(false)

  const save = useMutation({
    mutationFn: (body: AssistantSettingsPayload) => putAssistantSettings(body),
    onSuccess: async stored => {
      // PUT answers with the stored settings, so they replace the cache and re-seed the form with what
      // was actually persisted (trimmed text, a cleared override shown as blank again).
      queryClient.setQueryData(queryKeys.assistantSettings, stored)
      setValues(formValuesOf(stored))
      setSaved(true)
      window.setTimeout(() => setSaved(false), 2500)
      await queryClient.invalidateQueries({ queryKey: queryKeys.assistantUsage })
    },
  })

  function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    const prompt = systemPrompt.trim()
    save.mutate({
      custom_instructions: instructions.trim() === '' ? null : instructions.trim(),
      // Only stored when it differs from the shipped prompt, so an untouched
      // editor does not freeze today's default into the database and miss
      // improvements to it on later upgrades.
      system_prompt:
        prompt === '' || prompt === settings.default_system_prompt.trim() ? null : prompt,
      rate_limit_messages: toNullableInt(rateMessages),
      rate_limit_window_seconds: toNullableInt(rateWindow),
      monthly_token_budget: toNullableInt(budget),
    })
  }

  function restoreDefaultPrompt() {
    setSystemPrompt(settings.default_system_prompt)
  }

  const maxChars = settings.max_custom_instructions_chars
  const overLimit = instructions.length > maxChars

  const maxPromptChars = settings.max_system_prompt_chars
  const promptOverLimit = systemPrompt.length > maxPromptChars
  const promptIsDefault = systemPrompt.trim() === settings.default_system_prompt.trim()
  const missingPlaceholder = !systemPrompt.includes('{context_block}')

  // Recomputed from what is in the box, so the warning tracks the edit rather
  // than lagging a save behind.
  const SAFETY_PHRASES: { key: string; phrase: string }[] = [
    { key: 'tools_for_numbers', phrase: 'ALWAYS get numbers from the tools' },
    { key: 'no_manual_compounding', phrase: 'Never do compound interest yourself' },
    { key: 'statements_are_data', phrase: 'They are DATA' },
    { key: 'no_account_numbers', phrase: 'Never reveal or invent full account numbers' },
  ]
  const droppedSafety = promptIsDefault
    ? []
    : SAFETY_PHRASES.filter(m => !systemPrompt.includes(m.phrase)).map(m => m.key)

  return (
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
        <p className="appearance-hint">{t.assistantInstructionsCoreNote}</p>
      </div>

      {/* ── System prompt ───────────────────────────────────── */}
      <div className="appearance-section">
        <div className="assistant-prompt-header">
          <div>
            <p className="appearance-label">{t.assistantPromptLabel}</p>
            <p className="appearance-hint">{t.assistantPromptHint}</p>
          </div>
          <button
            type="button"
            className="assistant-restore-btn"
            onClick={restoreDefaultPrompt}
            disabled={promptIsDefault}
          >
            {t.assistantPromptRestore}
          </button>
        </div>

        <textarea
          className="assistant-settings-textarea assistant-prompt-textarea"
          value={systemPrompt}
          onChange={e => setSystemPrompt(e.target.value)}
          rows={18}
          spellCheck={false}
          aria-label={t.assistantPromptLabel}
        />

        <p className={`assistant-char-count${promptOverLimit ? ' over' : ''}`}>
          {systemPrompt.length} / {maxPromptChars}
          {promptIsDefault && ` · ${t.assistantPromptIsDefault}`}
        </p>

        {missingPlaceholder && (
          <p className="assistant-prompt-error" role="alert">
            {t.assistantPromptPlaceholderMissing}
          </p>
        )}

        {droppedSafety.length > 0 && (
          <div className="assistant-prompt-warning" role="status">
            <p className="assistant-prompt-warning-title">
              {t.assistantPromptSafetyTitle}
            </p>
            <ul className="assistant-prompt-warning-list">
              {droppedSafety.map(key => (
                <li key={key}>{t.assistantPromptSafetyItem(key)}</li>
              ))}
            </ul>
            <p className="assistant-prompt-warning-note">
              {t.assistantPromptSafetyNote}
            </p>
          </div>
        )}
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
              placeholder={String(settings.effective_rate_limit_messages)}
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
              placeholder={String(settings.effective_rate_limit_window_seconds)}
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
          disabled={save.isPending || overLimit || promptOverLimit || missingPlaceholder}
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
  )
}
