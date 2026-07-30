/**
 * Traduce un error de red o de API a un mensaje que el usuario pueda entender.
 *
 * Los `catch` de la aplicación hacían `String(e)`, que pinta en pantalla cosas
 * como «TypeError: Failed to fetch» o «Error: HTTP 500 Internal Server Error»:
 * ruido de implementación que no le dice nada a quien lo lee.
 */
import type { Dict } from '../i18n'

/**
 * `fetch` rechaza con TypeError cuando no llega a establecer la conexión
 * (servidor caído, DNS, CORS, red). Un servidor que responde 4xx/5xx no pasa
 * por aquí: eso lo lanza `apiFetch` como Error normal.
 */
function isNetworkFailure(error: unknown): boolean {
  return error instanceof TypeError
}

/** Mensaje presentable para el usuario. */
export function errorMessage(error: unknown, t: Dict): string {
  if (isNetworkFailure(error)) return t.errorNetwork
  const detail = error instanceof Error ? error.message : String(error)
  return t.errorUnexpected(detail)
}
