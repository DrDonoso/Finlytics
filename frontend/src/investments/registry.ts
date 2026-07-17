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
    icon: '/logos/indexa-capital.svg',
    name: 'Indexa Capital',
    component: lazy(() => import('./views/IndexaView')),
  },
  'fidelity-espp': {
    icon: '/logos/fidelity-espp.svg',
    name: 'Fidelity ESPP',
    component: lazy(() => import('./views/FidelityView')),
  },
}

const PLUGIN_ID_ALIASES: Record<string, string> = {
  indexa: 'indexa-capital',
  fidelity: 'fidelity-espp',
}

export function normalizePluginId(pluginId: string): string {
  return PLUGIN_ID_ALIASES[pluginId] ?? pluginId
}

export function getPluginLogo(pluginId: string): string | null {
  return PLUGIN_VIEW_REGISTRY[normalizePluginId(pluginId)]?.icon ?? null
}

export function pluginInitial(name: string): string {
  return name.trim().charAt(0).toUpperCase() || '•'
}
