import { Suspense } from 'react'
import { useParams, Link } from 'react-router'
import { PLUGIN_VIEW_REGISTRY } from './registry'
import { useT } from '../i18n'

export default function PluginViewWrapper() {
  const { pluginId } = useParams<{ pluginId: string }>()
  const { t } = useT()

  const entry = pluginId ? PLUGIN_VIEW_REGISTRY[pluginId] : undefined

  if (!entry) {
    return (
      <main className="dashboard">
        <div className="card">
          <div className="state-box">
            <span className="icon">🔌</span>
            <p>{t.invPluginNotAvailable}</p>
            <Link to="/settings/connectors" className="btn-primary">
              {t.investmentsManageConnectors}
            </Link>
          </div>
        </div>
      </main>
    )
  }

  const { component: PluginComponent } = entry

  return (
    <Suspense fallback={
      <main className="dashboard">
        <div className="card">
          <div className="state-box">
            <span className="icon">⏳</span>
            <span>{t.loading}</span>
          </div>
        </div>
      </main>
    }>
      <PluginComponent />
    </Suspense>
  )
}
