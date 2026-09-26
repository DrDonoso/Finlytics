import { Component, type ReactNode } from 'react'
import { useT } from '../i18n'
import { IconAlert } from './icons'

interface Props {
  /** The boundary clears itself when this changes, so navigating away recovers. */
  resetKey: string
  children: ReactNode
}

interface State {
  failed: boolean
  resetKey: string
}

/** Keeps a page that fails to render inside the content area, with the shell still
 *  usable. The usual cause is a lazily loaded page whose chunk no longer exists
 *  because a new version was deployed while the tab was open; only a reload fixes
 *  that, since React caches the rejected import.
 *
 *  It resets through state rather than a `key`: a key would remount the Suspense
 *  boundary below on every navigation and flash its fallback. */
export default class RouteErrorBoundary extends Component<Props, State> {
  state: State = { failed: false, resetKey: this.props.resetKey }

  static getDerivedStateFromProps(props: Props, state: State): Partial<State> | null {
    return props.resetKey === state.resetKey ? null : { failed: false, resetKey: props.resetKey }
  }

  static getDerivedStateFromError(): Partial<State> {
    return { failed: true }
  }

  render() {
    return this.state.failed ? <PageLoadFailed /> : this.props.children
  }
}

function PageLoadFailed() {
  const { t } = useT()
  return (
    <main className="dashboard">
      <div className="card">
        <div className="state-box" role="alert">
          <IconAlert size={18} />
          <p>{t.pageLoadFailed}</p>
          <button type="button" className="btn-primary" onClick={() => window.location.reload()}>
            {t.pageReload}
          </button>
        </div>
      </div>
    </main>
  )
}
