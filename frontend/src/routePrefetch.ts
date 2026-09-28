import type { ComponentType } from 'react'
import { matchPath } from 'react-router'
import { PLUGIN_VIEW_REGISTRY } from './investments/registry'

type Chunk = () => Promise<unknown>

/**
 * Every lazily loaded page, keyed by its route pattern. App.tsx builds its lazy()
 * components from these same loaders, so a prefetch and the navigation after it
 * resolve one module instead of two.
 */
export const pageChunks = {
  '/': () => import('./pages/Dashboard'),
  '/finances': () => import('./pages/FinancesOverviewPage'),
  '/transactions': () => import('./pages/TransactionsPage'),
  '/analytics': () => import('./pages/AnalyticsPage'),
  '/statements': () => import('./pages/StatementsPage'),
  '/investments': () => import('./pages/InvestmentsLandingPage'),
  '/investments/:pluginId': () => import('./investments/PluginViewWrapper'),
  '/mortgage': () => import('./pages/MortgagePage'),
  '/settings/accounts': () => import('./pages/AccountsPage'),
  '/settings/tags': () => import('./pages/SettingsPage'),
  '/settings/categories': () => import('./pages/CategoriesPage'),
  '/settings/appearance': () => import('./pages/AppearancePage'),
  '/settings/backup': () => import('./pages/BackupPage'),
  '/settings/security': () => import('./pages/SecurityPage'),
  '/settings/connectors': () => import('./pages/ConnectorsPage'),
  '/settings/assistant': () => import('./pages/AssistantSettingsPage'),
  '/settings/rules': () => import('./pages/RulesPage'),
  '/settings/about': () => import('./pages/AboutPage'),
} satisfies Record<string, () => Promise<{ default: ComponentType }>>

/** Where a visitor most likely goes next, whichever screen they landed on. */
export const LIKELY_NEXT = ['/', '/finances', '/transactions', '/analytics', '/investments', '/mortgage']

/** What opening `path` downloads: its page and, on a connector route, that connector's view. */
export function chunksFor(path: string): Chunk[] {
  for (const [pattern, page] of Object.entries(pageChunks)) {
    const match = matchPath(pattern, path)
    if (!match) continue
    const pluginId = match.params.pluginId
    const view = pluginId ? PLUGIN_VIEW_REGISTRY[pluginId]?.load : undefined
    return view ? [page, view] : [page]
  }
  return []
}

export interface Prefetcher {
  /** Starts downloading what `path` needs. Settles once that does; never rejects. */
  route(path: string): Promise<void>
  /** Prefetches the in-app link, or `data-prefetch` element, that an event came from. */
  target(target: EventTarget | null): void
  /** Prefetches `paths` one at a time while the browser is idle. Returns a cancel function. */
  whenIdle(paths: readonly string[]): () => void
}

export function createPrefetcher(resolve: (path: string) => Chunk[]): Prefetcher {
  const started = new Set<Chunk>()

  function route(path: string): Promise<void> {
    const pending = resolve(path).filter(chunk => !started.has(chunk))
    for (const chunk of pending) started.add(chunk)
    // A failure is not reported here: navigating to the page imports it again,
    // and RouteErrorBoundary owns that error.
    return Promise.allSettled(pending.map(chunk => chunk())).then(() => undefined)
  }

  function target(eventTarget: EventTarget | null): void {
    if (!(eventTarget instanceof Element)) return
    const el = eventTarget.closest<HTMLElement>('a[href], [data-prefetch]')
    if (el instanceof HTMLAnchorElement) {
      if (el.origin === window.location.origin) void route(el.pathname)
    } else if (el?.dataset.prefetch) {
      void route(el.dataset.prefetch)
    }
  }

  function whenIdle(paths: readonly string[]): () => void {
    if (prefersSavingData()) return () => {}
    const queue = [...paths]
    let stopped = false
    let cancelNext = () => {}
    const step = () => {
      const path = queue.shift()
      if (stopped || path === undefined) return
      void route(path).then(() => {
        if (!stopped) cancelNext = onIdle(step)
      })
    }
    cancelNext = onIdle(step)
    return () => {
      stopped = true
      cancelNext()
    }
  }

  return { route, target, whenIdle }
}

function onIdle(callback: () => void): () => void {
  if (typeof window.requestIdleCallback === 'function') {
    const id = window.requestIdleCallback(callback, { timeout: 5000 })
    return () => window.cancelIdleCallback(id)
  }
  // Safari has no requestIdleCallback.
  const id = window.setTimeout(callback, 1500)
  return () => window.clearTimeout(id)
}

function prefersSavingData(): boolean {
  const { connection } = navigator as Navigator & { connection?: { saveData?: boolean } }
  return connection?.saveData === true
}

export const prefetch = createPrefetcher(chunksFor)
