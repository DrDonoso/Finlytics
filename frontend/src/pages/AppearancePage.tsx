import { useTheme } from '../contexts/ThemeContext'
import type { AccentPalette, ThemeMode } from '../contexts/ThemeContext'
import type { ReactNode } from 'react'
import { useT } from '../i18n'
import { usePrivacy } from '../contexts/PrivacyContext'
import { IconSun, IconMoon, IconMonitor, IconEye, IconEyeOff } from '../components/icons'

export default function AppearancePage() {
  const { t } = useT()
  const { mode, setMode, palette, setPalette } = useTheme()
  const { hidden, toggle } = usePrivacy()

  const options: { value: ThemeMode; label: string; icon: ReactNode }[] = [
    { value: 'light', label: t.themeLight, icon: <IconSun size={16} /> },
    { value: 'dark',  label: t.themeDark,  icon: <IconMoon size={16} /> },
    { value: 'system', label: t.themeSystem, icon: <IconMonitor size={16} /> },
  ]

  const paletteOptions: { value: AccentPalette; label: string; swatches: string[] }[] = [
    { value: 'classic', label: t.paletteClassicBlue, swatches: ['#2563eb', '#dbeafe', '#1d4ed8'] },
    { value: 'emerald', label: t.paletteEmerald, swatches: ['#047857', '#d1fae5', '#065f46'] },
    { value: 'violet', label: t.paletteViolet, swatches: ['#7c3aed', '#ede9fe', '#6d28d9'] },
    { value: 'amber', label: t.paletteAmber, swatches: ['#b45309', '#fef3c7', '#92400e'] },
    { value: 'contrast', label: t.paletteHighContrast, swatches: ['#111827', '#f8fafc', '#000000'] },
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

      <div className="appearance-section">
        <div>
          <p className="appearance-label">{t.settingsAccentLabel}</p>
          <p className="appearance-hint">{t.settingsAccentHint}</p>
        </div>
        <div className="palette-grid">
          {paletteOptions.map(opt => (
            <button
              key={opt.value}
              type="button"
              className={`palette-option${palette === opt.value ? ' active' : ''}`}
              onClick={() => setPalette(opt.value)}
              aria-pressed={palette === opt.value}
            >
              <span className="palette-swatch-row" aria-hidden="true">
                {opt.swatches.map(color => (
                  <span key={color} className="palette-swatch" style={{ background: color }} />
                ))}
              </span>
              <span>{opt.label}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="appearance-section">
        <div className="privacy-toggle-row">
          <div>
            <p className="appearance-label">
              {t.settingsPrivacyLabel}
              <span className="privacy-shortcut">Alt+Shift+H</span>
            </p>
            <p className="appearance-hint">{t.settingsPrivacyHint}</p>
          </div>
          <button
            type="button"
            className={`privacy-switch${hidden ? ' active' : ''}`}
            onClick={toggle}
            aria-pressed={hidden}
          >
            {hidden ? <IconEyeOff size={16} /> : <IconEye size={16} />}
            <span>{hidden ? t.privacyStateHidden : t.privacyStateVisible}</span>
          </button>
        </div>
      </div>
    </div>
  )
}
