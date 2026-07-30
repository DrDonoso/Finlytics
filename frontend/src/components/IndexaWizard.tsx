import { useState } from 'react'
import { useNavigate } from 'react-router'
import type { ValidatedAccount, InvestmentConnection } from '../api/types'
import { validateIndexaToken, connectPlugin } from '../api/client'
import { useT } from '../i18n'
import { IconClose, IconTrendingUp, IconKey, IconLock, IconAlert, IconCheck } from './icons'

type WizardStep = 1 | 2 | '3-loading' | '3-error' | '3-accounts' | 4

interface Props {
  onClose: () => void
  onConnected: () => void
}

function stepToActiveDot(step: WizardStep): number {
  if (step === 1) return 1
  if (step === 2 || step === '3-error') return 2
  if (step === '3-loading' || step === '3-accounts') return 3
  return 5   // step 4: all done (use 5 so all dots get "done")
}

function dotClass(dotIndex: 1 | 2 | 3 | 4, activeDot: number): string {
  if (dotIndex < activeDot) return 'inv-wizard__step-dot inv-wizard__step-dot--done'
  if (dotIndex === activeDot) return 'inv-wizard__step-dot inv-wizard__step-dot--active'
  return 'inv-wizard__step-dot'
}

function sepClass(afterDot: 1 | 2 | 3, activeDot: number): string {
  if (afterDot < activeDot) return 'inv-wizard__step-sep inv-wizard__step-sep--done'
  return 'inv-wizard__step-sep'
}

