import { useState, useMemo } from 'react'
import type { Account, Category, Mortgage, MortgageInput, MortgageRatePeriod, MortgageRateType, MortgageBonus } from '../api/types'
import { createMortgage, updateMortgage, formatEur } from '../api/client'
import { errorMessage } from '../api/errors'
import { useEuriborSeries, useMortgagePaymentCandidates } from '../api/queries'
import { IconAlert, IconClose } from './icons'
import DatePicker from './DatePicker'
import { useT, categoryLabel } from '../i18n'
import { previewSchedule } from '../mortgage/calc'
import { Private } from './Money'

const INDEX_NAME = 'euribor_12m'

interface Props {
  mortgage?: Mortgage | null
  accounts: Account[]
  categories: Category[]
  onClose: () => void
  onSaved: (mortgage: Mortgage) => void
}

/** A bonus plus a stable key: new rows have no id until they are saved. */
type BonusRow = MortgageBonus & { key: string }

let bonusKeySeq = 0
function nextBonusKey(): string {
  bonusKeySeq += 1
  return `bonus-${bonusKeySeq}`
}

interface FormState {
  name: string
  lender: string
  principal: string
  startDate: string
  signatureDate: string
  termYears: string
  termExtraMonths: string
  paymentDay: string
  rateType: MortgageRateType
  fixedRate: string
  spread: string
  reviewMonths: string
  reviewLag: string
  floorRate: string
  capRate: string
  fixedYears: string
  bonuses: BonusRow[]
  linkedAccountId: string
  linkedCategoryId: string
  propertyValue: string
  includeInNetWorth: boolean
  notes: string
}

function num(value: string): number {
  const parsed = Number(value.replace(',', '.'))
  return Number.isFinite(parsed) ? parsed : 0
}

function optionalNum(value: string): number | null {
  return value.trim() === '' ? null : num(value)
}

function initialState(mortgage?: Mortgage | null): FormState {
  const fixed = mortgage?.rate_periods.find(p => p.kind === 'fixed')
  const variable = mortgage?.rate_periods.find(p => p.kind === 'variable')
  return {
    name: mortgage?.name ?? '',
    lender: mortgage?.lender ?? '',
    principal: mortgage ? String(mortgage.initial_principal) : '',
    startDate: mortgage?.start_date ?? '',
    signatureDate: mortgage?.signature_date ?? '',
    termYears: mortgage ? String(Math.floor(mortgage.term_months / 12)) : '30',
    termExtraMonths: mortgage ? String(mortgage.term_months % 12) : '0',
    paymentDay: mortgage ? String(mortgage.payment_day) : '1',
    rateType: mortgage?.rate_type ?? 'fixed',
    fixedRate: fixed?.fixed_rate != null ? String(fixed.fixed_rate) : '',
    spread: variable?.spread != null ? String(variable.spread) : '',
    reviewMonths: variable?.review_months != null ? String(variable.review_months) : '12',
    reviewLag: variable?.review_lag_months != null ? String(variable.review_lag_months) : '2',
    floorRate: variable?.floor_rate != null ? String(variable.floor_rate) : '',
    capRate: variable?.cap_rate != null ? String(variable.cap_rate) : '',
    fixedYears: variable?.start_month ? String(Math.round(variable.start_month / 12)) : '5',
    bonuses: mortgage?.bonuses.map(b => ({ ...b, key: nextBonusKey() })) ?? [],
    linkedAccountId: mortgage?.linked_account_id != null ? String(mortgage.linked_account_id) : '',
    linkedCategoryId: mortgage?.linked_category_id != null ? String(mortgage.linked_category_id) : '',
    propertyValue: mortgage?.property_value != null ? String(mortgage.property_value) : '',
    includeInNetWorth: mortgage?.include_in_net_worth ?? true,
    notes: mortgage?.notes ?? '',
  }
}

