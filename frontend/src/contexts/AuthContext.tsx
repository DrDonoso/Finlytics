import { createContext, useContext, useEffect, useRef, useState, useCallback, useMemo, createElement } from 'react'
import type { ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { getAuthStatus, getMe, logout as apiLogout, registerOn401Handler } from '../api/client'

interface AuthState {
  loading: boolean
  initialized: boolean
  authenticated: boolean
  username: string | null
}

interface AuthContextValue extends AuthState {
  onSetupSuccess: (username: string) => void
  onLoginSuccess: (username: string) => void
  onLogout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue>({
  loading: true,
  initialized: false,
  authenticated: false,
  username: null,
  onSetupSuccess: () => {},
  onLoginSuccess: () => {},
  onLogout: async () => {},
})

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    loading: true,
    initialized: false,
    authenticated: false,
    username: null,
  })

  useEffect(() => {
    let cancelled = false

    async function init() {
      try {
        const status = await getAuthStatus()
        if (cancelled) return

        if (status.authenticated) {
          try {
            const me = await getMe()
            if (!cancelled) setState({ loading: false, ...status, username: me.username })
          } catch {
            if (!cancelled) setState({ loading: false, ...status, username: null })
          }
        } else {
          if (!cancelled) setState({ loading: false, ...status, username: null })
        }
      } catch {
        if (!cancelled) setState({ loading: false, initialized: false, authenticated: false, username: null })
      }
    }

    init()
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    registerOn401Handler(() => {
      setState(s => ({ ...s, authenticated: false, username: null }))
    })
  }, [])

  // Cached responses belong to the session that fetched them, whether it ended by logout or by a 401.
  // This runs after the authenticated tree has unmounted, so no observer can re-fetch into the cleared cache.
  const queryClient = useQueryClient()
  const wasAuthenticated = useRef(false)
  useEffect(() => {
    if (wasAuthenticated.current && !state.authenticated) queryClient.clear()
    wasAuthenticated.current = state.authenticated
  }, [state.authenticated, queryClient])

  const onSetupSuccess = useCallback((username: string) => {
    setState({ loading: false, initialized: true, authenticated: true, username })
  }, [])

  const onLoginSuccess = useCallback((username: string) => {
    setState(s => ({ ...s, authenticated: true, username }))
  }, [])

  const onLogout = useCallback(async () => {
    try { await apiLogout() } catch { /* ignore — clears cookie best-effort */ }
    setState(s => ({ ...s, authenticated: false, username: null }))
  }, [])

  // Memoised: without this the object is new on every provider render and triggers a full re-render of the app, which hangs from this context.
  const value = useMemo(
    () => ({ ...state, onSetupSuccess, onLoginSuccess, onLogout }),
    [state, onSetupSuccess, onLoginSuccess, onLogout],
  )

  return createElement(AuthContext.Provider, { value }, children)
}

export function useAuth(): AuthContextValue {
  return useContext(AuthContext)
}
