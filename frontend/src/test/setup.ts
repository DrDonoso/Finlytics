/** Common setup for all frontend tests. */
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, beforeAll, vi } from 'vitest'

// jsdom does not implement matchMedia, which ThemeContext uses to resolve the
// system theme. Without this, any test that mounts the theme provider fails.
beforeAll(() => {
  if (!window.matchMedia) {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))
  }
})

// Testing Library does not unmount automatically when `globals` is active in
// Vitest; without this, components from one test would linger in the DOM during the next.
afterEach(() => {
  cleanup()
})
