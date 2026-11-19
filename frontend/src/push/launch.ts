/**
 * The alerts a push notification told: the page it opens carries `?notif=12,13`. main.tsx takes
 * the parameter out of the address before the router starts, so no screen sees it or keeps it in
 * a shared link, and NotificationsProvider marks those alerts as read once the user is signed in.
 */
export const INTENT_PARAM = 'notif'

const MAX_IDS = 50

let pending: number[] = []

/** Takes the told alerts out of the current address, keeping the rest of it. */
export function takeLaunchIntent(location: Location = window.location, history: History = window.history): void {
  const url = new URL(location.href)
  const raw = url.searchParams.get(INTENT_PARAM)
  if (raw === null) return
  pending = raw
    .split(',')
    .map(Number)
    .filter(id => Number.isSafeInteger(id) && id > 0)
    .slice(0, MAX_IDS)
  url.searchParams.delete(INTENT_PARAM)
  history.replaceState(history.state, '', `${url.pathname}${url.search}${url.hash}`)
}

/** The alerts the app was opened for, once (empty afterwards, and without any). */
export function consumeLaunchIntent(): number[] {
  const ids = pending
  pending = []
  return ids
}
