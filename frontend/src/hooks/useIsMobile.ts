import { useMediaQuery } from './useMediaQuery'

const MOBILE_QUERY = '(max-width: 600px)'

/** Returns true when the viewport is ≤600px (mobile breakpoint). Updates live on resize. */
export function useIsMobile(): boolean {
  return useMediaQuery(MOBILE_QUERY)
}