import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { deleteMortgage, deleteMortgagePrepayment, formatEur } from '../api/client'
import { errorMessage } from '../api/errors'
import {
  queryKeys, useAccounts, useCategories, useMortgage, useMortgageCharts,
  useMortgageOverview, useMortgageReconciliation, useMortgageSchedule, useMortgages,
} from '../api/queries'
import { MortgageBalanceChart, MortgageCompositionChart } from '../components/MortgageCharts'
import MortgageFormModal from '../components/MortgageFormModal'
import MortgagePrepaymentSimulator from '../components/MortgagePrepaymentSimulator'
import MortgageScheduleTable from '../components/MortgageScheduleTable'
import { IconAlert, IconBuilding, IconInfo, IconLoading, IconTrash } from '../components/icons'
import { IS_DEMO } from '../demo/config'
import { formatDate, useT } from '../i18n'
import type { Dict } from '../i18n'

const RATE_LABEL: Record<string, keyof Dict> = {
  fixed: 'mortgageRateFixed',
  variable: 'mortgageRateVariable',
  mixed: 'mortgageRateMixed',
}

/** Deviation above this share of the instalment is worth flagging. */
const DEVIATION_TOLERANCE_PCT = 1

function InfoTip({ text }: { text: string }) {
  return <IconInfo size={13} className="inv-info-tip" title={text} />
}

