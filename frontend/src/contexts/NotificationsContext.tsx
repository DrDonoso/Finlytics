import { createContext, useContext, useCallback, useMemo } from 'react'
import type { ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { NotificationOut } from '../api/types'
import {
  markNotificationRead as apiMarkRead,
  markAllNotificationsRead as apiMarkAllRead,
  dismissNotification as apiDismiss,
} from '../api/client'
import { queryKeys, unreadCountOf, useNotificationChangePoll, useNotificationList } from '../api/queries'

interface NotificationsContextValue {
  notifications: NotificationOut[]
  unreadCount: number
  loading: boolean
  refresh: () => void
  markRead: (id: number) => Promise<void>
  markAllRead: () => Promise<void>
  dismiss: (id: number) => Promise<void>
}

const NO_NOTIFICATIONS: NotificationOut[] = []

const NotificationsContext = createContext<NotificationsContextValue>({
  notifications: NO_NOTIFICATIONS,
  unreadCount: 0,
  loading: false,
  refresh: () => {},
  markRead: async () => {},
  markAllRead: async () => {},
  dismiss: async () => {},
})

export function NotificationsProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const list = useNotificationList()
  useNotificationChangePoll({ enabled: !list.isPending })

  const notifications = list.data ?? NO_NOTIFICATIONS
  // Derived from the list rather than taken from the poll, so the badge can never disagree with the dropdown under it.
  const unreadCount = useMemo(() => unreadCountOf(notifications), [notifications])

  // Invalidating cancels a list request still in flight, so a response that predates the mutation can no longer overwrite the one that follows it.
  const refresh = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.notifications, exact: true })
  }, [queryClient])

  const markRead = useCallback(async (id: number) => {
    await apiMarkRead(id)
    refresh()
  }, [refresh])

  const markAllRead = useCallback(async () => {
    await apiMarkAllRead()
    refresh()
  }, [refresh])

  const dismiss = useCallback(async (id: number) => {
    await apiDismiss(id)
    refresh()
  }, [refresh])

  const loading = list.isFetching
  const value = useMemo(
    () => ({ notifications, unreadCount, loading, refresh, markRead, markAllRead, dismiss }),
    [notifications, unreadCount, loading, refresh, markRead, markAllRead, dismiss],
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
