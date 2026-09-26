import { useT } from '../i18n'
import { IconLoading } from './icons'

/** Placeholder shown in the content area while a lazily loaded page's code arrives. */
export default function PageLoading() {
  const { t } = useT()
  return (
    <main className="dashboard">
      <div className="card">
        <div className="state-box" role="status">
          <IconLoading size={18} />
          <span>{t.loading}</span>
        </div>
      </div>
    </main>
  )
}
