import { Outlet } from 'react-router'
import { useT } from '../i18n'

export default function SettingsLayout() {
  const { t } = useT()

  return (
    <main className="settings-page">
      <div className="settings-container">
        <h1 className="settings-heading">{t.navSettings}</h1>
        <Outlet />
      </div>
    </main>
  )
}
