import { useState } from 'react'
import { setupUser } from '../api/client'
import { useAuth } from '../contexts/AuthContext'
import { useT } from '../i18n'

const MIN_PASSWORD_LENGTH = 8

export default function SetupPage() {
  const { onSetupSuccess } = useAuth()
  const { t } = useT()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  function validate(): string | null {
    if (username.trim().length < 3) return t.authErrorUsernameTooShort
    if (password.length < MIN_PASSWORD_LENGTH) return t.authErrorPasswordTooShort
    if (password !== confirmPassword) return t.authErrorPasswordMismatch
    return null
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const validationError = validate()
    if (validationError) { setError(validationError); return }
    setError(null)
    setPending(true)
    try {
      const user = await setupUser(username.trim(), password)
      onSetupSuccess(user.username)
    } catch (err: unknown) {
      const status = (err as { status?: number }).status
      setError(status === 409 ? t.authErrorAlreadySetup : t.authErrorUnexpected)
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="auth-container">
      <div className="auth-card">
        <div className="auth-logo">Finlytics</div>
        <h1 className="auth-title">{t.authSetupTitle}</h1>
        <p className="auth-subtitle">{t.authSetupSubtitle}</p>
        <form onSubmit={handleSubmit} className="auth-form">
          <div className="auth-field">
            <label htmlFor="setup-username">{t.authUsername}</label>
            <input
              id="setup-username"
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              autoComplete="username"
              autoFocus
              required
            />
          </div>
          <div className="auth-field">
            <label htmlFor="setup-password">{t.authPassword}</label>
            <input
              id="setup-password"
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              autoComplete="new-password"
              required
            />
          </div>
          <div className="auth-field">
            <label htmlFor="setup-confirm">{t.authConfirmPassword}</label>
            <input
              id="setup-confirm"
              type="password"
              value={confirmPassword}
              onChange={e => setConfirmPassword(e.target.value)}
              autoComplete="new-password"
              required
            />
          </div>
          {error && <div className="auth-error">{error}</div>}
          <button type="submit" className="auth-btn" disabled={pending}>
            {pending ? t.loading : t.authSetupBtn}
          </button>
        </form>
      </div>
    </div>
  )
}
