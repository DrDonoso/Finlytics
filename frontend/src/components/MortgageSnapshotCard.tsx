import { Link } from 'react-router'

import { useMortgageOverview, useMortgages } from '../api/queries'
import { useT, formatDate } from '../i18n'
import CardHeader from './CardHeader'
import { Percent } from './Money'
import { IconChevronRight } from './icons'

/** Dashboard snapshot: outstanding debt, progress and next instalment. */
export default function MortgageSnapshotCard() {
  const { t, lang, formatCurrency, formatPercent } = useT()
  const list = useMortgages()
  const firstId = list.data?.[0]?.id ?? null
  const overview = useMortgageOverview(firstId)

  // Stay invisible until there is something worth showing.
  if (!overview.data) return null
  const data = overview.data

  return (
    <div className="card mortgage-snapshot">
      <CardHeader
        title={t.mortgageCardTitle}
        action={<Link to="/mortgage" className="card-link">{t.mortgageCardViewDetail} <IconChevronRight size={14} /></Link>}
      />
      <div className="mortgage-snapshot__body">
        <div className="mortgage-snapshot__main">
          <span className="mortgage-snapshot__label">{t.mortgageKpiOutstanding}</span>
          <span className="mortgage-snapshot__value private num">{formatCurrency(data.outstanding_balance)}</span>
          <div
            className="mortgage-progress"
            role="progressbar"
            aria-label={t.mortgageKpiAmortized}
            aria-valuenow={data.progress_pct}
            aria-valuetext={formatPercent(data.progress_pct)}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <div
              className="mortgage-progress__fill"
              style={{ width: `${Math.min(data.progress_pct, 100)}%` }}
            />
          </div>
          <span className="mortgage-snapshot__sub">
            <Percent value={data.progress_pct} /> · {data.months_remaining} {t.mortgageMonthsShort} {t.mortgageRemainingSuffix}
          </span>
        </div>
        <div className="mortgage-snapshot__side">
          <div>
            <span className="mortgage-snapshot__label">{t.mortgageKpiPayment}</span>
            <span className="mortgage-snapshot__side-value private num">{formatCurrency(data.current_payment)}</span>
          </div>
          <div>
            <span className="mortgage-snapshot__label">{t.mortgageKpiEndDate}</span>
            <span className="mortgage-snapshot__side-value">
              {data.end_date ? formatDate(data.end_date, lang) : '—'}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
