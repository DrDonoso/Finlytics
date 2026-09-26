import { useState } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import type { MortgageSimulation, PrepaymentMode } from '../api/types'
import { simulateMortgagePrepayment, createMortgagePrepayment, formatEur } from '../api/client'
import { errorMessage } from '../api/errors'
import { IconAlert, IconClose } from './icons'
import DatePicker from './DatePicker'
import { IS_DEMO } from '../demo/config'
import { useT } from '../i18n'
import { Private } from './Money'

interface Props {
  mortgageId: number
  onClose: () => void
  onApplied: () => void
}

function today(): string {
  return new Date().toISOString().slice(0, 10)
}

function num(value: string): number {
  const parsed = Number(value.replace(',', '.'))
  return Number.isFinite(parsed) ? parsed : 0
}

/** Merge both balance curves into a single series keyed by date, for one chart. */
function mergeCurves(sim: MortgageSimulation) {
  const map = new Map<string, { date: string; before?: number; after?: number }>()
  for (const p of sim.balance_before) {
    map.set(p.date, { date: p.date, before: p.balance })
  }
  for (const p of sim.balance_after) {
    const entry = map.get(p.date) ?? { date: p.date }
    entry.after = p.balance
    map.set(p.date, entry)
  }
  return [...map.values()].sort((a, b) => a.date.localeCompare(b.date))
}

