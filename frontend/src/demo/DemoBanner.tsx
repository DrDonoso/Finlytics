/** Banner shown on every demo page.
 *
 * Makes it unmistakable that the figures are invented and that edits are
 * discarded on reload, so nobody mistakes the demo for a real account.
 */

import { useT } from '../i18n'

export default function DemoBanner() {
  const { t } = useT()
  return (
    <div className="demo-banner" role="status">
      <span className="demo-banner-icon" aria-hidden="true">🧪</span>
      <span className="demo-banner-text">
        <strong>{t.demoBannerTitle}</strong> {t.demoBannerBody}
      </span>
    </div>
  )
}
