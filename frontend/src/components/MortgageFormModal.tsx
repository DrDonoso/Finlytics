import { useState, useMemo, useId } from 'react'
import type { Account, Category, Mortgage, MortgageInput, MortgageRatePeriod, MortgageRateType, MortgageBonus } from '../api/types'
import { createMortgage, updateMortgage } from '../api/client'
import { errorMessage } from '../api/errors'
import { useEuriborSeries, useMortgagePaymentCandidates } from '../api/queries'
import Modal from './Modal'
import { IconAlert, IconClose } from './icons'
import DatePicker from './DatePicker'
import { useT, categoryLabel } from '../i18n'
import { previewSchedule } from '../mortgage/calc'
import { Private } from './Money'
import NumericInput from './NumericInput'
import { finiteOrZero, isBlank, isMalformed, parseAmount, parseDecimal, parseOptional, parseOr, type NumberParser } from '../utils/parseNumber'

const INDEX_NAME = 'euribor_12m'

interface Props {
  mortgage?: Mortgage | null
  accounts: Account[]
  categories: Category[]
  onClose: () => void
  onSaved: (mortgage: Mortgage) => void
}

/** A bonus as edited: a stable key, since new rows have no id until they are
 *  saved, and the numbers kept as typed so "0," survives until it is "0,25". */
type BonusRow = Omit<MortgageBonus, 'spread_reduction' | 'annual_cost'> & {
  key: string
  spreadReduction: string
  annualCost: string
}

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
    bonuses: mortgage?.bonuses.map(({ spread_reduction, annual_cost, ...bonus }) => ({
      ...bonus,
      key: nextBonusKey(),
      spreadReduction: String(spread_reduction),
      annualCost: String(annual_cost),
    })) ?? [],
    linkedAccountId: mortgage?.linked_account_id != null ? String(mortgage.linked_account_id) : '',
    linkedCategoryId: mortgage?.linked_category_id != null ? String(mortgage.linked_category_id) : '',
    propertyValue: mortgage?.property_value != null ? String(mortgage.property_value) : '',
    includeInNetWorth: mortgage?.include_in_net_worth ?? true,
    notes: mortgage?.notes ?? '',
  }
}

