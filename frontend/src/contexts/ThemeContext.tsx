import { createContext, createElement, useContext, useState, useEffect, useCallback } from 'react'
import type { ReactNode } from 'react'

export type ThemeMode = 'light' | 'dark' | 'system'
export type AccentPalette = 'classic' | 'emerald' | 'violet' | 'amber' | 'contrast'

const LS_KEY = 'finlytics_theme'
const PALETTE_LS_KEY = 'finlytics_accent_palette'

function storedMode(): ThemeMode {
  try {
    const v = localStorage.getItem(LS_KEY)
    if (v === 'light' || v === 'dark' || v === 'system') return v
  } catch { /* ignore */ }
  return 'system'
}

function storedPalette(): AccentPalette {
  try {
    const v = localStorage.getItem(PALETTE_LS_KEY)
    if (v === 'classic' || v === 'emerald' || v === 'violet' || v === 'amber' || v === 'contrast') return v
  } catch { /* ignore */ }
  return 'classic'
}

function systemIsDark(): boolean {
  try { return window.matchMedia('(prefers-color-scheme: dark)').matches } catch { return false }
}

function resolveTheme(mode: ThemeMode): 'light' | 'dark' {
  if (mode === 'system') return systemIsDark() ? 'dark' : 'light'
  return mode
}

function applyTheme(resolved: 'light' | 'dark') {
  document.documentElement.setAttribute('data-theme', resolved)
}

function applyPalette(palette: AccentPalette) {
  document.documentElement.setAttribute('data-palette', palette)
}

interface ThemeContextValue {
  mode: ThemeMode
  setMode: (m: ThemeMode) => void
  resolved: 'light' | 'dark'
  palette: AccentPalette
  setPalette: (p: AccentPalette) => void
}

const ThemeContext = createContext<ThemeContextValue>({
  mode: 'system',
  setMode: () => {},
  resolved: 'light',
  palette: 'classic',
  setPalette: () => {},
})

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(storedMode)
  const [resolved, setResolved] = useState<'light' | 'dark'>(() => resolveTheme(storedMode()))
  const [palette, setPaletteState] = useState<AccentPalette>(storedPalette)

  const setMode = useCallback((m: ThemeMode) => {
    try { localStorage.setItem(LS_KEY, m) } catch { /* ignore */ }
    const r = resolveTheme(m)
    setModeState(m)
    setResolved(r)
    applyTheme(r)
  }, [])

  const setPalette = useCallback((p: AccentPalette) => {
    try { localStorage.setItem(PALETTE_LS_KEY, p) } catch { /* ignore */ }
    setPaletteState(p)
    applyPalette(p)
  }, [])

  // React to OS preference changes (only when mode === 'system')
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = () => {
      if (storedMode() === 'system') {
        const r = resolveTheme('system')
        setResolved(r)
        applyTheme(r)
      }
    }
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])

  // Apply on mount (after FOUC-prevention script in index.html)
  useEffect(() => { applyTheme(resolved) }, [resolved])
  useEffect(() => { applyPalette(palette) }, [palette])

  return createElement(ThemeContext.Provider, { value: { mode, setMode, resolved, palette, setPalette } }, children)
}

export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext)
}
