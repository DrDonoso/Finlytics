/**
 * Tests del traductor de errores.
 *
 * Antes los `catch` volcaban `String(e)` directamente en pantalla, así que el
 * usuario leía «TypeError: Failed to fetch». Estos tests fijan que un fallo de
 * red se distinga de un error del servidor, porque la acción que debe tomar
 * quien lo lee es distinta en cada caso.
 */
import { describe, expect, it } from 'vitest'

import es from '../i18n/es'
import en from '../i18n/en'
import { errorMessage } from './errors'

describe('errorMessage', () => {
  it('reconoce un fallo de red', () => {
    // fetch rechaza con TypeError cuando no llega a conectar: servidor caído,
    // DNS, CORS o sin red.
    expect(errorMessage(new TypeError('Failed to fetch'), es)).toBe(es.errorNetwork)
  })

  it('no filtra el mensaje técnico del fallo de red', () => {
    const message = errorMessage(new TypeError('Failed to fetch'), es)

    expect(message).not.toContain('TypeError')
    expect(message).not.toContain('Failed to fetch')
  })

  it('conserva el detalle de un error del servidor', () => {
    // Un 500 sí es accionable: interesa saber qué código devolvió.
    const message = errorMessage(new Error('HTTP 500 Internal Server Error'), es)

    expect(message).toBe(es.errorUnexpected('HTTP 500 Internal Server Error'))
    expect(message).toContain('500')
  })

  it('acepta valores lanzados que no son Error', () => {
    // Nada impide hacer `throw 'algo'`, y el traductor no debe romperse por ello.
    expect(errorMessage('algo raro', es)).toBe(es.errorUnexpected('algo raro'))
    expect(errorMessage(null, es)).toBe(es.errorUnexpected('null'))
    expect(errorMessage(undefined, es)).toBe(es.errorUnexpected('undefined'))
  })

  it('responde en el idioma que se le pasa', () => {
    const network = new TypeError('Failed to fetch')

    expect(errorMessage(network, es)).toBe(es.errorNetwork)
    expect(errorMessage(network, en)).toBe(en.errorNetwork)
    expect(errorMessage(network, es)).not.toBe(errorMessage(network, en))
  })
})
