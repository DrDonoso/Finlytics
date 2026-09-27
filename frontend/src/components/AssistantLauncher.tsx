/**
 * Floating button that opens the assistant.
 *
 * Hidden entirely when the backend reports the assistant as unavailable: a
 * button whose only outcome is a 503 is worse than no button, and the status
 * endpoint exists precisely so this decision can be made before the first click.
 */
import { useAssistantStatus } from '../api/queries'
import { useAssistant } from '../contexts/AssistantContext'
import { useT } from '../i18n'
import { IconSparkles } from './icons'

export default function AssistantLauncher({ variant = 'fab' }: { variant?: 'fab' | 'toolbar' }) {
  const { t } = useT()
  const { open, togglePanel } = useAssistant()
  const statusQuery = useAssistantStatus()

  if (statusQuery.data?.enabled !== true) return null

  const classes = ['assistant-launcher']
  if (variant === 'toolbar') classes.push('assistant-launcher--toolbar')
  if (open) classes.push('active')

  return (
    <button
      type="button"
      className={classes.join(' ')}
      onClick={togglePanel}
      aria-label={open ? t.assistantClose : t.assistantOpen}
      aria-expanded={open}
      title={open ? t.assistantClose : t.assistantOpen}
    >
      <IconSparkles size={variant === 'toolbar' ? 18 : 20} />
    </button>
  )
}
