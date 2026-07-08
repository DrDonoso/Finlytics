import { useState } from 'react'
import { login } from '../api/client'
import { useAuth } from '../contexts/AuthContext'
import { useT } from '../i18n'

export default function LoginPage() {
  const { onLoginSuccess } = useAuth()
  const { t } = useT()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setPending(true)
    try {
      const user = await login(username, password)
      onLoginSuccess(user.username)
    } catch (err: unknown) {
      const status = (err as { status?: number }).status
      setError(status === 401 ? t.authErrorInvalidCredentials : t.authErrorUnexpected)
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="auth-container">
      <div className="auth-card">
        <img src="/logo_withtext.png" alt="Finlytics" className="auth-logo-img" />
        <h1 className="auth-title">{t.authLoginTitle}</h1>
        <form onSubmit={handleSubmit} className="auth-form">
          <div className="auth-field">
            <label htmlFor="auth-username">{t.authUsername}</label>
            <input
              id="auth-username"
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              autoComplete="username"
              autoFocus
              required
            />
          </div>
          <div className="auth-field">
            <label htmlFor="auth-password">{t.authPassword}</label>
            <input
              id="auth-password"
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>
          {error && <div className="auth-error">{error}</div>}
          <button type="submit" className="auth-btn" disabled={pending}>
            {pending ? t.loading : t.authLoginBtn}
          </button>
        </form>
      </div>
    </div>
  )
}
