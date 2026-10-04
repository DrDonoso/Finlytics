export const MIN_PASSWORD_LENGTH = 8

// bcrypt reads only the first 72 bytes; the API rejects anything longer.
export const MAX_PASSWORD_BYTES = 72

export function passwordTooLong(password: string): boolean {
  return new TextEncoder().encode(password).length > MAX_PASSWORD_BYTES
}
