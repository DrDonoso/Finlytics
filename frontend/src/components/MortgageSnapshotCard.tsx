import { Link } from 'react-router'

import { formatEur } from '../api/client'
import { useMortgageOverview, useMortgages } from '../api/queries'
import { useT, formatDate } from '../i18n'

/** Dashboard snapshot: outstanding debt, progress and next instalment. */
export default function MortgageSnapshotCard() {
  const { t, lang } = useT()
  const list = useMortgages()
  const firstId = list.data?.[0]?.id ?? null
  const overview = useMortgageOverview(firstId)

  // Stay invisible until there is something worth showing.
  if (!overview.data) return null
  const data = overview.data

  return (
    <div className="card mortgage-snapshot">
      <h3 className="card-title">{t.mortgageCardTitle}</h3>
      <div className="mortgage-snapshot__body">
        <div className="mortgage-snapshot__main">
          <span className="mortgage-snapshot__label">{t.mortgageKpiOutstanding}</span>
          <span className="mortgage-snapshot__value">{formatEur(data.outstanding_balance)}</span>
          <div
            className="mortgage-progress"
            role="progressbar"
            aria-valuenow={data.progress_pct}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <div
              className="mortgage-progress__fill"
              style={{ width: `${Math.min(data.progress_pct, 100)}%` }}
            />
          </div>
          <span className="mortgage-snapshot__sub">
            {data.progress_pct.toFixed(1)} % · {data.months_remaining} {t.mortgageMonthsShort} {t.mortgageRemainingSuffix}
          </span>
        </div>
        <div className="mortgage-snapshot__side">
          <div>
            <span className="mortgage-snapshot__label">{t.mortgageKpiPayment}</span>
            <span className="mortgage-snapshot__side-value">{formatEur(data.current_payment)}</span>
          </div>
          <div>
            <span className="mortgage-snapshot__label">{t.mortgageKpiEndDate}</span>
            <span className="mortgage-snapshot__side-value">
              {data.end_date ? formatDate(data.end_date, lang) : '—'}
            </span>
          </div>
        </div>
      </div>
      <Link to="/mortgage" className="inv-provider-card__cta">{t.mortgageCardViewDetail}</Link>
    </div>
  )
}
