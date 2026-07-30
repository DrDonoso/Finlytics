/** Demo notice shown on the login screen.
 *
 * Lives here and nowhere else on purpose: the point is to set expectations once,
 * before the visitor is inside, and then stay out of the way. A persistent
 * banner on every page would just be noise covering the UI being demoed.
 */

import { DEMO_PASSWORD, DEMO_USERNAME } from './config'
import { useT } from '../i18n'

export default function DemoLoginNotice() {
  const { t } = useT()
  return (
    <div className="demo-notice" role="note">
      <p className="demo-notice-text">
        <strong>{t.demoNoticeTitle}</strong> {t.demoNoticeBody}
      </p>
      <p className="demo-notice-creds">
        {t.demoNoticeCredentials}{' '}
        <code>{DEMO_USERNAME}</code> / <code>{DEMO_PASSWORD}</code>
      </p>
    </div>
  )
}