export default function MortgagePrepaymentSimulator({ mortgageId, onClose, onApplied }: Props) {
  const { t } = useT()
  const [amount, setAmount] = useState('')
  const [date, setDate] = useState(today())
  const [mode, setMode] = useState<PrepaymentMode>('reduce_term')
  const [fee, setFee] = useState('0')
  const [altReturn, setAltReturn] = useState('')
  const [result, setResult] = useState<MortgageSimulation | null>(null)
  const [loading, setLoading] = useState(false)
  const [applying, setApplying] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const canRun = num(amount) > 0 && date !== ''

  async function run() {
    setLoading(true)
    setError(null)
    try {
      const sim = await simulateMortgagePrepayment(mortgageId, {
        amount: num(amount),
        payment_date: date,
        mode,
        fee: num(fee),
        alt_return_pct: altReturn.trim() === '' ? null : num(altReturn),
      })
      setResult(sim)
    } catch (e) {
      setError(errorMessage(e, t))
    }
    setLoading(false)
  }

  async function apply() {
    setApplying(true)
    setError(null)
    try {
      await createMortgagePrepayment(mortgageId, {
        amount: num(amount),
        payment_date: date,
        mode,
        fee: num(fee),
      })
      onApplied()
    } catch (e) {
      setError(errorMessage(e, t))
      setApplying(false)
    }
  }

  const curves = result ? mergeCurves(result) : []

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal modal-wide" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <span className="modal-title">{t.mortgageSimulatorTitle}</span>
          <button className="modal-close" onClick={onClose} type="button" aria-label={t.mortgageFormCancel}><IconClose size={15} /></button>
        </div>

        <div className="modal-body">
          <p className="form-hint">{t.mortgageSimulatorIntro}</p>

          <div className="mortgage-form__grid">
            <div className="form-group">
              <label htmlFor="sim-amount">{t.mortgageSimAmount}</label>
              <input id="sim-amount" className="form-input" inputMode="decimal" value={amount} onChange={e => setAmount(e.target.value)} />
            </div>
            <div className="form-group">
              <label htmlFor="sim-date">{t.mortgageSimDate}</label>
              <DatePicker value={date} onChange={setDate} ariaLabel={t.mortgageSimDate} />
            </div>
            <div className="form-group">
              <label htmlFor="sim-fee">{t.mortgageSimFee}</label>
              <input id="sim-fee" className="form-input" inputMode="decimal" value={fee} onChange={e => setFee(e.target.value)} />
            </div>
            <div className="form-group">
              <label htmlFor="sim-alt">{t.mortgageSimAltReturn}</label>
              <input id="sim-alt" className="form-input" inputMode="decimal" placeholder="4" value={altReturn} onChange={e => setAltReturn(e.target.value)} />
              <span className="form-hint">{t.mortgageSimAltReturnInfo}</span>
            </div>
          </div>

          <div className="form-group">
            <label>{t.mortgageSimMode}</label>
            <div className="theme-segmented">
              <button
                type="button"
                className={`theme-seg-btn${mode === 'reduce_term' ? ' active' : ''}`}
                onClick={() => setMode('reduce_term')}
                aria-pressed={mode === 'reduce_term'}
              >{t.mortgageModeReduceTerm}</button>
              <button
                type="button"
                className={`theme-seg-btn${mode === 'reduce_payment' ? ' active' : ''}`}
                onClick={() => setMode('reduce_payment')}
                aria-pressed={mode === 'reduce_payment'}
              >{t.mortgageModeReducePayment}</button>
            </div>
          </div>

          <button type="button" className="btn-primary" onClick={run} disabled={!canRun || loading}>
            {loading ? t.loading : t.mortgageSimRun}
          </button>

          {error && <div className="state-box error"><IconAlert size={26} className="icon" /><span>{error}</span></div>}

          {result && (
            <>
              <div className="mortgage-sim__headline">
                <div className="mortgage-sim__headline-item">
                  <span className="mortgage-sim__key">{t.mortgageSimInterestSaved}</span>
                  <span className="mortgage-sim__value inv-kpi-card__value--pos private">{formatEur(result.interest_saved)}</span>
                </div>
                <div className="mortgage-sim__headline-item">
                  <span className="mortgage-sim__key">{t.mortgageSimMonthsSaved}</span>
                  <span className="mortgage-sim__value">{result.months_saved} {t.mortgageMonthsShort}</span>
                </div>
                <div className="mortgage-sim__headline-item">
                  <span className="mortgage-sim__key">{t.mortgageSimImpliedReturn}</span>
                  <span className="mortgage-sim__value">
                    {result.implied_annual_return == null ? '—' : `${result.implied_annual_return.toFixed(2)} %`}
                  </span>
                </div>
              </div>

              <table className="cat-table mortgage-sim__table">
                <thead>
                  <tr>
                    <th className="cat-th-name" />
                    <th className="cat-th-num">{t.mortgageSimBefore}</th>
                    <th className="cat-th-num">{t.mortgageSimAfter}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="cat-row">
                    <td className="cat-td-name">{t.mortgageKpiPayment}</td>
                    <td className="cat-td-num private">{formatEur(result.before.monthly_payment)}</td>
                    <td className="cat-td-num private">{formatEur(result.after.monthly_payment)}</td>
                  </tr>
                  <tr className="cat-row">
                    <td className="cat-td-name">{t.mortgageKpiEndDate}</td>
                    <td className="cat-td-num">{result.before.end_date ?? '—'}</td>
                    <td className="cat-td-num">{result.after.end_date ?? '—'}</td>
                  </tr>
                  <tr className="cat-row">
                    <td className="cat-td-name">{t.mortgageKpiTotalInterest}</td>
                    <td className="cat-td-num private">{formatEur(result.before.total_interest)}</td>
                    <td className="cat-td-num private">{formatEur(result.after.total_interest)}</td>
                  </tr>
                </tbody>
              </table>

              {result.alternative_gain != null && (
                <div className={`mortgage-sim__verdict${result.worth_it ? ' positive' : ' negative'}`}>
                  <strong>{result.worth_it ? t.mortgageSimWorthIt : t.mortgageSimNotWorthIt}</strong>
                  <span>
                    {t.mortgageSimNetSaving}: <Private>{formatEur(result.net_saving)}</Private> · {t.mortgageSimAlternative}: <Private>{formatEur(result.alternative_gain)}</Private>
                  </span>
                </div>
              )}

              <div className="mortgage-sim__chart">
                <ResponsiveContainer width="100%" height={220}>
                  <LineChart data={curves}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={40} />
                    <YAxis tick={{ fontSize: 11 }} width={70} tickFormatter={v => `${Math.round(v / 1000)}k`} />
                    <Tooltip
                      contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }}
                      formatter={value => formatEur(Number(value))}
                    />
                    <Legend />
                    <Line type="monotone" dataKey="before" name={t.mortgageSimBefore} stroke="#94a3b8" dot={false} strokeWidth={2} />
                    <Line type="monotone" dataKey="after" name={t.mortgageSimAfter} stroke="var(--primary)" dot={false} strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </>
          )}
        </div>

        <div className="modal-footer">
          <button type="button" className="btn-secondary" onClick={onClose} disabled={applying}>
            {t.mortgageFormCancel}
          </button>
          {/* Simulating is read-only, but recording the prepayment is a write the
              demo does not accept. */}
          {!IS_DEMO && (
            <button type="button" className="btn-primary" onClick={apply} disabled={!result || applying}>
              {t.mortgageSimApply}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
