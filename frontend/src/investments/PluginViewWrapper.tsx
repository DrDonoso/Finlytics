import { Suspense } from 'react'
import { useParams, Link } from 'react-router'
import { PLUGIN_VIEW_REGISTRY } from './registry'
import { useT } from '../i18n'
import { DEMO_PLUGIN_IDS, IS_DEMO } from '../demo/config'

export default function PluginViewWrapper() {
  const { pluginId } = useParams<{ pluginId: string }>()
  const { t } = useT()

  const registered = pluginId ? PLUGIN_VIEW_REGISTRY[pluginId] : undefined
  // The demo only carries data for some connectors; the rest would mount a view
  // whose endpoints are unhandled and render an error instead of an empty state.
  const entry = IS_DEMO && (!pluginId || !DEMO_PLUGIN_IDS.includes(pluginId))
    ? undefined
    : registered

  if (!entry) {
    return (
      <main className="dashboard">
        <div className="card">
          <div className="state-box">
            <span className="icon">🔌</span>
            <p>{t.invPluginNotAvailable}</p>
            <Link to={IS_DEMO ? '/investments' : '/settings/connectors'} className="btn-primary">
              {IS_DEMO ? t.navInvestments : t.investmentsManageConnectors}
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
