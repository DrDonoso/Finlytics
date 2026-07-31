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

export default function AssistantLauncher() {
  const { t } = useT()
  const { open, togglePanel } = useAssistant()
  const statusQuery = useAssistantStatus()

  if (statusQuery.data?.enabled !== true) return null

  return (
    <button
      type="button"
      className={`assistant-launcher${open ? ' active' : ''}`}
      onClick={togglePanel}
      aria-label={open ? t.assistantClose : t.assistantOpen}
      aria-expanded={open}
      title={open ? t.assistantClose : t.assistantOpen}
    >
      <IconSparkles size={20} />
    </button>
  )
}
