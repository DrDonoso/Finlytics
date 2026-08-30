import { useT } from '../i18n'
import { usePrivacy } from '../contexts/PrivacyContext'
import { IconEye, IconEyeOff } from './icons'

export default function PrivacyToggle() {
  const { t } = useT()
  const { hidden, toggle } = usePrivacy()
  const label = hidden ? t.privacyShow : t.privacyHide

  return (
    <button
      type="button"
      className={`privacy-btn${hidden ? ' active' : ''}`}
      onClick={toggle}
      aria-pressed={hidden}
      aria-label={label}
      title={`${label} (Alt+Shift+H)`}
    >
      {hidden ? <IconEyeOff size={18} /> : <IconEye size={18} />}
    </button>
  )
}
