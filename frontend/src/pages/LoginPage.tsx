import { useState } from 'react'
import { login } from '../api/client'
import { useAuth } from '../contexts/AuthContext'
import { useT } from '../i18n'
import { Wordmark } from '../components/Brand'
import { DEMO_PASSWORD, DEMO_USERNAME, IS_DEMO } from '../demo/config'
import DemoLoginNotice from '../demo/DemoLoginNotice'
import LanguageSelect from '../components/LanguageSelect'

export default function LoginPage() {
  const { onLoginSuccess } = useAuth()
  const { t } = useT()
  // Prefilled in demo builds so the visitor can just press the button; the
  // notice above the form still spells the credentials out.
  const [username, setUsername] = useState(IS_DEMO ? DEMO_USERNAME : '')
  const [password, setPassword] = useState(IS_DEMO ? DEMO_PASSWORD : '')
  const [remember, setRemember] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setPending(true)
    try {
      const user = await login(username, password, remember)
      onLoginSuccess(user.username)
    } catch (err: unknown) {
      const { status, retryAfter } = err as { status?: number; retryAfter?: number }
      if (status === 429) {
        // Retry-After viene en segundos; se redondea hacia arriba a minutos
        // porque «espera 247 segundos» no ayuda a nadie.
        const minutes = Math.max(1, Math.ceil((retryAfter ?? 60) / 60))
        setError(t.authErrorTooManyAttempts(minutes))
      } else {
        setError(status === 401 ? t.authErrorInvalidCredentials : t.authErrorUnexpected)
      }
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="auth-container">
      <div className="auth-card">
        <Wordmark size="lg" className="auth-logo" />
        <h1 className="auth-title">{t.authLoginTitle}</h1>
        {IS_DEMO && <DemoLoginNotice />}
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
          <label className="auth-remember">
            <input
              id="auth-remember"
              type="checkbox"
              checked={remember}
              onChange={e => setRemember(e.target.checked)}
            />
            {t.authRememberMe}
          </label>
          {error && <div className="auth-error">{error}</div>}
          <button type="submit" className="auth-btn" disabled={pending}>
            {pending ? t.loading : t.authLoginBtn}
          </button>
        </form>
        {/* The app follows the browser's language, but that guess can be wrong —
            and this screen is the first thing a visitor sees, so the override
            has to be reachable before signing in. */}
        <div className="auth-lang">
          <LanguageSelect />
        </div>
      </div>
    </div>
  )
}