export default function IndexaWizard({ onClose, onConnected }: Props) {
  const { t } = useT()
  const navigate = useNavigate()

  const [step, setStep] = useState<WizardStep>(1)
  const [token, setToken] = useState('')
  const [accounts, setAccounts] = useState<ValidatedAccount[]>([])
  const [selectedAccounts, setSelectedAccounts] = useState<string[]>([])
  const [connectedAccounts, setConnectedAccounts] = useState<InvestmentConnection[]>([])
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const activeDot = stepToActiveDot(step)

  function toggleAccount(accountNumber: string) {
    setSelectedAccounts(prev =>
      prev.includes(accountNumber)
        ? prev.filter(n => n !== accountNumber)
        : [...prev, accountNumber],
    )
  }

  async function handleValidate() {
    setStep('3-loading')
    setErrorMsg(null)
    try {
      const resp = await validateIndexaToken(token)
      setAccounts(resp.accounts)
      setSelectedAccounts(resp.accounts.map(a => a.account_number))
      setStep('3-accounts')
    } catch (err) {
      const status = (err as { status?: number }).status
      setErrorMsg(status === 503 ? t.wizardErrorNetwork : t.wizardErrorInvalidToken)
      setStep('3-error')
    }
  }

  async function handleConnect() {
    try {
      const connections = await connectPlugin(token, selectedAccounts)
      setConnectedAccounts(connections)
      onConnected()
      setStep(4)
    } catch {
      setErrorMsg(t.wizardErrorNetwork)
      setStep('3-error')
    }
  }

  function handleViewInvestments() {
    onClose()
    navigate('/investments')
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="wizard-title">
      <div className="modal inv-wizard">

        {/* Step progress indicator */}
        <div className="inv-wizard__progress" aria-label={t.wizardProgressLabel}>
          <span className={dotClass(1, activeDot)} />
          <span className={sepClass(1, activeDot)} />
          <span className={dotClass(2, activeDot)} />
          <span className={sepClass(2, activeDot)} />
          <span className={dotClass(3, activeDot)} />
          <span className={sepClass(3, activeDot)} />
          <span className={dotClass(4, activeDot)} />
        </div>

        {/* Modal header */}
        <div className="modal-header">
          <span className="modal-title" id="wizard-title">{t.wizardTitle}</span>
          <button className="modal-close" onClick={onClose} aria-label={t.wizardClose}><IconClose size={16} /></button>
        </div>

        {/* Modal body */}
        <div className="modal-body">

          {step === 1 && (
            <div className="inv-wizard__body">
              <span className="inv-wizard__logo" aria-hidden="true"><IconTrendingUp size={44} /></span>
              <h2 className="inv-wizard__title">{t.wizardStep1Title}</h2>
              <p className="inv-wizard__desc">{t.wizardStep1Desc}</p>
              <a
                className="inv-wizard__link"
                href="https://indexacapital.com/u/user#settings-apps"
                target="_blank"
                rel="noopener noreferrer"
              >
                <IconKey size={15} /> {t.wizardStep1Link}
              </a>
              <div className="inv-wizard__security-note">
                <span className="inv-wizard__security-note-icon" aria-hidden="true"><IconLock size={15} /></span>
                <span>{t.wizardSecurityNote}</span>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="inv-wizard__body">
              <h2 className="inv-wizard__title">{t.wizardStep2Title}</h2>
              <div className="inv-wizard__token-field">
                <label className="inv-wizard__token-label" htmlFor="indexa-token">
                  {t.wizardTokenLabel}
                </label>
                <input
                  id="indexa-token"
                  type="password"
                  className="inv-wizard__token-input"
                  placeholder={t.wizardTokenPlaceholder}
                  value={token}
                  onChange={e => setToken(e.target.value)}
                  autoComplete="off"
                  spellCheck={false}
                />
              </div>
              <div className="inv-wizard__security-note">
                <span className="inv-wizard__security-note-icon" aria-hidden="true"><IconLock size={15} /></span>
                <span>{t.wizardSecurityNote}</span>
              </div>
            </div>
          )}

          {step === '3-loading' && (
            <div className="spinner-wrap">
              <div className="spinner" role="status" aria-label={t.wizardStep3Validating} />
              <p className="spinner-label">{t.wizardStep3Validating}</p>
            </div>
          )}

          {step === '3-error' && (
            <div className="inv-wizard__body">
              <div className="inv-wizard__error-banner" role="alert">
                <span className="inv-wizard__error-banner-icon" aria-hidden="true"><IconAlert size={16} /></span>
                <span>{errorMsg ?? t.wizardErrorInvalidToken}</span>
              </div>
              <div className="inv-wizard__token-field">
                <label className="inv-wizard__token-label" htmlFor="indexa-token-retry">
                  {t.wizardTokenLabel}
                </label>
                <input
                  id="indexa-token-retry"
                  type="password"
                  className="inv-wizard__token-input"
                  placeholder={t.wizardTokenPlaceholder}
                  value={token}
                  onChange={e => setToken(e.target.value)}
                  autoComplete="off"
                />
              </div>
            </div>
          )}

          {step === '3-accounts' && (
            <div className="inv-wizard__body">
              <h2 className="inv-wizard__title">{t.wizardStep3Title}</h2>
              <p className="inv-wizard__desc">{t.wizardStep3Desc}</p>
              <div className="inv-wizard__account-list">
                {accounts.map(acc => (
                  <label
                    key={acc.account_number}
                    className={`inv-wizard__account-item${selectedAccounts.includes(acc.account_number) ? ' inv-wizard__account-item--checked' : ''}`}
                  >
                    <input
                      type="checkbox"
                      className="inv-wizard__account-checkbox"
                      checked={selectedAccounts.includes(acc.account_number)}
                      onChange={() => toggleAccount(acc.account_number)}
                    />
                    <div className="inv-wizard__account-info">
                      <span className="inv-wizard__account-label">{acc.account_number_masked}</span>
                      <span className="inv-wizard__account-type">{acc.type}</span>
                    </div>
                  </label>
                ))}
              </div>
            </div>
          )}

          {step === 4 && (
            <div className="inv-wizard__success">
              <span className="inv-wizard__success-icon" aria-hidden="true"><IconCheck size={40} /></span>
              <h2 className="inv-wizard__success-title">{t.wizardStep4Title}</h2>
              <p className="inv-wizard__success-desc">{t.wizardStep4Desc}</p>
              <div className="inv-wizard__success-accounts">
                {connectedAccounts.map(acc => (
                  <div className="inv-wizard__success-account" key={acc.id}>
                    <em className="inv-wizard__success-account-check" aria-hidden="true"><IconCheck size={14} /></em>
                    {acc.account_label_masked}
                  </div>
                ))}
              </div>
            </div>
          )}

        </div>

        {/* Modal footer */}
        <div className="modal-footer">
          {step === 1 && (
            <>
              <button className="btn-secondary" onClick={onClose}>{t.wizardClose}</button>
              <button className="btn-primary" onClick={() => setStep(2)}>{t.wizardNext}</button>
            </>
          )}
          {step === 2 && (
            <>
              <button className="btn-secondary" onClick={() => setStep(1)}>{t.wizardBack}</button>
              <button className="btn-primary" onClick={handleValidate} disabled={!token.trim()}>
                {t.wizardValidate}
              </button>
            </>
          )}
          {step === '3-error' && (
            <>
              <button className="btn-secondary" onClick={onClose}>{t.wizardClose}</button>
              <button className="btn-primary" onClick={handleValidate} disabled={!token.trim()}>
                {t.wizardRetry}
              </button>
            </>
          )}
          {step === '3-accounts' && (
            <>
              <button className="btn-secondary" onClick={() => setStep(2)}>{t.wizardBack}</button>
              <button className="btn-primary" onClick={handleConnect} disabled={selectedAccounts.length === 0}>
                {t.wizardConnect}
              </button>
            </>
          )}
          {step === 4 && (
            <button className="btn-primary" onClick={handleViewInvestments}>
              {t.wizardViewInvestments}
            </button>
          )}
        </div>

      </div>
    </div>
  )
}
