/**
 * bcrypt only reads the first 72 bytes of a password, so the server rejects a
 * longer one. The form has to count bytes, not characters, or a password of
 * accented letters or emoji passes the client check and fails on submit.
 */
import { describe, expect, it } from 'vitest'

import { MAX_PASSWORD_BYTES, MIN_PASSWORD_LENGTH, passwordTooLong } from './password'

describe('passwordTooLong', () => {
  it('accepts exactly the byte limit and rejects one byte more', () => {
    expect(passwordTooLong('a'.repeat(72))).toBe(false)
    expect(passwordTooLong('a'.repeat(73))).toBe(true)
  })

  it('counts multi-byte characters by their UTF-8 length', () => {
    expect(passwordTooLong('€'.repeat(24))).toBe(false)
    expect(passwordTooLong('€'.repeat(25))).toBe(true)
    expect(passwordTooLong('😀'.repeat(18))).toBe(false)
    expect(passwordTooLong('😀'.repeat(19))).toBe(true)
  })

  it('matches the server limits', () => {
    expect(MIN_PASSWORD_LENGTH).toBe(8)
    expect(MAX_PASSWORD_BYTES).toBe(72)
  })
})
