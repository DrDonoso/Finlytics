// Finlytics' service worker: only for the push notifications of the server
// (src/finlytics/notifications/push.py, frontend/src/push/). Their messages are declarative
// ("web_push": 8030): Safari on iOS 18.4 and later shows them by itself and opens their
// `navigate` page; everywhere else this worker shows them and opens that page when one is
// tapped. Nothing else: no fetch handler, nothing cached.

self.addEventListener('install', () => {
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim())
})

/** The notification a push message describes (null when it describes none). */
function notificationOf(data) {
  let message = null
  try {
    message = data ? data.json() : null
  } catch {
    return null
  }
  const notification = message && message.web_push === 8030 ? message.notification : null
  if (!notification || typeof notification.title !== 'string' || !notification.title) return null
  return { notification, badge: message.app_badge }
}

async function show(data) {
  const found = notificationOf(data)
  if (!found) {
    // Every push must show something: browsers revoke the subscriptions that stay silent.
    await self.registration.showNotification('Finlytics', { data: { navigate: '/' } })
    return
  }
  const { title, navigate, ...options } = found.notification
  const badge = Number(found.badge)
  await Promise.all([
    self.registration.showNotification(title, { ...options, data: { navigate } }),
    Number.isInteger(badge) && badge >= 0 && 'setAppBadge' in self.navigator
      ? self.navigator.setAppBadge(badge).catch(() => undefined)
      : undefined,
  ])
}

self.addEventListener('push', (event) => {
  event.waitUntil(show(event.data))
})

/** Shows `navigate` (a page of Finlytics only) in an open window of the app, or in a new one. */
async function open(navigate) {
  let url
  try {
    url = new URL(typeof navigate === 'string' ? navigate : '/', self.location.origin)
  } catch {
    url = new URL('/', self.location.origin)
  }
  if (url.origin !== self.location.origin) return
  const windows = await self.clients.matchAll({ type: 'window' })
  for (const client of windows) {
    try {
      await client.focus()
      await client.navigate(url.href)
      return
    } catch {
      // Not one this worker can steer: try the next one, or a new window.
    }
  }
  await self.clients.openWindow(url.href)
}

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  event.waitUntil(open(event.notification.data && event.notification.data.navigate))
})
