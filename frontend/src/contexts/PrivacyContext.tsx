import { createContext, createElement, useContext, useState, useEffect, useCallback, useMemo } from 'react'
import type { ReactNode } from 'react'

const LS_KEY = 'finlytics_privacy'

function storedHidden(): boolean {
  try { return localStorage.getItem(LS_KEY) === '1' } catch { return false }
}

function applyPrivacy(hidden: boolean) {
  const root = document.documentElement
  if (hidden) root.setAttribute('data-privacy', 'on')
  else root.removeAttribute('data-privacy')
}

interface PrivacyContextValue {
  /** True while monetary values are blurred. */
  hidden: boolean
  setHidden: (v: boolean) => void
  toggle: () => void
}

const PrivacyContext = createContext<PrivacyContextValue>({
  hidden: false,
  setHidden: () => {},
  toggle: () => {},
})

/** Ignore the shortcut while the user is typing, so it cannot eat a keystroke. */
function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  const tag = target.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable
}

export function PrivacyProvider({ children }: { children: ReactNode }) {
  const [hidden, setHiddenState] = useState<boolean>(storedHidden)

  const setHidden = useCallback((v: boolean) => {
    try { localStorage.setItem(LS_KEY, v ? '1' : '0') } catch { /* ignore */ }
    setHiddenState(v)
    applyPrivacy(v)
  }, [])

  const toggle = useCallback(() => { setHidden(!storedHidden()) }, [setHidden])

  // Alt+Shift+H. `code` rather than `key` because holding Option on macOS
  // rewrites `key` into a dead/accented character and the match would fail.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!e.altKey || !e.shiftKey || e.code !== 'KeyH') return
      if (isEditableTarget(e.target)) return
      e.preventDefault()
      toggle()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [toggle])

  // Apply on mount (after the FOUC-prevention script in index.html)
  useEffect(() => { applyPrivacy(hidden) }, [hidden])

  const value = useMemo(() => ({ hidden, setHidden, toggle }), [hidden, setHidden, toggle])

  return createElement(PrivacyContext.Provider, { value }, children)
}

export function usePrivacy(): PrivacyContextValue {
  return useContext(PrivacyContext)
}
