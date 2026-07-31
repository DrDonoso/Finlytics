/**
 * Translates a network or API error into a user-facing message.
 *
 * Raw `String(e)` calls in catch blocks were printing implementation noise
 * like "TypeError: Failed to fetch" directly on screen.
 */
import type { Dict } from '../i18n'

/**
 * `fetch` rejects with TypeError when the connection cannot be established
 * (server down, DNS, CORS, no network). A 4xx/5xx response does not go through
 * here — `apiFetch` throws that as a regular Error.
 */
function isNetworkFailure(error: unknown): boolean {
  return error instanceof TypeError
}

/** User-facing message. */
export function errorMessage(error: unknown, t: Dict): string {
  if (isNetworkFailure(error)) return t.errorNetwork
  const detail = error instanceof Error ? error.message : String(error)
  return t.errorUnexpected(detail)
}
