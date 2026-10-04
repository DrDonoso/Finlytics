import { useState } from 'react'
import { changePassword, logoutOtherSessions } from '../api/client'
import { useAuth } from '../contexts/AuthContext'
import { useT } from '../i18n'
import { MIN_PASSWORD_LENGTH, passwordTooLong } from '../utils/password'

type Outcome = { ok: boolean; message: string } | null

function OutcomeMessage({ outcome }: { outcome: Outcome }) {
  if (!outcome) return null
  return outcome.ok
    ? <output className="security-ok">{outcome.message}</output>
    : <span className="security-error" role="alert">{outcome.message}</span>
}

export default function SecurityPage() {
  const { t } = useT()
  const { username } = useAuth()

  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [passwordPending, setPasswordPending] = useState(false)
  const [passwordOutcome, setPasswordOutcome] = useState<Outcome>(null)

  const [sessionsPending, setSessionsPending] = useState(false)
  const [sessionsOutcome, setSessionsOutcome] = useState<Outcome>(null)

  function describeFailure(err: unknown): string {
    const { status, retryAfter } = err as { status?: number; retryAfter?: number }
    if (status === 400) return t.securityErrorWrongPassword
    if (status === 429) return t.authErrorTooManyAttempts(Math.max(1, Math.ceil((retryAfter ?? 60) / 60)))
    return t.authErrorUnexpected
  }

  async function handlePasswordSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (next.length < MIN_PASSWORD_LENGTH) {
      setPasswordOutcome({ ok: false, message: t.authErrorPasswordTooShort })
      return
    }
    if (passwordTooLong(next)) {
      setPasswordOutcome({ ok: false, message: t.authErrorPasswordTooLong })
      return
    }
    if (next !== confirm) {
      setPasswordOutcome({ ok: false, message: t.authErrorPasswordMismatch })
      return
    }
    setPasswordOutcome(null)
    setPasswordPending(true)
    try {
      await changePassword(current, next)
      setCurrent('')
      setNext('')
      setConfirm('')
      setPasswordOutcome({ ok: true, message: t.securityPasswordChanged })
    } catch (err) {
      setPasswordOutcome({ ok: false, message: describeFailure(err) })
    } finally {
      setPasswordPending(false)
    }
  }

  async function handleLogoutOthers() {
    setSessionsOutcome(null)
    setSessionsPending(true)
    try {
      await logoutOtherSessions()
      setSessionsOutcome({ ok: true, message: t.securityLogoutOthersDone })
    } catch {
      setSessionsOutcome({ ok: false, message: t.authErrorUnexpected })
    } finally {
      setSessionsPending(false)
    }
  }

  return (
    <div className="card settings-card">
      <h2 className="settings-section-title">{t.securityPageTitle}</h2>

      <form className="appearance-section" onSubmit={handlePasswordSubmit}>
        <div>
          <p className="appearance-label">{t.securityPasswordTitle}</p>
          <p className="appearance-hint">{t.securityPasswordHint}</p>
        </div>
        {/* Lets a password manager tell which saved credential to update. */}
        <input type="text" autoComplete="username" value={username ?? ''} readOnly hidden />
        <div className="security-fields">
          <label className="security-field">
            <span className="security-field-label">{t.securityCurrentPassword}</span>
            <input
              type="password"
              className="security-input"
              value={current}
              onChange={e => setCurrent(e.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          <label className="security-field">
            <span className="security-field-label">{t.securityNewPassword}</span>
            <input
              type="password"
              className="security-input"
              value={next}
              onChange={e => setNext(e.target.value)}
              autoComplete="new-password"
              required
            />
          </label>
          <label className="security-field">
            <span className="security-field-label">{t.securityConfirmPassword}</span>
            <input
              type="password"
              className="security-input"
              value={confirm}
              onChange={e => setConfirm(e.target.value)}
              autoComplete="new-password"
              required
            />
          </label>
        </div>
        <div className="security-actions">
          <button type="submit" className="btn-primary" disabled={passwordPending}>
            {passwordPending ? t.loading : t.securityPasswordBtn}
          </button>
          <OutcomeMessage outcome={passwordOutcome} />
        </div>
      </form>

      <div className="appearance-section">
        <div>
          <p className="appearance-label">{t.securitySessionsTitle}</p>
          <p className="appearance-hint">{t.securitySessionsHint}</p>
        </div>
        <div className="security-actions">
          <button
            type="button"
            className="btn-secondary"
            onClick={handleLogoutOthers}
            disabled={sessionsPending}
          >
            {sessionsPending ? t.loading : t.securityLogoutOthersBtn}
          </button>
          <OutcomeMessage outcome={sessionsOutcome} />
        </div>
      </div>
    </div>
  )
}
