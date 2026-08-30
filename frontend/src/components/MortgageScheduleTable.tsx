import { useState } from 'react'
import type { MortgageScheduleYear } from '../api/types'
import { formatEur } from '../api/client'
import { IconAlert, IconCheck, IconChevronDown, IconLoading } from './icons'
import { Private } from './Money'
import { usePrivacy } from '../contexts/PrivacyContext'
import { useT, formatDate } from '../i18n'

interface Props {
  years: MortgageScheduleYear[]
  /** Whether an account/category is linked: without one a past row can only
   *  be reported as elapsed, never as confirmed paid. */
  linked: boolean
  /** Oldest charge on record. Years ending before it are outside what the
   *  ledger covers, so no payment count is claimed for them. */
  chargesFrom?: string | null
  loading: boolean
  error: string | null
}

/** Amortization table, collapsed to one row per year and expandable to months. */
export default function MortgageScheduleTable({ years, linked, chargesFrom, loading, error }: Props) {
  const { t, lang } = useT()
  const { hidden: hideAmounts } = usePrivacy()
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  const coverageYear = chargesFrom ? Number(chargesFrom.slice(0, 4)) : null

  function toggle(year: number) {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(year)) next.delete(year)
      else next.add(year)
      return next
    })
  }

  if (loading) {
    return <div className="state-box"><IconLoading size={26} className="icon" /><span>{t.loading}</span></div>
  }
  if (error) {
    return <div className="state-box error"><IconAlert size={26} className="icon" /><span>{error}</span></div>
  }
  if (years.length === 0) {
    return <div className="state-box"><span>{t.noDataPeriod}</span></div>
  }

  const totals = years.reduce(
    (acc, y) => ({
      payment: acc.payment + y.payment,
      interest: acc.interest + y.interest,
      principal: acc.principal + y.principal,
      prepayment: acc.prepayment + y.prepayment,
    }),
    { payment: 0, interest: 0, principal: 0, prepayment: 0 },
  )

  return (
    <div className="cat-table-wrap mortgage-schedule">
      <table className="cat-table">
        <thead>
          <tr>
            <th className="cat-th-name">{t.mortgageColYear}</th>
            <th className="cat-th-num">{t.mortgageColPayment}</th>
            <th className="cat-th-num">{t.mortgageColInterest}</th>
            <th className="cat-th-num">{t.mortgageColPrincipal}</th>
            <th className="cat-th-num">{t.mortgageColPrepayment}</th>
            <th className="cat-th-num">{t.mortgageColBalance}</th>
          </tr>
        </thead>
        <tbody>
          {years.map(year => {
            const open = expanded.has(year.year)
            return [
              <tr
                key={year.year}
                className="cat-row mortgage-schedule__year"
                onClick={() => toggle(year.year)}
                role="button"
                tabIndex={0}
                aria-expanded={open}
                onKeyDown={e => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    toggle(year.year)
                  }
                }}
              >
                <td className="cat-td-name">
                  <IconChevronDown size={14} className={`sidebar-arrow${open ? ' open' : ''}`} /> {year.year}
                  {year.months_elapsed > 0 && (!linked || coverageYear == null || year.year >= coverageYear) && (
                    <span className="mortgage-schedule__year-progress">
                      {linked
                        ? t.mortgageSchedulePaidCount(year.months_paid, year.months_total)
                        : t.mortgageScheduleElapsedCount(year.months_elapsed, year.months_total)}
                    </span>
                  )}
                </td>
                <td className="cat-td-num private">{formatEur(year.payment)}</td>
                <td className="cat-td-num private">{formatEur(year.interest)}</td>
                <td className="cat-td-num private">{formatEur(year.principal)}</td>
                <td className="cat-td-num">{year.prepayment > 0 ? <Private>{formatEur(year.prepayment)}</Private> : '—'}</td>
                <td className="cat-td-num private">{formatEur(year.closing_balance)}</td>
              </tr>,
              ...(open ? year.months.map(row => (
                <tr
                  key={`${year.year}-${row.period_index}`}
                  className={`cat-row mortgage-schedule__month${linked ? ` is-${row.status}` : ''}`}
                >
                  <td className="cat-td-name">
                    <span className="mortgage-schedule__marker">
                      {row.status === 'paid' && (
                        <IconCheck
                          size={13}
                          className="mortgage-schedule__paid"
                          title={row.charged != null && !hideAmounts
                            ? t.mortgageSchedulePaidOn(formatEur(row.charged))
                            : t.mortgageSchedulePaid}
                        />
                      )}
                    </span>
                    {formatDate(row.date, lang)}
                    {row.projected && <span className="mortgage-schedule__projected" title={t.mortgageProjectionNote}>~</span>}
                    <span className="mortgage-schedule__rate">{row.annual_rate.toFixed(3)} %</span>
                  </td>
                  <td className="cat-td-num private">{formatEur(row.payment)}</td>
                  <td className="cat-td-num private">{formatEur(row.interest)}</td>
                  <td className="cat-td-num private">{formatEur(row.principal)}</td>
                  <td className="cat-td-num">{row.prepayment > 0 ? <Private>{formatEur(row.prepayment)}</Private> : '—'}</td>
                  <td className="cat-td-num private">{formatEur(row.closing_balance)}</td>
                </tr>
              )) : []),
            ]
          })}
        </tbody>
        <tfoot>
          <tr className="mortgage-schedule__total">
            <td className="cat-td-name">{t.mortgageScheduleTotal}</td>
            <td className="cat-td-num private">{formatEur(totals.payment)}</td>
            <td className="cat-td-num private">{formatEur(totals.interest)}</td>
            <td className="cat-td-num private">{formatEur(totals.principal)}</td>
            <td className="cat-td-num private">{formatEur(totals.prepayment)}</td>
            <td className="cat-td-num" />
          </tr>
        </tfoot>
      </table>
    </div>
  )
}
