import { useTheme } from '../contexts/ThemeContext'
import type { ThemeMode } from '../contexts/ThemeContext'
import { useT } from '../i18n'

export default function AppearancePage() {
  const { t } = useT()
  const { mode, setMode } = useTheme()

  const options: { value: ThemeMode; label: string; icon: string }[] = [
    { value: 'light', label: t.themeLight, icon: '☀️' },
    { value: 'dark',  label: t.themeDark,  icon: '🌙' },
    { value: 'system', label: t.themeSystem, icon: '💻' },
  ]

  return (
    <div className="card settings-card">
      <h2 className="settings-section-title">{t.settingsAppearanceTitle}</h2>
      <div className="appearance-section">
        <p className="appearance-label">{t.settingsThemeLabel}</p>
        <div className="theme-segmented">
          {options.map(opt => (
            <button
              key={opt.value}
              type="button"
              className={`theme-seg-btn${mode === opt.value ? ' active' : ''}`}
              onClick={() => setMode(opt.value)}
              aria-pressed={mode === opt.value}
            >
              <span className="theme-seg-icon">{opt.icon}</span>
              <span>{opt.label}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
