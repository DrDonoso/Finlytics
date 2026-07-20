import { useState, useEffect, useRef } from 'react'
import type { CSSProperties } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate } from 'react-router-dom'
import type { NotificationOut } from '../api/types'
import { useNotifications } from '../contexts/NotificationsContext'
import { useT } from '../i18n'
import type { Dict } from '../i18n'

// ─── Relative-time helper ─────────────────────────────────────────────────────

function relativeTime(isoStr: string, t: Dict): string {
  try {
    const diffMs = Date.now() - new Date(isoStr).getTime()
    const diffMin = Math.floor(diffMs / 60_000)
    if (diffMin < 1) return t.notifTimeJustNow
    if (diffMin < 60) return t.notifTimeMinutes(diffMin)
    const diffHours = Math.floor(diffMs / 3_600_000)
    if (diffHours < 24) return t.notifTimeHours(diffHours)
    const diffDays = Math.floor(diffMs / 86_400_000)
    if (diffDays < 7) return t.notifTimeDays(diffDays)
    return t.notifTimeWeeks(Math.floor(diffDays / 7))
  } catch {
    return ''
  }
}

// ─── Body resolver ────────────────────────────────────────────────────────────

function resolveBody(notif: NotificationOut, t: Dict): string | null {
  if (!notif.body_key) return null
  const a = notif.body_args ?? {}
  switch (notif.body_key) {
    case 'notif.statement_missing':
      return t.notifBodyStatementMissing({
        month: String(a.month ?? ''),
        account: String(a.account ?? ''),
      })
    case 'notif.espp_overdue':
      return t.notifBodyEsppOverdue({ period: String(a.period ?? '') })
    default:
      return null
  }
}

// ─── Title resolver ───────────────────────────────────────────────────────────

function resolveTitle(notif: NotificationOut, t: Dict): string {
  const a = notif.title_args
  switch (notif.title_key) {
    case 'notif.statement_missing':
      return t.notifTitleStatementMissing({
        month: a.month ?? '',
        account: a.account ?? '',
      })
    case 'notif.espp_overdue':
      return t.notifTitleEsppOverdue({ period: a.period ?? '' })
    default:
      return notif.title_key.split('.').pop() ?? notif.title_key
  }
}

// ─── Notification Item ────────────────────────────────────────────────────────

interface NotifItemProps {
  notif: NotificationOut
  onDismiss: (id: number) => void
  onAction: (id: number, link: string) => void
  onMarkRead: (id: number) => void
  t: Dict
}

function NotifItem({ notif, onDismiss, onAction, onMarkRead, t }: NotifItemProps) {
  const isUnread = !notif.read_at
  const isWarning = notif.severity === 'warning'
  const body = resolveBody(notif, t)

  return (
    <div
      className={[
        'notif-item',
        isWarning ? 'notif-item--warning' : 'notif-item--info',
        isUnread ? 'notif-item--unread' : '',
      ].filter(Boolean).join(' ')}
    >
      {isUnread && (
        <button
          type="button"
          className="notif-item__dot"
          aria-label={t.notifMarkRead}
          onClick={() => onMarkRead(notif.id)}
        />
      )}
      <span className="notif-item__icon" aria-hidden="true">
        {isWarning ? '⚠' : 'ℹ'}
      </span>
      <div className="notif-item__body">
        <div className={`notif-item__title ${isUnread ? 'notif-item__title--unread' : 'notif-item__title--read'}`}>
          {resolveTitle(notif, t)}
        </div>
        {body && (
          <div className="notif-item__body-text">{body}</div>
        )}
        <div className="notif-item__time">{relativeTime(notif.created_at, t)}</div>
        {notif.action_link && (
          <button
            type="button"
            className="notif-item__action"
            onClick={() => onAction(notif.id, notif.action_link!)}
          >
            {t.notifActionView}
          </button>
        )}
      </div>
      <button
        type="button"
        className="notif-item__dismiss"
        aria-label={t.notifDismiss}
        onClick={() => onDismiss(notif.id)}
        title={t.notifDismiss}
      >
        ✕
      </button>
    </div>
  )
}

// ─── Main Bell Component ──────────────────────────────────────────────────────

export default function NotificationBell() {
  const { t } = useT()
  const { notifications, unreadCount, markRead, markAllRead, dismiss } = useNotifications()
  const navigate = useNavigate()

  const [open, setOpen] = useState(false)
  const [panelPos, setPanelPos] = useState<{ top: number; right: number }>({ top: 0, right: 0 })
  const bellRef = useRef<HTMLButtonElement>(null)

  // Close on Escape
  useEffect(() => {
    if (!open) return
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [open])

  function handleBellClick() {
    if (open) { setOpen(false); return }
    if (bellRef.current) {
      const r = bellRef.current.getBoundingClientRect()
      setPanelPos({ top: r.bottom + 8, right: window.innerWidth - r.right })
    }
    setOpen(true)
  }

  async function handleMarkRead(id: number) {
    await markRead(id)
  }

  async function handleDismiss(id: number) {
    await dismiss(id)
  }

  async function handleAction(id: number, link: string) {
    await markRead(id)
    setOpen(false)
    navigate(link)
  }

  async function handleMarkAllRead() {
    await markAllRead()
  }

  const badgeLabel = unreadCount > 9 ? '9+' : String(unreadCount)

  const panelStyle: CSSProperties = {
    top: panelPos.top,
    right: panelPos.right,
  }

  return (
    <>
      <button
        ref={bellRef}
        type="button"
        className="notif-bell-btn"
        aria-label={t.notifPanelTitle}
        aria-haspopup="true"
        aria-expanded={open}
        onClick={handleBellClick}
      >
        🔔
        {unreadCount > 0 && (
          <span className="notif-badge" aria-hidden="true">{badgeLabel}</span>
        )}
      </button>

      {open && createPortal(
        <>
          <div
            className="notif-backdrop"
            onClick={() => setOpen(false)}
            aria-hidden="true"
          />
          <div
            className="notif-panel"
            style={panelStyle}
            role="dialog"
            aria-label={t.notifPanelTitle}
          >
            <div className="notif-panel__header">
              <span className="notif-panel__title">{t.notifPanelTitle}</span>
              {unreadCount > 0 && (
                <button
                  type="button"
                  className="notif-panel__mark-all"
                  onClick={handleMarkAllRead}
                >
                  {t.notifMarkAllRead}
                </button>
              )}
            </div>

            <div className="notif-panel__list">
              {notifications.length === 0 ? (
                <div className="notif-empty">
                  <span className="notif-empty__icon">🔔</span>
                  <span>{t.notifEmpty}</span>
                </div>
              ) : (
                notifications.map(n => (
                  <NotifItem
                    key={n.id}
                    notif={n}
                    onDismiss={handleDismiss}
                    onAction={handleAction}
                    onMarkRead={handleMarkRead}
                    t={t}
                  />
                ))
              )}
            </div>
          </div>
        </>,
        document.body,
      )}
    </>
  )
}
