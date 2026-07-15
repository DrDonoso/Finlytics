import { lazy } from 'react'
import type { LazyExoticComponent, ComponentType } from 'react'

export interface PluginViewEntry {
  icon: string
  name: string
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  component: LazyExoticComponent<ComponentType<any>>
}

export const PLUGIN_VIEW_REGISTRY: Record<string, PluginViewEntry> = {
  'indexa-capital': {
    icon: '🏦',
    name: 'Indexa Capital',
    component: lazy(() => import('./views/IndexaView')),
  },
  'fidelity-espp': {
    icon: '💼',
    name: 'Fidelity ESPP',
    component: lazy(() => import('./views/FidelityView')),
  },
}
