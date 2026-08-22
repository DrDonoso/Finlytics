/**
 * The PWA status-bar colour is not visible in a browser tab, so a drift between
 * these values and `--bg` in tokens.css only shows up on someone's home screen.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { ThemeProvider, useTheme } from '../contexts/ThemeContext'

const LIGHT = '#f4f6f9'
const DARK = '#0c1420'

function themeColor(): string | null {
  return document.querySelector('meta[name="theme-color"]')?.getAttribute('content') ?? null
}

function Harness() {
  const { setMode } = useTheme()
  return (
    <>
      <button type="button" onClick={() => setMode('dark')}>go dark</button>
      <button type="button" onClick={() => setMode('light')}>go light</button>
    </>
  )
}

describe('theme-color meta', () => {
  beforeEach(() => {
    localStorage.clear()
    document.head.innerHTML = '<meta name="theme-color" content="' + LIGHT + '">'
  })

  it('follows the selected theme', async () => {
    const user = userEvent.setup()
    render(<ThemeProvider><Harness /></ThemeProvider>)

    expect(themeColor()).toBe(LIGHT)

    await user.click(screen.getByRole('button', { name: 'go dark' }))
    expect(themeColor()).toBe(DARK)
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')

    await user.click(screen.getByRole('button', { name: 'go light' }))
    expect(themeColor()).toBe(LIGHT)
  })

  it('does not throw when the meta tag is absent', () => {
    document.head.innerHTML = ''
    expect(() => render(<ThemeProvider><Harness /></ThemeProvider>)).not.toThrow()
  })
})
