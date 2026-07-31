/**
 * Tests for the error translator.
 *
 * These pin the contract that a network failure is distinguished from a server
 * error, because the remediation for each is different.
 */
import { describe, expect, it } from 'vitest'

import es from '../i18n/es'
import en from '../i18n/en'
import { errorMessage } from './errors'

describe('errorMessage', () => {
  it('recognises a network failure', () => {
    // fetch rejects with TypeError when it cannot connect: server down, DNS, CORS, or offline.
    expect(errorMessage(new TypeError('Failed to fetch'), es)).toBe(es.errorNetwork)
  })

  it('strips the raw error text from a network failure', () => {
    const message = errorMessage(new TypeError('Failed to fetch'), es)

    expect(message).not.toContain('TypeError')
    expect(message).not.toContain('Failed to fetch')
  })

  it('preserves the detail from a server error', () => {
    // A 500 is actionable — knowing the status code matters.
    const message = errorMessage(new Error('HTTP 500 Internal Server Error'), es)

    expect(message).toBe(es.errorUnexpected('HTTP 500 Internal Server Error'))
    expect(message).toContain('500')
  })

  it('handles thrown values that are not Error instances', () => {
    // Nothing prevents `throw 'something'`, so the translator must not crash on non-Error values.
    expect(errorMessage('something odd', es)).toBe(es.errorUnexpected('something odd'))
    expect(errorMessage(null, es)).toBe(es.errorUnexpected('null'))
    expect(errorMessage(undefined, es)).toBe(es.errorUnexpected('undefined'))
  })

  it('returns a message in the language passed to it', () => {
    const network = new TypeError('Failed to fetch')

    expect(errorMessage(network, es)).toBe(es.errorNetwork)
    expect(errorMessage(network, en)).toBe(en.errorNetwork)
    expect(errorMessage(network, es)).not.toBe(errorMessage(network, en))
  })
})
