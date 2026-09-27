import { useCallback, useSyncExternalStore } from 'react'

/** Matches the CSS breakpoint below which the sidebar becomes a drawer and the bottom nav appears. */
export const COMPACT_NAV_QUERY = '(max-width: 767px)'

/** Live `matchMedia` result for `query`; re-renders only when the match flips. */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback((onChange: () => void) => {
    const mq = window.matchMedia(query)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [query])
  return useSyncExternalStore(subscribe, () => window.matchMedia(query).matches, () => false)
}

export function useIsCompactNav(): boolean {
  return useMediaQuery(COMPACT_NAV_QUERY)
}
