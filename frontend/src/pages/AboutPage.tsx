import { useAppVersion } from '../api/queries'
import { useT } from '../i18n'

const REPO = 'https://github.com/DrDonoso/Finlytics'

export default function AboutPage() {
  const { t } = useT()
  const versionQuery = useAppVersion()
  const appVersion = versionQuery.data ?? null

  const imageTag = appVersion?.image_tag
  const displayVersion = imageTag ?? appVersion?.version ?? __APP_VERSION__
  const isLocal = appVersion != null && !imageTag

  return (
    <div className="card settings-card">
      <h2 className="settings-section-title">{t.aboutTitle}</h2>

      <div className="about-list">
        <div className="about-row">
          <span className="about-label">{t.aboutVersion}</span>
          <span className="about-value">
            {displayVersion}{isLocal && <span className="about-local-hint"> (local)</span>}
          </span>
        </div>

        {appVersion?.built_at && (
          <div className="about-row">
            <span className="about-label">{t.aboutBuiltAt}</span>
            <span className="about-value">{appVersion.built_at}</span>
          </div>
        )}

        <div className="about-row">
          <span className="about-label">{t.aboutRepository}</span>
          <a href={REPO} target="_blank" rel="noopener noreferrer" className="about-link">
            github.com/DrDonoso/Finlytics
          </a>
        </div>

        <div className="about-row">
          <span className="about-label">{t.aboutReportIssue}</span>
          <a href={`${REPO}/issues`} target="_blank" rel="noopener noreferrer" className="about-link">
            GitHub Issues
          </a>
        </div>

        <div className="about-row">
          <span className="about-label">{t.aboutChangelog}</span>
          <a href={`${REPO}/blob/main/CHANGELOG.md`} target="_blank" rel="noopener noreferrer" className="about-link">
            CHANGELOG.md
          </a>
        </div>

        <div className="about-row">
          <span className="about-label">{t.aboutLicense}</span>
          <a
            href="https://github.com/DrDonoso/Finlytics/blob/main/LICENSE"
            target="_blank"
            rel="noopener noreferrer"
            className="about-link"
          >
            MIT
          </a>
        </div>
      </div>
    </div>
  )
}
