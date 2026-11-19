import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { putPushSubscription, testPush, unsubscribePush } from '../api/client'
import { usePushConfig } from '../api/queries'
import type { PushSubscriptionPayload, PushTestResult } from '../api/types'
import { useAuth } from '../contexts/AuthContext'
import { IS_DEMO } from '../demo/config'
import { useT } from '../i18n'
import type { Lang } from '../i18n'
import { base64UrlBytes, isAppleMobile, isStandalone, pushSupported, subscribedWith } from './support'

/**
 * Push notifications on this device: `insecure` (served over plain HTTP) · `install` (an iPhone
 * or iPad in Safari: only the app added to the Home Screen gets them) · `unsupported` ·
 * `pending` (asking the server) · `error` · `unavailable` (the server has no AUTH_SECRET) ·
 * `denied` (blocked in the browser's settings) · `off` · `on`.
 */
export type PushStatus =
  | 'insecure' | 'install' | 'unsupported' | 'pending' | 'error' | 'unavailable' | 'denied' | 'off' | 'on'

export interface PushValue {
  status: PushStatus
  /** Turning them on or off. */
  busy: boolean
  /** Asks for permission (call it from a tap: Safari only asks then) and registers this device; whether they are on. */
  enable: () => Promise<boolean>
  disable: () => Promise<void>
  /** Registers the device again and sends it a test notification. */
  sendTest: () => Promise<PushTestResult>
}

export const SERVICE_WORKER = '/sw.js'
const STORAGE_KEY = 'finlytics_push'

const PushContext = createContext<PushValue | null>(null)

/** Whether `username` turned them on in this browser (the browser keeps the subscription itself). */
function enabledFor(username: string | null): boolean {
  if (!username) return false
  try { return localStorage.getItem(STORAGE_KEY) === username } catch { return false }
}

function rememberEnabled(username: string | null): void {
  try {
    if (username) localStorage.setItem(STORAGE_KEY, username)
    else localStorage.removeItem(STORAGE_KEY)
  } catch { /* private browsing: nothing to remember */ }
}

function subscriptionBody(subscription: PushSubscription, lang: Lang): PushSubscriptionPayload {
  const keys = subscription.toJSON().keys ?? {}
  return { endpoint: subscription.endpoint, keys: { p256dh: keys.p256dh ?? '', auth: keys.auth ?? '' }, locale: lang }
}

async function currentSubscription(): Promise<PushSubscription | null> {
  const registration = await navigator.serviceWorker.getRegistration()
  return (await registration?.pushManager.getSubscription()) ?? null
}

/** Drops a subscription made with an older key of the server, there and in the browser. */
async function forget(subscription: PushSubscription): Promise<void> {
  await unsubscribePush(subscription.endpoint).catch(() => undefined)
  await subscription.unsubscribe()
}

/** Why push cannot work in this browser at all, or null when it can. */
function browserStatus(): PushStatus | null {
  if (IS_DEMO) return 'unsupported'
  if (!window.isSecureContext) return 'insecure'
  if (!pushSupported()) return isAppleMobile() && !isStandalone() ? 'install' : 'unsupported'
  return null
}

/**
 * The push notifications of the signed-in user on this device (src/finlytics/notifications/push.py):
 * turned on from Settings → Notifications, and registered again each time the app opens and
 * when the language changes, so the server keeps the device's session, language and a
 * subscription made with its current key.
 */
export function PushProvider({ children }: { children: ReactNode }) {
  const { username } = useAuth()
  const { lang } = useT()
  const supported = pushSupported()
  const config = usePushConfig({ enabled: supported })
  const publicKey = config.data?.public_key ?? null
  const [enabled, setEnabled] = useState(() => enabledFor(username))
  const [permission, setPermission] = useState<NotificationPermission>(
    () => (supported ? Notification.permission : 'default'),
  )
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!supported || !username || !publicKey || !enabledFor(username)) return
    if (Notification.permission !== 'granted') return
    let cancelled = false
    async function refresh(key: Uint8Array<ArrayBuffer>) {
      const registration = await navigator.serviceWorker.register(SERVICE_WORKER)
      let subscription = await registration.pushManager.getSubscription()
      if (subscription && !subscribedWith(subscription, key)) {
        // The server's key changed (a new AUTH_SECRET): the old subscription no longer works.
        await forget(subscription)
        const ready = await navigator.serviceWorker.ready
        subscription = await ready.pushManager
          .subscribe({ userVisibleOnly: true, applicationServerKey: key })
          .catch(() => null)
      }
      if (!subscription) {
        // The browser dropped it: off until the user turns them on again.
        rememberEnabled(null)
        if (!cancelled) setEnabled(false)
        return
      }
      await putPushSubscription(subscriptionBody(subscription, lang))
    }
    // Offline, or the server is unreachable: nothing changes, the next opening tries again.
    refresh(base64UrlBytes(publicKey)).catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [supported, username, publicKey, lang])

  const enable = useCallback(async (): Promise<boolean> => {
    if (!username || !publicKey || !pushSupported()) return false
    setBusy(true)
    try {
      // First, while the tap is being handled: Safari only asks for permission then.
      const answer = await Notification.requestPermission()
      setPermission(answer)
      if (answer !== 'granted') return false
      const key = base64UrlBytes(publicKey)
      await navigator.serviceWorker.register(SERVICE_WORKER)
      const registration = await navigator.serviceWorker.ready
      let subscription = await registration.pushManager.getSubscription()
      if (subscription && !subscribedWith(subscription, key)) {
        await forget(subscription)
        subscription = null
      }
      subscription ??= await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key })
      await putPushSubscription(subscriptionBody(subscription, lang))
      rememberEnabled(username)
      setEnabled(true)
      return true
    } finally {
      setBusy(false)
    }
  }, [username, publicKey, lang])

  const disable = useCallback(async (): Promise<void> => {
    setBusy(true)
    try {
      const subscription = pushSupported() ? await currentSubscription() : null
      if (subscription) {
        await unsubscribePush(subscription.endpoint)
        await subscription.unsubscribe()
      }
      rememberEnabled(null)
      setEnabled(false)
    } finally {
      setBusy(false)
    }
  }, [])

  const sendTest = useCallback(async (): Promise<PushTestResult> => {
    const subscription = await currentSubscription()
    if (!subscription) {
      rememberEnabled(null)
      setEnabled(false)
      return { ok: false, error: 'gone' }
    }
    await putPushSubscription(subscriptionBody(subscription, lang))
    const result = await testPush(subscription.endpoint)
    if (result.error === 'gone') {
      await subscription.unsubscribe().catch(() => false)
      rememberEnabled(null)
      setEnabled(false)
    }
    return result
  }, [lang])

  let status: PushStatus
  const unavailableHere = browserStatus()
  if (unavailableHere) status = unavailableHere
  else if (config.isPending) status = 'pending'
  else if (config.isError) status = 'error'
  else if (!publicKey) status = 'unavailable'
  else if (permission === 'denied') status = 'denied'
  else status = permission === 'granted' && enabled ? 'on' : 'off'

  const value = useMemo<PushValue>(
    () => ({ status, busy, enable, disable, sendTest }),
    [status, busy, enable, disable, sendTest],
  )
  return <PushContext.Provider value={value}>{children}</PushContext.Provider>
}

/** Push notifications on this device; null outside {@link PushProvider}. */
export function usePush(): PushValue | null {
  return useContext(PushContext)
}