export default function MortgagePage() {
  const { t, lang } = useT()
  const queryClient = useQueryClient()

  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [showSimulator, setShowSimulator] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const accounts = useAccounts()
  const categories = useCategories()
  const list = useMortgages()

  // Fall back to the first mortgage until the user picks one explicitly.
  const activeId = selectedId ?? list.data?.[0]?.id ?? null

  const mortgage = useMortgage(activeId)
  const overview = useMortgageOverview(activeId)
  const schedule = useMortgageSchedule(activeId, 'year')
  const charts = useMortgageCharts(activeId)
  const reconciliation = useMortgageReconciliation(activeId)

  /** Every mortgage key is prefixed with 'mortgages', so one invalidation covers all. */
  function refresh() {
    void queryClient.invalidateQueries({ queryKey: queryKeys.mortgages })
  }

  async function handleDelete() {
    if (activeId == null || !window.confirm(t.mortgageDeleteConfirm)) return
    try {
      await deleteMortgage(activeId)
      setSelectedId(null)
      refresh()
    } catch (err) {
      setActionError(errorMessage(err, t))
    }
  }

  async function handleDeletePrepayment(prepaymentId: number) {
    if (activeId == null || !window.confirm(t.mortgagePrepaymentDeleteConfirm)) return
    try {
      await deleteMortgagePrepayment(activeId, prepaymentId)
      refresh()
    } catch (err) {
      setActionError(errorMessage(err, t))
    }
  }

  function closeForm(nextId: number) {
    setShowForm(false)
    setSelectedId(nextId)
    refresh()
  }

  // ── Empty state ─────────────────────────────────────────────────────────
  if (list.isSuccess && list.data.length === 0) {
    return (
      <main className="dashboard">
        <div className="investments-header">
          <h1 className="investments-page-title">{t.mortgageTitle}</h1>
        </div>
        <div className="card">
          <div className="investments-empty">
            <IconBuilding size={40} className="investments-empty__icon" />
            <p className="investments-empty__text">{t.mortgageEmptyText}</p>
            <button className="btn-primary" onClick={() => setShowForm(true)}>
              {t.mortgageAddBtn}
            </button>
          </div>
        </div>
        {showForm && (
          <MortgageFormModal
            accounts={accounts.data ?? []}
            categories={categories.data ?? []}
            onClose={() => setShowForm(false)}
            onSaved={m => closeForm(m.id)}
          />
        )}
      </main>
    )
  }

  const data = overview.data
  const loading = list.isPending || overview.isPending
  const loadError = list.error ?? overview.error

  return (
    <main className="dashboard">
      <div className="investments-header mortgage-header">
        <div>
          <h1 className="investments-page-title">{data?.name ?? t.mortgageTitle}</h1>
          {data && (
            <span className="mortgage-header__meta">
              {data.lender ? `${data.lender} · ` : ''}
              {t[RATE_LABEL[data.rate_type]] as string}
              {data.current_rate > 0 && ` · ${data.current_rate.toFixed(3)} %`}
            </span>
          )}
        </div>
        <div className="dashboard-header-actions">
          {(list.data?.length ?? 0) > 1 && (
            <select
              className="form-input"
              value={activeId ?? ''}
              onChange={e => setSelectedId(Number(e.target.value))}
              aria-label={t.mortgageTitle}
            >
              {list.data?.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
          )}
          {/* The demo serves the mortgage read-only: the simulator works (it
              computes without persisting), but editing and deleting do not. */}
          {!IS_DEMO && (
            <button className="btn-secondary" onClick={() => setShowForm(true)} disabled={!mortgage.data}>
              {t.mortgageEditBtn}
            </button>
          )}
          <button className="btn-primary" onClick={() => setShowSimulator(true)} disabled={!mortgage.data}>
            {t.mortgagePrepaymentAdd}
          </button>
        </div>
      </div>

      {(loadError || actionError) && (
        <div className="state-box error">
          <IconAlert size={26} className="icon" />
          <span>{actionError ?? errorMessage(loadError, t)}</span>
        </div>
      )}
      {loading && (
        <div className="state-box">
          <IconLoading size={26} className="icon" />
          <span>{t.loading}</span>
        </div>
      )}

      {data && (
        <>
          {/* ── KPI strip ─────────────────────────────────────────────── */}
          <div className="inv-kpi-strip">
            <div className="inv-kpi-card">
              <div className="inv-kpi-card__label">
                {t.mortgageKpiOutstanding} <InfoTip text={t.mortgageKpiOutstandingInfo} />
              </div>
              <div className="inv-kpi-card__value">{formatEur(data.outstanding_balance)}</div>
              <div className="inv-kpi-card__sub">
                {data.months_remaining} {t.mortgageMonthsShort} {t.mortgageRemainingSuffix}
              </div>
            </div>

            <div className="inv-kpi-card">
              <div className="inv-kpi-card__label">{t.mortgageKpiAmortized}</div>
              <div className="inv-kpi-card__value">{formatEur(data.amortized_principal)}</div>
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
              <div className="inv-kpi-card__sub">{data.progress_pct.toFixed(1)} %</div>
            </div>

            <div className="inv-kpi-card">
              <div className="inv-kpi-card__label">{t.mortgageKpiPayment}</div>
              <div className="inv-kpi-card__value">{formatEur(data.current_payment)}</div>
              <div className="inv-kpi-card__sub">
                {data.next_payment_date ? formatDate(data.next_payment_date, lang) : '—'}
              </div>
            </div>

            <div className="inv-kpi-card">
              <div className="inv-kpi-card__label">{t.mortgageKpiInterestPaid}</div>
              <div className="inv-kpi-card__value inv-kpi-card__value--neg">
                {formatEur(data.interest_paid)}
              </div>
              <div className="inv-kpi-card__sub">
                {t.mortgageKpiInterestRemaining}: {formatEur(data.interest_remaining)}
              </div>
            </div>

            <div className="inv-kpi-card">
              <div className="inv-kpi-card__label">{t.mortgageKpiEndDate}</div>
              <div className="inv-kpi-card__value">
                {data.end_date ? formatDate(data.end_date, lang) : '—'}
              </div>
              {data.months_saved > 0 && (
                <div className="inv-kpi-card__sub inv-kpi-card__value--pos">
                  −{data.months_saved} {t.mortgageMonthsShort}
                </div>
              )}
            </div>

            {data.ltv_pct != null && (
              <div className="inv-kpi-card">
                <div className="inv-kpi-card__label">
                  {t.mortgageKpiLtv} <InfoTip text={t.mortgageKpiLtvInfo} />
                </div>
                <div className="inv-kpi-card__value">{data.ltv_pct.toFixed(1)} %</div>
                <div className="inv-kpi-card__sub">{formatEur(data.property_value ?? 0)}</div>
              </div>
            )}
          </div>

          {data.has_projection && (
            <p className="mortgage-projection-note">
              <IconInfo size={13} /> {t.mortgageProjectionNote}
            </p>
          )}

          {/* ── Charts ────────────────────────────────────────────────── */}
          <div className="inv-donuts-row">
            <div className="card">
              <h3 className="card-title">
                {t.mortgageChartBalance} <InfoTip text={t.mortgageChartBalanceInfo} />
              </h3>
              <MortgageBalanceChart points={charts.data?.balance ?? []} />
            </div>
            <div className="card">
              <h3 className="card-title">
                {t.mortgageChartComposition} <InfoTip text={t.mortgageChartCompositionInfo} />
              </h3>
              <MortgageCompositionChart years={charts.data?.composition ?? []} />
            </div>
          </div>

          {/* ── Prepayments ───────────────────────────────────────────── */}
          <div className="card">
            <h3 className="card-title">{t.mortgagePrepaymentsTitle}</h3>
            {mortgage.data && mortgage.data.prepayments.length > 0 ? (
              <div className="cat-table-wrap">
                <table className="cat-table">
                  <thead>
                    <tr>
                      <th className="cat-th-name">{t.mortgageColDate}</th>
                      <th className="cat-th-num">{t.mortgageColPrepayment}</th>
                      <th className="cat-th-name">{t.mortgageColMode}</th>
                      <th className="cat-th-num">{t.mortgageColFee}</th>
                      <th className="cat-th-num" />
                    </tr>
                  </thead>
                  <tbody>
                    {mortgage.data.prepayments.map(p => (
                      <tr key={p.id} className="cat-row">
                        <td className="cat-td-name">{formatDate(p.payment_date, lang)}</td>
                        <td className="cat-td-num">{formatEur(p.amount)}</td>
                        <td className="cat-td-name">
                          {p.mode === 'reduce_term' ? t.mortgageModeReduceTerm : t.mortgageModeReducePayment}
                        </td>
                        <td className="cat-td-num">{p.fee > 0 ? formatEur(p.fee) : '—'}</td>
                        <td className="cat-td-num">
                          {!IS_DEMO && (
                            <button
                              type="button"
                              className="btn-row-delete"
                              onClick={() => handleDeletePrepayment(p.id)}
                              aria-label={t.mortgagePrepaymentDelete}
                            >
                              <IconTrash size={14} />
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {data.interest_saved > 0 && (
                  <p className="mortgage-saving-note inv-kpi-card__value--pos">
                    {t.mortgageKpiSavedByPrepayments}: {formatEur(data.interest_saved)}
                  </p>
                )}
              </div>
            ) : (
              <div className="state-box"><span>{t.mortgagePrepaymentsEmpty}</span></div>
            )}
          </div>

          {/* ── Schedule ──────────────────────────────────────────────── */}
          <div className="card">
            <h3 className="card-title">{t.mortgageScheduleTitle}</h3>
            <MortgageScheduleTable
              years={schedule.data?.years ?? []}
              linked={schedule.data?.linked ?? false}
              chargesFrom={schedule.data?.charges_from ?? null}
              loading={schedule.isPending}
              error={schedule.error ? errorMessage(schedule.error, t) : null}
            />
          </div>

          {/* ── Reconciliation (only when linked) ─────────────────────── */}
          <div className="card">
            <h3 className="card-title">{t.mortgageReconTitle}</h3>
            {!reconciliation.data?.linked ? (
              <div className="state-box"><span>{t.mortgageReconNotLinked}</span></div>
            ) : reconciliation.data.rows.length === 0 ? (
              <div className="state-box"><span>{t.noDataPeriod}</span></div>
            ) : (
              <>
                <p className="form-hint">{t.mortgageReconIntro}</p>
                <div className="cat-table-wrap">
                  <table className="cat-table">
                    <thead>
                      <tr>
                        <th className="cat-th-name">{t.mortgageReconColPeriod}</th>
                        <th className="cat-th-num">{t.mortgageReconColExpected}</th>
                        <th className="cat-th-num">{t.mortgageReconColActual}</th>
                        <th className="cat-th-num">{t.mortgageReconColDeviation}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...reconciliation.data.rows].reverse().map(row => {
                        const off = row.deviation_pct != null
                          && Math.abs(row.deviation_pct) > DEVIATION_TOLERANCE_PCT
                        return (
                          <tr key={row.period} className="cat-row">
                            <td className="cat-td-name">{formatDate(row.period, lang)}</td>
                            <td className="cat-td-num">{formatEur(row.expected)}</td>
                            <td className="cat-td-num">
                              {row.actual == null ? t.mortgageReconMissing : formatEur(row.actual)}
                            </td>
                            <td className={`cat-td-num${off ? ' inv-kpi-card__value--neg' : ''}`}>
                              {row.deviation == null
                                ? '—'
                                : `${row.deviation >= 0 ? '+' : ''}${formatEur(row.deviation)}`}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>

          <div className="mortgage-danger-zone">
            {!IS_DEMO && (
              <button type="button" className="btn-row-delete" onClick={handleDelete}>
                {t.mortgageDeleteBtn}
              </button>
            )}
          </div>
        </>
      )}

      {showForm && (
        <MortgageFormModal
          mortgage={mortgage.data ?? null}
          accounts={accounts.data ?? []}
          categories={categories.data ?? []}
          onClose={() => setShowForm(false)}
          onSaved={m => closeForm(m.id)}
        />
      )}

      {showSimulator && activeId != null && (
        <MortgagePrepaymentSimulator
          mortgageId={activeId}
          onClose={() => setShowSimulator(false)}
          onApplied={() => { setShowSimulator(false); refresh() }}
        />
      )}
    </main>
  )
}
