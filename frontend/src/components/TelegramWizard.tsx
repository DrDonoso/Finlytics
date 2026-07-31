import { useState } from 'react'
import { createTelegramChannel, testTelegramChannel } from '../api/client'
import { useT } from '../i18n'
import { IconClose, IconLock, IconAlert, IconSend, IconCheck, IconChevronRight } from './icons'

type TelegramStep = 1 | 2 | 3
type SaveState = 'idle' | 'saving' | 'success' | 'error'

interface Props {
  onClose: () => void
  onConnected: () => void
}

const CHAT_ID_RE = /^-?\d+$/
const THREAD_ID_RE = /^\d+$/

function stepToActiveDot(step: TelegramStep): number {
  if (step === 1) return 1
  if (step === 2) return 2
  return 4  // step 3 → use 4 so all 3 dots show "done"
}

function dotClass(dotIndex: 1 | 2 | 3, activeDot: number): string {
  if (dotIndex < activeDot) return 'inv-wizard__step-dot inv-wizard__step-dot--done'
  if (dotIndex === activeDot) return 'inv-wizard__step-dot inv-wizard__step-dot--active'
  return 'inv-wizard__step-dot'
}

function sepClass(afterDot: 1 | 2, activeDot: number): string {
  if (afterDot < activeDot) return 'inv-wizard__step-sep inv-wizard__step-sep--done'
  return 'inv-wizard__step-sep'
}

