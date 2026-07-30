/** Configuración común a todos los tests del frontend. */
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// Testing Library no desmonta solo cuando `globals` está activo en Vitest, y sin
// esto los componentes de un test seguirían en el DOM durante el siguiente.
afterEach(() => {
  cleanup()
})