export default function MortgageFormModal({ mortgage, accounts, categories, onClose, onSaved }: Props) {
  const { t, lang } = useT()
  const [step, setStep] = useState(1)
  const [form, setForm] = useState<FormState>(() => initialState(mortgage))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Only the variable/mixed paths need the index, so the query stays disabled otherwise.
  const euribor = useEuriborSeries({ enabled: form.rateType !== 'fixed' })
  const latestIndex = euribor.data?.latest ?? 0
  const dynamicEs = useMemo(
    () => Object.fromEntries(categories.filter(c => c.name_es).map(c => [c.name, c.name_es!])),
    [categories],
  )

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm(f => ({ ...f, [key]: value }))
  }

  // Terms are not always a whole number of years: a loan signed mid-month
  // often amortizes over 359 instalments because the first charge only
  // covers interest, and a year-only field cannot express that.
  const termMonths = Math.round(num(form.termYears)) * 12 + Math.round(num(form.termExtraMonths))

  const preview = useMemo(() => previewSchedule({
    principal: num(form.principal),
    termMonths,
    rateType: form.rateType,
    fixedRate: num(form.fixedRate),
    spread: num(form.spread),
    latestIndex,
    fixedYears: num(form.fixedYears),
  }), [form.principal, termMonths, form.rateType, form.fixedRate, form.spread, latestIndex, form.fixedYears])

  // Queried only on the linking step, and keyed by the computed instalment so
  // the deviation always refers to the terms currently on screen.
  const candidates = useMortgagePaymentCandidates(
    preview.payment > 0 ? preview.payment : undefined,
    { enabled: step === 3 },
  )

  const step1Valid = form.name.trim() !== '' && num(form.principal) > 0 && form.startDate !== '' && termMonths > 0
  const step2Valid = form.rateType === 'fixed'
    ? num(form.fixedRate) > 0
    : form.rateType === 'variable'
      ? form.spread.trim() !== ''
      : num(form.fixedRate) > 0 && form.spread.trim() !== '' && num(form.fixedYears) > 0

  function buildRatePeriods(): MortgageRatePeriod[] {
    const variable: MortgageRatePeriod = {
      start_month: form.rateType === 'mixed' ? Math.round(num(form.fixedYears) * 12) : 0,
      kind: 'variable',
      index_name: INDEX_NAME,
      spread: num(form.spread),
      review_months: Math.round(num(form.reviewMonths)) || 12,
      review_lag_months: Math.round(num(form.reviewLag)),
      floor_rate: optionalNum(form.floorRate),
      cap_rate: optionalNum(form.capRate),
    }
    const fixed: MortgageRatePeriod = {
      start_month: 0,
      kind: 'fixed',
      fixed_rate: num(form.fixedRate),
      review_lag_months: 2,
    }
    if (form.rateType === 'fixed') return [fixed]
    if (form.rateType === 'variable') return [variable]
    return [fixed, variable]
  }

  async function handleSave() {
    setSaving(true)
    setError(null)
    const payload: MortgageInput = {
      name: form.name.trim(),
      lender: form.lender.trim() || null,
      initial_principal: num(form.principal),
      start_date: form.startDate,
      signature_date: form.signatureDate || null,
      term_months: termMonths,
      payment_day: Math.round(num(form.paymentDay)) || 1,
      rate_type: form.rateType,
      linked_account_id: form.linkedAccountId ? Number(form.linkedAccountId) : null,
      linked_category_id: form.linkedCategoryId ? Number(form.linkedCategoryId) : null,
      property_value: optionalNum(form.propertyValue),
      property_value_date: null,
      include_in_net_worth: form.includeInNetWorth,
      notes: form.notes.trim() || null,
      rate_periods: buildRatePeriods(),
      bonuses: form.bonuses.map(({ key: _key, ...bonus }) => bonus),
    }
    try {
      const saved = mortgage
        ? await updateMortgage(mortgage.id, payload)
        : await createMortgage(payload)
      onSaved(saved)
    } catch (e) {
      setError(errorMessage(e, t))
      setSaving(false)
    }
  }

  function addBonus() {
    set('bonuses', [...form.bonuses, { key: nextBonusKey(), name: '', spread_reduction: 0, annual_cost: 0, active: true }])
  }

  function updateBonus(index: number, patch: Partial<MortgageBonus>) {
    set('bonuses', form.bonuses.map((b, i) => (i === index ? { ...b, ...patch } : b)))
  }

  const steps = [t.mortgageFormStepLoan, t.mortgageFormStepRate, t.mortgageFormStepLink]
  function renderDetectedMismatch(expected: string, deviation: string) {
    const text = t.mortgageFormDetectedMismatch(expected, deviation)
    const expectedAt = text.indexOf(expected)
    if (expectedAt < 0) return <Private>{text}</Private>
    const beforeExpected = text.slice(0, expectedAt)
    const afterExpected = text.slice(expectedAt + expected.length)
    const deviationAt = afterExpected.indexOf(deviation)
    if (deviationAt < 0) return <Private>{text}</Private>
    return (
      <>
        {beforeExpected}<Private>{expected}</Private>{afterExpected.slice(0, deviationAt)}
        <Private>{deviation}</Private>{afterExpected.slice(deviationAt + deviation.length)}
      </>
    )
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal modal-wide mortgage-form" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <span className="modal-title">
            {mortgage ? t.mortgageFormEditTitle : t.mortgageFormCreateTitle}
          </span>
          <button className="modal-close" onClick={onClose} type="button" aria-label={t.mortgageFormCancel}><IconClose size={15} /></button>
        </div>

        <div className="mortgage-form__steps">
          {steps.map((label, i) => (
            <div key={label} className={`mortgage-form__step${step === i + 1 ? ' active' : ''}${step > i + 1 ? ' done' : ''}`}>
              <span className="mortgage-form__step-num">{i + 1}</span>
              <span>{label}</span>
            </div>
          ))}
        </div>

        <div className="modal-body">
          {step === 1 && (
            <div className="mortgage-form__grid">
              <div className="form-group">
                <label htmlFor="mf-name">{t.mortgageFormName}</label>
                <input id="mf-name" className="form-input" value={form.name} onChange={e => set('name', e.target.value)} />
              </div>
              <div className="form-group">
                <label htmlFor="mf-lender">{t.mortgageFormLender}</label>
                <input id="mf-lender" className="form-input" value={form.lender} onChange={e => set('lender', e.target.value)} />
              </div>
              <div className="form-group">
                <label htmlFor="mf-principal">{t.mortgageFormPrincipal}</label>
                <input id="mf-principal" className="form-input" inputMode="decimal" value={form.principal} onChange={e => set('principal', e.target.value)} />
              </div>
              <div className="form-group">
                <label htmlFor="mf-signature">{t.mortgageFormSignatureDate}</label>
                <DatePicker
                  value={form.signatureDate}
                  onChange={v => set('signatureDate', v)}
                  ariaLabel={t.mortgageFormSignatureDate}
                />
                <span className="form-hint">{t.mortgageFormSignatureDateInfo}</span>
              </div>
              <div className="form-group">
                <label htmlFor="mf-start">{t.mortgageFormStartDate}</label>
                {/* The native date input renders its calendar in the browser's
                    locale, ignoring the language chosen in the app. */}
                <DatePicker
                  value={form.startDate}
                  onChange={v => set('startDate', v)}
                  ariaLabel={t.mortgageFormStartDate}
                />
              </div>
              <div className="form-group">
                <label htmlFor="mf-term">{t.mortgageFormTermYears}</label>
                <input id="mf-term" className="form-input" inputMode="numeric" value={form.termYears} onChange={e => set('termYears', e.target.value)} />
                <span className="form-hint">{t.mortgageFormTermTotal(termMonths)}</span>
              </div>
              <div className="form-group">
                <label htmlFor="mf-term-months">{t.mortgageFormTermExtraMonths}</label>
                <input id="mf-term-months" className="form-input" inputMode="numeric" value={form.termExtraMonths} onChange={e => set('termExtraMonths', e.target.value)} />
                <span className="form-hint">{t.mortgageFormTermExtraMonthsInfo}</span>
              </div>
              <div className="form-group">
                <label htmlFor="mf-day">{t.mortgageFormPaymentDay}</label>
                <input id="mf-day" className="form-input" inputMode="numeric" value={form.paymentDay} onChange={e => set('paymentDay', e.target.value)} />
              </div>
            </div>
          )}

          {step === 2 && (
            <>
              <div className="form-group">
                <label>{t.mortgageFormRateType}</label>
                <div className="theme-segmented">
                  {(['fixed', 'variable', 'mixed'] as MortgageRateType[]).map(type => (
                    <button
                      key={type}
                      type="button"
                      className={`theme-seg-btn${form.rateType === type ? ' active' : ''}`}
                      onClick={() => set('rateType', type)}
                      aria-pressed={form.rateType === type}
                    >
                      {type === 'fixed' ? t.mortgageRateFixed : type === 'variable' ? t.mortgageRateVariable : t.mortgageRateMixed}
                    </button>
                  ))}
                </div>
              </div>

              <div className="mortgage-form__grid">
                {form.rateType !== 'variable' && (
                  <div className="form-group">
                    <label htmlFor="mf-tin">{t.mortgageFormTin}</label>
                    <input id="mf-tin" className="form-input" inputMode="decimal" value={form.fixedRate} onChange={e => set('fixedRate', e.target.value)} />
                  </div>
                )}
                {form.rateType === 'mixed' && (
                  <div className="form-group">
                    <label htmlFor="mf-fyears">{t.mortgageFormFixedYears}</label>
                    <input id="mf-fyears" className="form-input" inputMode="numeric" value={form.fixedYears} onChange={e => set('fixedYears', e.target.value)} />
                  </div>
                )}
                {form.rateType !== 'fixed' && (
                  <>
                    <div className="form-group">
                      <label htmlFor="mf-index">{t.mortgageFormIndex}</label>
                      <input id="mf-index" className="form-input" value="Euríbor 12m" disabled />
                      {latestIndex > 0 && <span className="form-hint">{latestIndex.toFixed(3)} %</span>}
                    </div>
                    <div className="form-group">
                      <label htmlFor="mf-spread">{t.mortgageFormSpread}</label>
                      <input id="mf-spread" className="form-input" inputMode="decimal" value={form.spread} onChange={e => set('spread', e.target.value)} />
                    </div>
                    <div className="form-group">
                      <label htmlFor="mf-review">{t.mortgageFormReviewMonths}</label>
                      <input id="mf-review" className="form-input" inputMode="numeric" value={form.reviewMonths} onChange={e => set('reviewMonths', e.target.value)} />
                    </div>
                    <div className="form-group">
                      <label htmlFor="mf-lag">{t.mortgageFormReviewLag}</label>
                      <input id="mf-lag" className="form-input" inputMode="numeric" value={form.reviewLag} onChange={e => set('reviewLag', e.target.value)} />
                      <span className="form-hint">{t.mortgageFormReviewLagInfo}</span>
                    </div>
                    <div className="form-group">
                      <label htmlFor="mf-floor">{t.mortgageFormFloor}</label>
                      <input id="mf-floor" className="form-input" inputMode="decimal" value={form.floorRate} onChange={e => set('floorRate', e.target.value)} />
                    </div>
                    <div className="form-group">
                      <label htmlFor="mf-cap">{t.mortgageFormCap}</label>
                      <input id="mf-cap" className="form-input" inputMode="decimal" value={form.capRate} onChange={e => set('capRate', e.target.value)} />
                    </div>
                  </>
                )}
              </div>

              <div className="mortgage-form__section">
                <div className="mortgage-form__section-head">
                  <span>{t.mortgageFormBonuses}</span>
                  <button type="button" className="btn-secondary" onClick={addBonus}>{t.mortgageFormBonusAdd}</button>
                </div>
                <p className="form-hint">{t.mortgageFormBonusesInfo}</p>
                {form.bonuses.map((bonus, i) => (
                  <div key={bonus.key} className="mortgage-form__bonus-row">
                    <input
                      className="form-input"
                      placeholder={t.mortgageFormBonusName}
                      value={bonus.name}
                      onChange={e => updateBonus(i, { name: e.target.value })}
                    />
                    <input
                      className="form-input"
                      inputMode="decimal"
                      placeholder={t.mortgageFormBonusReduction}
                      value={String(bonus.spread_reduction)}
                      onChange={e => updateBonus(i, { spread_reduction: num(e.target.value) })}
                    />
                    <input
                      className="form-input"
                      inputMode="decimal"
                      placeholder={t.mortgageFormBonusCost}
                      value={String(bonus.annual_cost)}
                      onChange={e => updateBonus(i, { annual_cost: num(e.target.value) })}
                    />
                    <button
                      type="button"
                      className="btn-row-delete"
                      onClick={() => set('bonuses', form.bonuses.filter((_, idx) => idx !== i))}
                      aria-label={t.mortgageDeleteBtn}
                    ><IconClose size={14} /></button>
                  </div>
                ))}
              </div>
            </>
          )}

          {step === 3 && (
            <>
              <p className="form-hint">{t.mortgageFormLinkInfo}</p>

              {/* A recurring charge that differs from the computed instalment is
                  the signal that the terms are wrong, and this is the last
                  moment where fixing them is one click away. */}
              {candidates.data && candidates.data.candidates.length > 0 && (
                <div className="mortgage-form__detected">
                  {candidates.data.candidates.slice(0, 3).map(c => {
                    // Only a charge in the same ballpark as the instalment can
                    // be the mortgage; the rest are other recurring expenses and
                    // must not be reported as a wrong term.
                    const plausible = c.deviation_pct != null && Math.abs(c.deviation_pct) <= 20
                    const off = plausible && Math.abs(c.deviation ?? 0) >= 0.01
                    return (
                      <button
                        key={`${c.account_id}-${c.category_id}-${c.amount}`}
                        type="button"
                        className={`mortgage-form__detected-row${off ? ' mismatch' : ''}`}
                        onClick={() => {
                          set('linkedAccountId', String(c.account_id))
                          set('linkedCategoryId', c.category_id != null ? String(c.category_id) : '')
                        }}
                      >
                        <span className="mortgage-form__detected-main">
                          <strong className="private">{formatEur(c.amount)}</strong>
                          {' · '}{c.account_name}
                          {c.category_name ? ` · ${categoryLabel(c.category_name, lang, dynamicEs)}` : ''}
                          {' · '}{t.mortgageFormDetectedCharges(c.occurrences)}
                        </span>
                        {off ? (
                          <span className="mortgage-form__detected-warn">
                            <IconAlert size={13} />
                            {renderDetectedMismatch(
                              formatEur(preview.payment),
                              `${c.deviation! >= 0 ? '+' : ''}${formatEur(c.deviation!)}`,
                            )}
                          </span>
                        ) : plausible ? (
                          <span className="mortgage-form__detected-ok">
                            {t.mortgageFormDetectedMatch}
                          </span>
                        ) : (
                          <span className="mortgage-form__detected-other">
                            {t.mortgageFormDetectedOther}
                          </span>
                        )}
                      </button>
                    )
                  })}
                </div>
              )}

              <div className="mortgage-form__grid">
                <div className="form-group">
                  <label htmlFor="mf-account">{t.mortgageFormLinkAccount}</label>
                  <select id="mf-account" className="form-input" value={form.linkedAccountId} onChange={e => set('linkedAccountId', e.target.value)}>
                    <option value="">{t.mortgageFormNone}</option>
                    {accounts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                  </select>
                </div>
                <div className="form-group">
                  <label htmlFor="mf-category">{t.mortgageFormLinkCategory}</label>
                  <select id="mf-category" className="form-input" value={form.linkedCategoryId} onChange={e => set('linkedCategoryId', e.target.value)}>
                    <option value="">{t.mortgageFormNone}</option>
                    {categories.map(c => (
                      <option key={c.id} value={c.id}>{categoryLabel(c.name, lang, dynamicEs)}</option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label htmlFor="mf-property">{t.mortgageFormPropertyValue}</label>
                  <input id="mf-property" className="form-input" inputMode="decimal" value={form.propertyValue} onChange={e => set('propertyValue', e.target.value)} />
                </div>
                <div className="form-group">
                  <label htmlFor="mf-notes">{t.mortgageFormNotes}</label>
                  <input id="mf-notes" className="form-input" value={form.notes} onChange={e => set('notes', e.target.value)} />
                </div>
              </div>
              <label className="mortgage-form__checkbox">
                <input
                  type="checkbox"
                  checked={form.includeInNetWorth}
                  onChange={e => set('includeInNetWorth', e.target.checked)}
                />
                <span>
                  <strong>{t.mortgageFormIncludeNetWorth}</strong>
                  <span className="form-hint">{t.mortgageFormIncludeNetWorthInfo}</span>
                </span>
              </label>
            </>
          )}

          {error && <div className="state-box error"><IconAlert size={26} className="icon" /><span>{error}</span></div>}
        </div>

        {/* Live preview: catches a wrong input before the schedule is ever saved. */}
        <div className="mortgage-form__preview">
          <span className="mortgage-form__preview-label">{t.mortgageFormPreview}</span>
          <div className="mortgage-form__preview-values">
            <div>
              <span className="mortgage-form__preview-key">{t.mortgageFormPreviewPayment}</span>
              <span className="mortgage-form__preview-value private">{formatEur(preview.payment)}</span>
            </div>
            <div>
              <span className="mortgage-form__preview-key">{t.mortgageFormPreviewTotalInterest}</span>
              <span className="mortgage-form__preview-value private">{formatEur(preview.totalInterest)}</span>
            </div>
          </div>
        </div>

        <div className="modal-footer">
          {step > 1 && (
            <button type="button" className="btn-secondary" onClick={() => setStep(s => s - 1)} disabled={saving}>
              {t.mortgageFormBack}
            </button>
          )}
          {step < 3 ? (
            <button
              type="button"
              className="btn-primary"
              onClick={() => setStep(s => s + 1)}
              disabled={step === 1 ? !step1Valid : !step2Valid}
            >
              {t.mortgageFormNext}
            </button>
          ) : (
            <button type="button" className="btn-primary" onClick={handleSave} disabled={saving || !step1Valid || !step2Valid}>
              {t.mortgageFormSave}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
