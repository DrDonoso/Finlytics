/** Configuración común a todos los tests del frontend. */
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, beforeAll, vi } from 'vitest'

// jsdom no implementa matchMedia, que ThemeContext usa para resolver el tema
// del sistema. Sin esto cualquier test que monte el proveedor de tema falla.
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

// Testing Library no desmonta solo cuando `globals` está activo en Vitest, y sin
// esto los componentes de un test seguirían en el DOM durante el siguiente.
afterEach(() => {
  cleanup()
})
