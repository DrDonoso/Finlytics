import { createContext, useContext, useState, useEffect, useCallback, useMemo, useRef } from 'react'
import type { ReactNode } from 'react'
import type { NotificationOut } from '../api/types'
import {
  getNotifications,
  getUnreadCount,
  markNotificationRead as apiMarkRead,
  markAllNotificationsRead as apiMarkAllRead,
  dismissNotification as apiDismiss,
} from '../api/client'

const POLL_INTERVAL_MS = 60_000

interface NotificationsContextValue {
  notifications: NotificationOut[]
  unreadCount: number
  loading: boolean
  refresh: () => void
  markRead: (id: number) => Promise<void>
  markAllRead: () => Promise<void>
  dismiss: (id: number) => Promise<void>
}

const NotificationsContext = createContext<NotificationsContextValue>({
  notifications: [],
  unreadCount: 0,
  loading: false,
  refresh: () => {},
  markRead: async () => {},
  markAllRead: async () => {},
  dismiss: async () => {},
})

export function NotificationsProvider({ children }: { children: ReactNode }) {
  const [notifications, setNotifications] = useState<NotificationOut[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [loading, setLoading] = useState(false)
  const prevCountRef = useRef<number>(-1)

  const fetchList = useCallback(() => {
    setLoading(true)
    getNotifications()
      .then(list => {
        setNotifications(list)
        const count = list.filter(n => !n.read_at).length
        setUnreadCount(count)
        prevCountRef.current = count
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  // Initial fetch on mount
  useEffect(() => {
    fetchList()
  }, [fetchList])

  // Poll unread-count every 60s; refresh full list when it changes
  useEffect(() => {
    const id = setInterval(() => {
      getUnreadCount()
        .then(({ count }) => {
          setUnreadCount(count)
          if (count !== prevCountRef.current) {
            prevCountRef.current = count
            fetchList()
          }
        })
        .catch(() => {})
    }, POLL_INTERVAL_MS)
    return () => clearInterval(id)
  }, [fetchList])

  const markRead = useCallback(async (id: number) => {
    await apiMarkRead(id)
    fetchList()
  }, [fetchList])

  const markAllRead = useCallback(async () => {
    await apiMarkAllRead()
    fetchList()
  }, [fetchList])

  const dismiss = useCallback(async (id: number) => {
    await apiDismiss(id)
    fetchList()
  }, [fetchList])

  // Sin memoizar, el objeto sería nuevo en cada render y obligaría a
  // re-renderizar a todos los consumidores del contexto aunque nada hubiera
  // cambiado — y aquí hay un sondeo cada 60 s que dispara renders.
  const value = useMemo(
    () => ({
      notifications,
      unreadCount,
      loading,
      refresh: fetchList,
      markRead,
      markAllRead,
      dismiss,
    }),
    [notifications, unreadCount, loading, fetchList, markRead, markAllRead, dismiss],
  )

  return (
    <NotificationsContext.Provider value={value}>
      {children}
    </NotificationsContext.Provider>
  )
}

export function useNotifications(): NotificationsContextValue {
  return useContext(NotificationsContext)
}