export default function TelegramWizard({ onClose, onConnected }: Props) {
  const { t } = useT()

  const [step, setStep] = useState<TelegramStep>(1)
  const [botToken, setBotToken] = useState('')
  const [chatId, setChatId] = useState('')
  const [chatIdTouched, setChatIdTouched] = useState(false)
  const [threadId, setThreadId] = useState('')

  const [testState, setTestState] = useState<'idle' | 'loading' | 'ok' | 'error'>('idle')
  const [testError, setTestError] = useState<string | null>(null)

  const [saveState, setSaveState] = useState<SaveState>('idle')
  const [saveError, setSaveError] = useState<string | null>(null)

  const activeDot = stepToActiveDot(step)

  const chatIdValid = CHAT_ID_RE.test(chatId.trim())
  const showChatIdError = chatIdTouched && chatId.trim().length > 0 && !chatIdValid

  // Forum topics only exist in groups/supergroups, whose chat IDs are negative.
  const isGroupChat = chatId.trim().startsWith('-')
  const threadIdRaw = threadId.trim()
  const threadIdValid = threadIdRaw.length === 0 || (THREAD_ID_RE.test(threadIdRaw) && Number(threadIdRaw) > 0)
  const showThreadIdError = isGroupChat && threadIdRaw.length > 0 && !threadIdValid
  const messageThreadId = isGroupChat && threadIdValid && threadIdRaw.length > 0 ? Number(threadIdRaw) : null

  const canSubmit = chatIdValid && (!isGroupChat || threadIdValid)

  async function handleTest() {
    if (!canSubmit) return
    setTestState('loading')
    setTestError(null)
    try {
      const result = await testTelegramChannel({
        bot_token: botToken,
        chat_id: chatId.trim(),
        message_thread_id: messageThreadId,
      })
      if (result.ok) {
        setTestState('ok')
      } else {
        setTestError(result.error ?? t.tgWizardErrorSave)
        setTestState('error')
      }
    } catch {
      setTestError(t.tgWizardErrorSave)
      setTestState('error')
    }
  }

  async function handleConnect() {
    setSaveState('saving')
    setSaveError(null)
    try {
      await createTelegramChannel({
        bot_token: botToken,
        chat_id: chatId.trim(),
        message_thread_id: messageThreadId,
      })
      setSaveState('success')
      onConnected()
    } catch (err) {
      const status = (err as { status?: number }).status
      if (status === 503) {
        setSaveError(t.tgWizardErrorNoKey)
      } else if (status === 400 || status === 422) {
        setSaveError(t.tgWizardErrorBadToken)
      } else {
        setSaveError(t.tgWizardErrorSave)
      }
      setSaveState('error')
    }
  }

  function goToStep3() {
    setSaveState('idle')
    setSaveError(null)
    setStep(3)
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="tg-wizard-title">
      <div className="modal inv-wizard">

        {/* Step progress indicator */}
        <div className="inv-wizard__progress" aria-label={t.tgWizardProgressLabel}>
          <span className={dotClass(1, activeDot)} />
          <span className={sepClass(1, activeDot)} />
          <span className={dotClass(2, activeDot)} />
          <span className={sepClass(2, activeDot)} />
          <span className={dotClass(3, activeDot)} />
        </div>

        {/* Modal header */}
        <div className="modal-header">
          <span className="modal-title" id="tg-wizard-title">{t.tgWizardTitle}</span>
          <button className="modal-close" onClick={onClose} aria-label={t.tgWizardClose}><IconClose size={16} /></button>
        </div>

        {/* Modal body */}
        <div className="modal-body">

          {/* Step 1: BotFather instructions + bot token */}
          {step === 1 && (
            <div className="inv-wizard__body">
              <h2 className="inv-wizard__title">{t.tgWizardStep1Title}</h2>
              <div className="inv-wizard__security-note">
                <ol style={{ margin: '0 0 0.5rem 1.25rem', padding: 0, lineHeight: 1.6 }}>
                  <li>{t.tgWizardBotFatherStep1}</li>
                  <li>{t.tgWizardBotFatherStep2}</li>
                  <li>{t.tgWizardBotFatherStep3}</li>
                </ol>
                <a
                  className="inv-wizard__link"
                  href="https://t.me/BotFather"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {t.tgWizardBotFatherLink} <IconChevronRight size={13} />
                </a>
              </div>
              <div className="inv-wizard__token-field">
                <label className="inv-wizard__token-label" htmlFor="tg-bot-token">
                  {t.tgWizardStep2TokenLabel}
                </label>
                <input
                  id="tg-bot-token"
                  type="password"
                  className="inv-wizard__token-input"
                  placeholder={t.tgWizardStep2TokenPlaceholder}
                  value={botToken}
                  onChange={e => setBotToken(e.target.value)}
                  autoComplete="off"
                  spellCheck={false}
                />
              </div>
              <div className="inv-wizard__security-note">
                <span className="inv-wizard__security-note-icon" aria-hidden="true"><IconLock size={15} /></span>
                <span>{t.tgWizardSecurityNote}</span>
              </div>
            </div>
          )}

          {/* Step 2: Chat ID + test */}
          {step === 2 && (
            <div className="inv-wizard__body">
              <h2 className="inv-wizard__title">{t.tgWizardStep3Title}</h2>
              <div className="inv-wizard__token-field">
                <label className="inv-wizard__token-label" htmlFor="tg-chat-id">
                  {t.tgWizardStep3ChatIdLabel}
                </label>
                <input
                  id="tg-chat-id"
                  type="text"
                  className={`inv-wizard__token-input${showChatIdError ? ' inv-wizard__token-input--error' : ''}`}
                  placeholder={t.tgWizardStep3ChatIdPlaceholder}
                  value={chatId}
                  onChange={e => { setChatId(e.target.value); setTestState('idle'); setChatIdTouched(true) }}
                  onBlur={() => setChatIdTouched(true)}
                  autoComplete="off"
                  spellCheck={false}
                  inputMode="numeric"
                />
                <span className="inv-wizard__field-hint">{t.tgWizardStep3ChatIdHint}</span>
                {showChatIdError && (
                  <div className="inv-wizard__error-banner" role="alert" style={{ marginTop: '0.5rem' }}>
                    <span className="inv-wizard__error-banner-icon" aria-hidden="true"><IconAlert size={16} /></span>
                    <span>{t.tgWizardChatIdValidationError}</span>
                  </div>
                )}
              </div>
              {isGroupChat && (
                <div className="inv-wizard__token-field">
                  <label className="inv-wizard__token-label" htmlFor="tg-thread-id">
                    {t.tgWizardThreadIdLabel} <span className="inv-wizard__field-optional">({t.tgWizardThreadIdOptional})</span>
                  </label>
                  <input
                    id="tg-thread-id"
                    type="text"
                    className={`inv-wizard__token-input${showThreadIdError ? ' inv-wizard__token-input--error' : ''}`}
                    placeholder={t.tgWizardThreadIdPlaceholder}
                    value={threadId}
                    onChange={e => { setThreadId(e.target.value); setTestState('idle') }}
                    autoComplete="off"
                    spellCheck={false}
                    inputMode="numeric"
                  />
                  <span className="inv-wizard__field-hint">{t.tgWizardThreadIdHint}</span>
                  {showThreadIdError && (
                    <div className="inv-wizard__error-banner" role="alert" style={{ marginTop: '0.5rem' }}>
                      <span className="inv-wizard__error-banner-icon" aria-hidden="true"><IconAlert size={16} /></span>
                      <span>{t.tgWizardThreadIdValidationError}</span>
                    </div>
                  )}
                </div>
              )}
              <div className="inv-wizard__test-row">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={handleTest}
                  disabled={testState === 'loading' || !botToken.trim() || !chatId.trim() || !canSubmit}
                >
                  {testState === 'loading' ? t.tgWizardStep3Testing : t.tgWizardStep3TestBtn}
                </button>
                {testState === 'ok' && (
                  <span className="inv-wizard__test-ok">{t.tgWizardStep3TestOk}</span>
                )}
              </div>
              {testState === 'error' && testError && (
                <div className="inv-wizard__error-banner" role="alert">
                  <span className="inv-wizard__error-banner-icon" aria-hidden="true"><IconAlert size={16} /></span>
                  <span>{testError}</span>
                </div>
              )}
            </div>
          )}

          {/* Step 3: Confirm + connect */}
          {step === 3 && saveState !== 'success' && (
            <div className="inv-wizard__body">
              <span className="inv-wizard__logo" aria-hidden="true"><IconSend size={44} /></span>
              <h2 className="inv-wizard__title">{t.tgWizardStep4Title}</h2>
              <p className="inv-wizard__desc">{t.tgWizardStep4Desc}</p>
              {saveState === 'error' && saveError && (
                <div className="inv-wizard__error-banner" role="alert">
                  <span className="inv-wizard__error-banner-icon" aria-hidden="true"><IconAlert size={16} /></span>
                  <span>{saveError}</span>
                </div>
              )}
            </div>
          )}

          {step === 3 && saveState === 'success' && (
            <div className="inv-wizard__success">
              <span className="inv-wizard__success-icon" aria-hidden="true"><IconCheck size={40} /></span>
              <h2 className="inv-wizard__success-title">{t.tgWizardStep4Title}</h2>
              <p className="inv-wizard__success-desc">{t.tgWizardStep4Desc}</p>
            </div>
          )}

        </div>

        {/* Modal footer */}
        <div className="modal-footer">
          {step === 1 && (
            <>
              <button className="btn-secondary" onClick={onClose}>{t.tgWizardClose}</button>
              <button
                className="btn-primary"
                onClick={() => setStep(2)}
                disabled={!botToken.trim()}
              >
                {t.tgWizardNext}
              </button>
            </>
          )}
          {step === 2 && (
            <>
              <button className="btn-secondary" onClick={() => setStep(1)}>{t.tgWizardBack}</button>
              <button
                className="btn-primary"
                onClick={goToStep3}
                disabled={!chatId.trim() || !canSubmit}
              >
                {t.tgWizardNext}
              </button>
            </>
          )}
          {step === 3 && saveState !== 'success' && (
            <>
              <button
                className="btn-secondary"
                onClick={() => { setSaveState('idle'); setSaveError(null); setStep(2) }}
                disabled={saveState === 'saving'}
              >
                {t.tgWizardBack}
              </button>
              <button
                className="btn-primary"
                onClick={handleConnect}
                disabled={saveState === 'saving'}
              >
                {saveState === 'saving' ? t.tgWizardStep4Saving : t.tgWizardConnect}
              </button>
            </>
          )}
          {step === 3 && saveState === 'success' && (
            <button className="btn-primary" onClick={onClose}>
              {t.tgWizardDone}
            </button>
          )}
        </div>

      </div>
    </div>
  )
}
