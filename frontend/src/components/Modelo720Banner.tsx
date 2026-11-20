import { Link } from 'react-router'
import { useNotifications } from '../contexts/NotificationsContext'
import { IS_DEMO } from '../demo/config'
import { useT } from '../i18n'
import Money from './Money'
import { IconAlert, IconClose, IconInfo } from './icons'

/**
 * The yearly Modelo 720 check (the `modelo720` alert) with the value it was based on, which
 * push and Telegram never carry. Dismissing it dismisses the alert, as the bell does.
 */
export default function Modelo720Banner({ showLink = false }: { showLink?: boolean }) {
  const { t } = useT()
  const { notifications, dismiss } = useNotifications()
  const check = notifications.find(n => n.source === 'modelo720')
  if (IS_DEMO || !check) return null

  const exceeds = check.title_key === 'notif.modelo720_exceeds'
  const year = check.title_args.year ?? ''
  const value = check.body_args?.value_eur
  return (
    <div
      className={`espp-reminder-banner modelo720-banner${exceeds ? '' : ' modelo720-banner--info'}`}
      role={exceeds ? 'alert' : 'status'}
    >
      {exceeds ? <IconAlert size={16} /> : <IconInfo size={16} />}
      <div className="modelo720-banner__text">
        <strong>{exceeds ? t.notifTitleModelo720Exceeds({ year }) : t.notifTitleModelo720Below({ year })}</strong>
        {typeof value === 'number' && (
          <span>{t.modelo720Value(year)} <Money value={value} /></span>
        )}
        <span>{exceeds ? t.notifBodyModelo720Exceeds : t.notifBodyModelo720Below}</span>
      </div>
      {showLink && (
        <Link to="/investments/fidelity-espp" className="espp-reminder-banner__link">
          {t.modelo720Action}
        </Link>
      )}
      <button
        type="button"
        className="modelo720-banner__dismiss"
        aria-label={t.notifDismiss}
        title={t.notifDismiss}
        onClick={() => void dismiss(check.id)}
      >
        <IconClose size={14} />
      </button>
    </div>
  )
}