export default function MortgageFormModal({ mortgage, accounts, categories, onClose, onSaved }: Props) {
  const { t, lang, formatCurrency, formatPercent } = useT()
  const [step, setStep] = useState(1)
  const [form, setForm] = useState<FormState>(() => initialState(mortgage))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const titleId = useId()

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
  const termMonths = Math.round(parseOr(form.termYears, parseDecimal, 0)) * 12
    + Math.round(parseOr(form.termExtraMonths, parseDecimal, 0))
  const principal = parseAmount(form.principal)
  const paymentDay = Math.round(parseOr(form.paymentDay, parseDecimal, 1))
  const paymentDayValid = paymentDay >= 1 && paymentDay <= 31
  const fixedRate = parseDecimal(form.fixedRate)
  const spread = parseDecimal(form.spread)
  const fixedYears = parseDecimal(form.fixedYears)

  function numberError(value: string, parse: NumberParser, positive = false): string | null {
    if (isBlank(value)) return null
    const n = parse(value)
    if (!Number.isFinite(n)) return t.formInvalidNumber
    return positive && n <= 0 ? t.formPositiveNumber : null
  }

  const preview = useMemo(() => previewSchedule({
    principal: finiteOrZero(principal),
    termMonths: finiteOrZero(termMonths),
    rateType: form.rateType,
    fixedRate: finiteOrZero(fixedRate),
    spread: finiteOrZero(spread),
    latestIndex,
    fixedYears: finiteOrZero(fixedYears),
  }), [principal, termMonths, form.rateType, fixedRate, spread, latestIndex, fixedYears])

  // Queried only on the linking step, and keyed by the computed instalment so
  // the deviation always refers to the terms currently on screen.
  const candidates = useMortgagePaymentCandidates(
    preview.payment > 0 ? preview.payment : undefined,
    { enabled: step === 3 },
  )

  const step1Valid = form.name.trim() !== '' && principal > 0 && form.startDate !== '' && termMonths > 0 && paymentDayValid
  const variableValid = Number.isFinite(spread)
    && [form.reviewMonths, form.reviewLag, form.floorRate, form.capRate].every(v => !isMalformed(v, parseDecimal))
  const bonusesValid = form.bonuses.every(b => !isMalformed(b.spreadReduction, parseDecimal) && !isMalformed(b.annualCost, parseAmount))
  const step2Valid = bonusesValid && (form.rateType === 'fixed'
    ? fixedRate > 0
    : form.rateType === 'variable'
      ? variableValid
      : fixedRate > 0 && fixedYears > 0 && variableValid)
  const step3Valid = !isMalformed(form.propertyValue, parseAmount)

  function buildRatePeriods(): MortgageRatePeriod[] {
    const variable: MortgageRatePeriod = {
      start_month: form.rateType === 'mixed' ? Math.round(fixedYears * 12) : 0,
      kind: 'variable',
      index_name: INDEX_NAME,
      spread,
      review_months: Math.round(parseOr(form.reviewMonths, parseDecimal, 12)) || 12,
      review_lag_months: Math.round(parseOr(form.reviewLag, parseDecimal, 0)),
      floor_rate: parseOptional(form.floorRate, parseDecimal),
      cap_rate: parseOptional(form.capRate, parseDecimal),
    }
    const fixed: MortgageRatePeriod = {
      start_month: 0,
      kind: 'fixed',
      fixed_rate: fixedRate,
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
      initial_principal: principal,
      start_date: form.startDate,
      signature_date: form.signatureDate || null,
      term_months: termMonths,
      payment_day: paymentDay,
      rate_type: form.rateType,
      linked_account_id: form.linkedAccountId ? Number(form.linkedAccountId) : null,
      linked_category_id: form.linkedCategoryId ? Number(form.linkedCategoryId) : null,
      property_value: parseOptional(form.propertyValue, parseAmount),
      property_value_date: null,
      include_in_net_worth: form.includeInNetWorth,
      notes: form.notes.trim() || null,
      rate_periods: buildRatePeriods(),
      bonuses: form.bonuses.map(({ key: _key, spreadReduction, annualCost, ...bonus }) => ({
        ...bonus,
        spread_reduction: parseOr(spreadReduction, parseDecimal, 0),
        annual_cost: parseOr(annualCost, parseAmount, 0),
      })),
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
    set('bonuses', [...form.bonuses, { key: nextBonusKey(), name: '', spreadReduction: '', annualCost: '', active: true }])
  }

  function updateBonus(index: number, patch: Partial<Omit<BonusRow, 'key'>>) {
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
    <Modal onDismiss={onClose} disabled={saving} labelledBy={titleId} className="modal-wide mortgage-form">
        <div className="modal-header">
          <span className="modal-title" id={titleId}>
            {mortgage ? t.mortgageFormEditTitle : t.mortgageFormCreateTitle}
          </span>
          <button className="modal-close" onClick={onClose} disabled={saving} type="button" aria-label={t.mortgageFormCancel}><IconClose size={15} /></button>
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
                <NumericInput id="mf-principal" value={form.principal} onChange={text => set('principal', text)} error={numberError(form.principal, parseAmount, true)} />
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
                <NumericInput id="mf-term" inputMode="numeric" value={form.termYears} onChange={text => set('termYears', text)} error={numberError(form.termYears, parseDecimal)} />
                <span className="form-hint">{t.mortgageFormTermTotal(finiteOrZero(termMonths))}</span>
              </div>
              <div className="form-group">
                <label htmlFor="mf-term-months">{t.mortgageFormTermExtraMonths}</label>
                <NumericInput id="mf-term-months" inputMode="numeric" value={form.termExtraMonths} onChange={text => set('termExtraMonths', text)} error={numberError(form.termExtraMonths, parseDecimal)} />
                <span className="form-hint">{t.mortgageFormTermExtraMonthsInfo}</span>
              </div>
              <div className="form-group">
                <label htmlFor="mf-day">{t.mortgageFormPaymentDay}</label>
                <NumericInput id="mf-day" inputMode="numeric" value={form.paymentDay} onChange={text => set('paymentDay', text)} error={paymentDayValid ? null : t.mortgageFormPaymentDayInvalid} />
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
                    <NumericInput id="mf-tin" value={form.fixedRate} onChange={text => set('fixedRate', text)} error={numberError(form.fixedRate, parseDecimal, true)} />
                  </div>
                )}
                {form.rateType === 'mixed' && (
                  <div className="form-group">
                    <label htmlFor="mf-fyears">{t.mortgageFormFixedYears}</label>
                    <NumericInput id="mf-fyears" inputMode="numeric" value={form.fixedYears} onChange={text => set('fixedYears', text)} error={numberError(form.fixedYears, parseDecimal, true)} />
                  </div>
                )}
                {form.rateType !== 'fixed' && (
                  <>
                    <div className="form-group">
                      <label htmlFor="mf-index">{t.mortgageFormIndex}</label>
                      <input id="mf-index" className="form-input" value="Euríbor 12m" disabled />
                      {latestIndex > 0 && <span className="form-hint">{formatPercent(latestIndex, { decimals: 3 })}</span>}
                    </div>
                    <div className="form-group">
                      <label htmlFor="mf-spread">{t.mortgageFormSpread}</label>
                      <NumericInput id="mf-spread" value={form.spread} onChange={text => set('spread', text)} error={numberError(form.spread, parseDecimal)} />
                    </div>
                    <div className="form-group">
                      <label htmlFor="mf-review">{t.mortgageFormReviewMonths}</label>
                      <NumericInput id="mf-review" inputMode="numeric" value={form.reviewMonths} onChange={text => set('reviewMonths', text)} error={numberError(form.reviewMonths, parseDecimal)} />
                    </div>
                    <div className="form-group">
                      <label htmlFor="mf-lag">{t.mortgageFormReviewLag}</label>
                      <NumericInput id="mf-lag" inputMode="numeric" value={form.reviewLag} onChange={text => set('reviewLag', text)} error={numberError(form.reviewLag, parseDecimal)} />
                      <span className="form-hint">{t.mortgageFormReviewLagInfo}</span>
                    </div>
                    <div className="form-group">
                      <label htmlFor="mf-floor">{t.mortgageFormFloor}</label>
                      <NumericInput id="mf-floor" value={form.floorRate} onChange={text => set('floorRate', text)} error={numberError(form.floorRate, parseDecimal)} />
                    </div>
                    <div className="form-group">
                      <label htmlFor="mf-cap">{t.mortgageFormCap}</label>
                      <NumericInput id="mf-cap" value={form.capRate} onChange={text => set('capRate', text)} error={numberError(form.capRate, parseDecimal)} />
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
                    <div className="form-group">
                      <label htmlFor={`mf-${bonus.key}-name`}>{t.mortgageFormBonusName}</label>
                      <input
                        id={`mf-${bonus.key}-name`}
                        className="form-input"
                        value={bonus.name}
                        onChange={e => updateBonus(i, { name: e.target.value })}
                      />
                    </div>
                    <div className="form-group">
                      <label htmlFor={`mf-${bonus.key}-reduction`}>{t.mortgageFormBonusReduction}</label>
                      <NumericInput
                        id={`mf-${bonus.key}-reduction`}
                        value={bonus.spreadReduction}
                        onChange={text => updateBonus(i, { spreadReduction: text })}
                        error={numberError(bonus.spreadReduction, parseDecimal)}
                      />
                    </div>
                    <div className="form-group">
                      <label htmlFor={`mf-${bonus.key}-cost`}>{t.mortgageFormBonusCost}</label>
                      <NumericInput
                        id={`mf-${bonus.key}-cost`}
                        value={bonus.annualCost}
                        onChange={text => updateBonus(i, { annualCost: text })}
                        error={numberError(bonus.annualCost, parseAmount)}
                      />
                    </div>
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
                          <strong className="private">{formatCurrency(c.amount)}</strong>
                          {' · '}{c.account_name}
                          {c.category_name ? ` · ${categoryLabel(c.category_name, lang, dynamicEs)}` : ''}
                          {' · '}{t.mortgageFormDetectedCharges(c.occurrences)}
                        </span>
                        {off ? (
                          <span className="mortgage-form__detected-warn">
                            <IconAlert size={13} />
                            {renderDetectedMismatch(
                              formatCurrency(preview.payment),
                              `${c.deviation! >= 0 ? '+' : ''}${formatCurrency(c.deviation!)}`,
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
                  <NumericInput id="mf-property" value={form.propertyValue} onChange={text => set('propertyValue', text)} error={numberError(form.propertyValue, parseAmount)} />
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
              <span className="mortgage-form__preview-value private">{formatCurrency(preview.payment)}</span>
            </div>
            <div>
              <span className="mortgage-form__preview-key">{t.mortgageFormPreviewTotalInterest}</span>
              <span className="mortgage-form__preview-value private">{formatCurrency(preview.totalInterest)}</span>
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
            <button type="button" className="btn-primary" onClick={handleSave} disabled={saving || !step1Valid || !step2Valid || !step3Valid}>
              {t.mortgageFormSave}
            </button>
          )}
        </div>
    </Modal>
  )
}
