import { useState, useRef, useMemo, useEffect } from 'react'
import type {
  Account, Category, Tag,
  ImportTransaction, PreviewResponse, ConfirmRequest, ImportResult,
} from '../api/types'
import { previewImport, confirmImport } from '../api/client'
import { useT, categoryLabel, type Dict, paletteColor } from '../i18n'
import DateInput from './DateInput'
import CategorySelect from './CategorySelect'
import TagTypeahead from './TagTypeahead'
import RuleFormModal from './RuleFormModal'

type Step = 'upload' | 'extracting' | 'account' | 'preview' | 'saving'

type EditRow = ImportTransaction & { _key: number }

interface Props {
  accounts:   Account[]
  categories: Category[]
  allTags:    Tag[]
  onClose:    () => void
  onSuccess:  (result: ImportResult) => void
}

function friendlyError(e: unknown, t: Dict): string {
  const msg = e instanceof Error ? e.message : String(e)
  if (msg.includes('503')) return t.error503
  if (msg.includes('400')) return t.error400
  if (msg.includes('Failed to fetch') || msg.includes('NetworkError') || msg.includes('network')) {
    return t.errorNetwork
  }
  return t.errorUnexpected(msg)
}

function toImportTxn(row: EditRow): ImportTransaction {
  return {
    transaction_date:    row.transaction_date,
    amount:              row.amount,
    currency:            row.currency,
    description:         row.description,
    raw_line:            row.raw_line,
    category:            row.category,
    category_confidence: row.category_confidence,
    account_ref:         row.account_ref,
    balance_after:       row.balance_after,
    tags:                row.tags,
    merchant:            row.merchant,
    detail:              row.detail,
  }
}


export default function ImportModal({ accounts, categories, allTags, onClose, onSuccess }: Props) {
  const { t, lang, formatCurrency } = useT()
  const [step,            setStep]            = useState<Step>('upload')
  const [file,            setFile]            = useState<File | null>(null)
  const [accountName,     setAccountName]     = useState('')
  const [newAccountMode,  setNewAccountMode]  = useState(false)
  const [preview,         setPreview]         = useState<PreviewResponse | null>(null)
  const [rows,            setRows]            = useState<EditRow[]>([])
  const [error,           setError]           = useState<string | null>(null)
  const nextKey = useRef(0)

  // Account detection state (populated after preview call)
  const [detectedMasked, setDetectedMasked] = useState<string | null>(null)
  const [detectedIban,   setDetectedIban]   = useState<string | null>(null)
  const [matchedId,      setMatchedId]      = useState<number | null>(null)
  const [matchedName,    setMatchedName]    = useState<string | null>(null)

  // Phase 1 validation
  const [submitAttempted,         setSubmitAttempted]         = useState(false)
  // Phase 2 validation
  const [accountContinueAttempted, setAccountContinueAttempted] = useState(false)
  const [accountTouched,           setAccountTouched]           = useState(false)

  const accountValid    = matchedId != null || accountName.trim().length > 0
  const showFileError   = submitAttempted && !file
  const showAccountError = (accountContinueAttempted || accountTouched) && !accountValid

  const [createRuleRow, setCreateRuleRow] = useState<EditRow | null>(null)
  const [ruleToast,     setRuleToast]     = useState<string | null>(null)

  useEffect(() => {
    if (!ruleToast) return
    const id = setTimeout(() => setRuleToast(null), 4000)
    return () => clearTimeout(id)
  }, [ruleToast])

  const dynamicEs = useMemo(
    () => Object.fromEntries(categories.filter(c => c.name_es).map(c => [c.name, c.name_es!])),
    [categories],
  )

  const baseCategories = useMemo(() =>
    categories
      .filter(c => c.is_base)
      .sort((a, b) => categoryLabel(a.name, lang, dynamicEs).localeCompare(categoryLabel(b.name, lang, dynamicEs))),
    [categories, lang, dynamicEs]
  )

  const customCategories = useMemo(() => {
    const baseNames = new Set(categories.filter(c => c.is_base).map(c => c.name))
    const seen = new Set<string>()
    const result: string[] = []
    for (const row of rows) {
      const val = row.category.trim()
      if (val && !baseNames.has(val) && !seen.has(val)) {
        seen.add(val)
        result.push(val)
      }
    }
    return result.sort()
  }, [rows, categories])

  /** AI-suggested colors for tags in this preview batch. */
  const suggestedColors = useMemo((): Record<string, string> => {
    if (!preview?.suggested_tags) return {}
    return Object.fromEntries(preview.suggested_tags.map(s => [s.name, s.color]))
  }, [preview])

  /** Distinct non-empty merchant values across all current rows — drives the datalist. */
  const distinctMerchants = useMemo(() => {
    const seen = new Set<string>()
    for (const row of rows) {
      const m = row.merchant?.trim()
      if (m) seen.add(m)
    }
    return [...seen].sort()
  }, [rows])

  /** Distinct tag names used across ALL preview rows — feeds TagTypeahead suggestions. */
  const distinctPreviewTagNames = useMemo(() => {
    const seen = new Set<string>()
    for (const row of rows) {
      for (const tag of row.tags) {
        if (tag) seen.add(tag)
      }
    }
    return [...seen].sort()
  }, [rows])

  function toEditRows(txns: ImportTransaction[]): EditRow[] {
    return txns.map(tx => ({ ...tx, _key: nextKey.current++ }))
  }

  // ── Phase 1 → upload file, call preview ──────────────────────────────────────

  async function handleUpload() {
    setSubmitAttempted(true)
    if (!file) return
    setStep('extracting')
    setError(null)
    try {
      const p = await previewImport(file)
      setPreview(p)

      const dm = p.detected_account_masked ?? null
      const di = p.detected_account_iban ?? null
      const mid = p.matched_account_id ?? null
      const mn = p.matched_account_name ?? null
      setDetectedMasked(dm)
      setDetectedIban(di)
      setMatchedId(mid)
      setMatchedName(mn)

      // Pre-set account name for matched accounts
      if (mid != null && mn) setAccountName(mn)

      const txns = p.transactions.map(tx => ({
        ...tx,
        account_ref: tx.account_ref || p.account_ref || '',
      }))
      setRows(toEditRows(txns))
      setStep('account')
    } catch (e) {
      setError(friendlyError(e, t))
      setStep('upload')
    }
  }

  // ── Phase 2 → account resolution → proceed to preview ────────────────────────

  function handleAccountContinue() {
    setAccountContinueAttempted(true)
    if (!accountValid) return
    setStep('preview')
  }

  // ── Phase 3 → confirm & save ──────────────────────────────────────────────────

  async function handleConfirm() {
    if (!preview) return
    setStep('saving')
    setError(null)
    try {
      const dbTagNames = new Set(allTags.map(t => t.name))
      const suggestedMap = Object.fromEntries(
        (preview.suggested_tags ?? []).map(s => [s.name, s.color])
      )
      const tag_colors: Record<string, string> = {}
      for (const row of rows) {
        for (const tagName of row.tags) {
          if (!dbTagNames.has(tagName) && !(tagName in tag_colors)) {
            tag_colors[tagName] = suggestedMap[tagName] ?? paletteColor(tagName)
          }
        }
      }
      const payload: ConfirmRequest = {
        account_name:    accountName.trim() || preview.account_ref || '',
        source_filename: preview.filename,
        transactions:    rows.map(toImportTxn),
        ...(Object.keys(tag_colors).length > 0 ? { tag_colors } : {}),
        // Send full IBAN only when creating a brand-new detected account
        ...(matchedId == null && detectedIban ? { account_number: detectedIban } : {}),
      }
      const result = await confirmImport(payload)
      onSuccess(result)
    } catch (e) {
      setError(friendlyError(e, t))
      setStep('preview')
    }
  }

  function updateRow(key: number, patch: Partial<Omit<EditRow, '_key'>>) {
    setRows(rs => rs.map(r => r._key === key ? { ...r, ...patch } : r))
  }
  function deleteRow(key: number) {
    setRows(rs => rs.filter(r => r._key !== key))
  }
  function addBlankRow() {
    const today = new Date().toISOString().slice(0, 10)
    setRows(rs => [...rs, {
      _key:                nextKey.current++,
      transaction_date:    today,
      amount:              -0.01,
      currency:            'EUR',
      description:         '',
      raw_line:            null,
      category:            'Other',
      category_confidence: null,
      account_ref:         accountName || preview?.account_ref || '',
      balance_after:       null,
      tags:                [],
      merchant:            null,
    }])
  }

  const isSpinning = step === 'extracting' || step === 'saving'
  const hasLowConf = rows.some(r => r.category_confidence !== null && r.category_confidence < 0.5)

  return (
    <>
      <div className="modal-backdrop">
        <div className="modal modal-wide" role="dialog" aria-modal="true" aria-labelledby="modal-title-id">

        <div className="modal-header">
          <h2 className="modal-title" id="modal-title-id">
            {step === 'preview' ? t.modalTitlePreview : t.modalTitleUpload}
          </h2>
          <button className="modal-close" onClick={onClose} disabled={isSpinning} aria-label={t.modalClose}>
            ✕
          </button>
        </div>

        <div className="modal-body">
          {/* ── Phase 1: File picker ────────────────────────────────────────── */}
          {step === 'upload' && (
            <div className="upload-form">
              <div className="form-group">
                <label htmlFor="import-file">{t.modalFileLabel} <span className="rules-required">*</span></label>
                <input
                  id="import-file"
                  className={`form-input${showFileError ? ' form-input--error' : ''}`}
                  type="file"
                  accept=".pdf"
                  onChange={e => setFile(e.target.files?.[0] ?? null)}
                />
                {showFileError
                  ? <span className="form-field-error">{t.modalFileRequired}</span>
                  : <span className="form-hint">{t.modalFileHint}</span>
                }
              </div>

              {error && <div className="import-error">{error}</div>}
            </div>
          )}

          {/* ── Phase 2: Account resolution ─────────────────────────────────── */}
          {step === 'account' && (
            <div className="upload-form">
              {matchedId != null ? (
                // Case A: existing account matched → show confirmation banner
                <div className="import-acct-banner import-acct-banner--matched">
                  ✓ {t.importDetectedAccount(detectedMasked ?? '', matchedName ?? '')}
                </div>
              ) : detectedMasked ? (
                // Case B: new IBAN detected — ask for account name
                <>
                  <div className="import-acct-banner import-acct-banner--new">
                    {t.importNewAccountDetected(detectedMasked)}
                  </div>
                  <div className="form-group" style={{ marginTop: 16 }}>
                    <label htmlFor="import-new-name">
                      {t.modalAccountLabel} <span className="rules-required">*</span>
                    </label>
                    <input
                      id="import-new-name"
                      type="text"
                      className={`form-input${showAccountError ? ' form-input--error' : ''}`}
                      placeholder={t.modalAccountPlaceholder}
                      value={accountName}
                      onChange={e => setAccountName(e.target.value)}
                      onBlur={() => setAccountTouched(true)}
                      autoFocus
                    />
                    {showAccountError
                      ? <span className="form-field-error">{t.modalAccountRequired}</span>
                      : <span className="form-hint">{t.modalAccountHint}</span>
                    }
                  </div>
                </>
              ) : (
                // Case C: no IBAN detected — manual account entry (fallback)
                <div className="form-group">
                  <label htmlFor="import-account">
                    {t.modalAccountLabel} <span className="rules-required">*</span>
                  </label>
                  {accounts.length === 0 ? (
                    <input
                      id="import-account"
                      className={`form-input${showAccountError ? ' form-input--error' : ''}`}
                      type="text"
                      placeholder={t.modalAccountPlaceholder}
                      value={accountName}
                      onChange={e => setAccountName(e.target.value)}
                      onBlur={() => setAccountTouched(true)}
                      autoFocus
                    />
                  ) : (
                    <>
                      <select
                        id="import-account"
                        className={`form-input${showAccountError && !newAccountMode ? ' form-input--error' : ''}`}
                        value={newAccountMode ? '__new__' : accountName}
                        onChange={e => {
                          if (e.target.value === '__new__') {
                            setNewAccountMode(true)
                            setAccountName('')
                            setAccountTouched(false)
                          } else {
                            setNewAccountMode(false)
                            setAccountName(e.target.value)
                            setAccountTouched(true)
                          }
                        }}
                        onBlur={() => !newAccountMode && setAccountTouched(true)}
                      >
                        <option value="">{t.modalAccountPlaceholder}</option>
                        {accounts.map(a => (
                          <option key={a.id} value={a.name}>{a.name}</option>
                        ))}
                        <option value="__new__">{t.modalAccountNew}</option>
                      </select>
                      {newAccountMode && (
                        <input
                          className={`form-input${showAccountError ? ' form-input--error' : ''}`}
                          type="text"
                          placeholder={t.modalAccountPlaceholder}
                          value={accountName}
                          onChange={e => setAccountName(e.target.value)}
                          onBlur={() => setAccountTouched(true)}
                          style={{ marginTop: 4 }}
                          autoFocus
                        />
                      )}
                    </>
                  )}
                  {showAccountError
                    ? <span className="form-field-error">{t.modalAccountRequired}</span>
                    : <span className="form-hint">{t.modalAccountHint}</span>
                  }
                </div>
              )}

              {error && <div className="import-error" style={{ marginTop: 12 }}>{error}</div>}
            </div>
          )}

          {isSpinning && (
            <div className="spinner-wrap">
              <div className="spinner" />
              <div className="spinner-label">
                {step === 'extracting' ? t.modalExtractingSpinner : t.modalSavingSpinner}
              </div>
            </div>
          )}

          {/* ── Phase 3: Transaction preview table ──────────────────────────── */}
          {step === 'preview' && preview && (
            <div>
              <div className="preview-meta">
                <span>{t.modalPreviewMeta(rows.length, preview.filename)}</span>
                {hasLowConf && (
                  <span className="confidence-hint">{t.modalLowConfidence}</span>
                )}
              </div>

              <button className="btn-outline" onClick={addBlankRow}>
                {t.modalAddRow}
              </button>

              {(preview.year_detected === false || preview.statement_year == null) && (
                <div className="year-warning-banner">
                  {t.modalYearNotFound}
                </div>
              )}

              <div className="preview-table-wrap">
                <table className="preview-table">
                  <thead>
                    <tr>
                      <th>{t.previewColDate}</th>
                      <th>{t.previewColDesc}</th>
                      <th>{t.colMerchant}</th>
                      <th>{t.previewColAmount}</th>
                      <th>{t.previewColCategory}</th>
                      <th>{t.previewColAccount}</th>
                      <th>{t.previewColTags}</th>
                      <th>{t.previewColConf}</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map(row => {
                      const lowConf = row.category_confidence !== null && row.category_confidence < 0.5
                      const amountColor = row.amount < 0
                        ? 'var(--expense)'
                        : row.amount > 0
                          ? 'var(--income)'
                          : 'inherit'
                      return (
                        <tr key={row._key} className={lowConf ? 'row-low-confidence' : ''}>
                          <td>
                            <DateInput
                              className="cell-input cell-date"
                              value={row.transaction_date}
                              lang={lang}
                              onChange={iso => updateRow(row._key, { transaction_date: iso })}
                            />
                          </td>

                          <td>
                            <input
                              type="text"
                              className="cell-input cell-desc"
                              value={row.description}
                              onChange={e => updateRow(row._key, { description: e.target.value })}
                            />
                            {row.detail && (
                              <div className="tx-detail-subline tx-detail-subline--input-aligned">{row.detail}</div>
                            )}
                          </td>

                          <td>
                            <input
                              type="text"
                              list="prev-merchants"
                              className="cell-input cell-merchant import-merchant-input"
                              value={row.merchant ?? ''}
                              placeholder={t.importMerchantPlaceholder}
                              onChange={e => updateRow(row._key, { merchant: e.target.value || null })}
                            />
                          </td>

                          <td>
                            <div className="amount-cell">
                              <select
                                className="cell-sign"
                                value={row.amount <= 0 ? '-' : '+'}
                                onChange={e => {
                                  const neg = e.target.value === '-'
                                  updateRow(row._key, { amount: neg ? -Math.abs(row.amount) : Math.abs(row.amount) })
                                }}
                                title={row.amount <= 0 ? t.previewSignExpense : t.previewSignIncome}
                              >
                                <option value="-">{t.previewSignExpense}</option>
                                <option value="+">{t.previewSignIncome}</option>
                              </select>
                              <input
                                type="number"
                                className="cell-input cell-amount"
                                value={Math.abs(row.amount)}
                                min="0"
                                step="0.01"
                                style={{ color: amountColor }}
                                onChange={e => {
                                  const abs = Math.abs(Number(e.target.value))
                                  updateRow(row._key, { amount: row.amount <= 0 ? -abs : abs })
                                }}
                              />
                            </div>
                          </td>

                          <td>
                            <div className="category-cell-wrap">
                              <CategorySelect
                                value={row.category}
                                baseCategories={baseCategories}
                                extraCategories={customCategories}
                                lang={lang}
                                t={t}
                                onChange={val => updateRow(row._key, { category: val })}
                              />
                              {row.matched_rule_id != null && (
                                <span
                                  className="rule-match-badge"
                                  title={t.ruleMatchTooltip(row.matched_rule_name ?? '')}
                                >
                                  {t.ruleMatchBadge}
                                </span>
                              )}
                            </div>
                          </td>

                          <td>
                            <input
                              type="text"
                              list="prev-accs"
                              className="cell-input cell-account"
                              value={row.account_ref}
                              onChange={e => updateRow(row._key, { account_ref: e.target.value })}
                            />
                          </td>

                          <td>
                            <TagTypeahead
                              tags={row.tags}
                              availableTags={allTags}
                              suggestedColors={suggestedColors}
                              previewTagNames={distinctPreviewTagNames}
                              onChange={tags => updateRow(row._key, { tags })}
                              placeholder={t.tagTypeaheadPlaceholder}
                            />
                          </td>

                          <td>
                            {row.category_confidence !== null ? (
                              <span className={`conf-badge ${lowConf ? 'conf-low' : 'conf-ok'}`}>
                                {Math.round(row.category_confidence * 100)}%
                              </span>
                            ) : (
                              <span className="conf-badge conf-na">—</span>
                            )}
                          </td>

                          <td>
                            <div className="td-actions">
                              <button
                                className="btn-row-icon btn-create-rule"
                                onClick={() => setCreateRuleRow(row)}
                                title={t.createRuleBtn}
                              >⚙+</button>
                              <button
                                className="btn-row-delete"
                                onClick={() => deleteRow(row._key)}
                                title={t.previewDeleteRow}
                              >✕</button>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>

              <datalist id="prev-accs">
                {accounts.map(a => <option key={a.id} value={a.name} />)}
              </datalist>
              <datalist id="prev-merchants">
                {distinctMerchants.map(m => <option key={m} value={m} />)}
              </datalist>

              <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-muted)' }}>
                {t.previewTotalExpenses}: <strong style={{ color: 'var(--expense)' }}>
                  {formatCurrency(rows.filter(r => r.amount < 0).reduce((s, r) => s + Math.abs(r.amount), 0))}
                </strong>
                &nbsp;·&nbsp;
                {t.previewTotalIncome}: <strong style={{ color: 'var(--income)' }}>
                  {formatCurrency(rows.filter(r => r.amount > 0).reduce((s, r) => s + r.amount, 0))}
                </strong>
              </div>

              {error && <div className="import-error" style={{ marginTop: 12 }}>{error}</div>}
            </div>
          )}
        </div>

        {!isSpinning && (
          <div className="modal-footer">
            <button className="btn-secondary" onClick={onClose}>{t.modalBtnCancel}</button>

            {step === 'upload' && (
              <button
                className="btn-primary"
                onClick={handleUpload}
                disabled={!file}
              >
                {t.modalBtnExtract}
              </button>
            )}

            {step === 'account' && (
              <button
                className="btn-primary"
                onClick={handleAccountContinue}
                disabled={matchedId == null && accountName.trim().length === 0}
              >
                {t.modalBtnContinue}
              </button>
            )}

            {step === 'preview' && (
              <button
                className="btn-primary"
                onClick={handleConfirm}
                disabled={rows.length === 0}
              >
                {t.modalBtnConfirm(rows.length)}
              </button>
            )}
          </div>
        )}

        </div>
      </div>

      {createRuleRow && (
        <RuleFormModal
          initialValues={{
            description_mode:  'contains',
            description_value: createRuleRow.description,
            set_category:      createRuleRow.category,
            set_merchant:      createRuleRow.merchant,
            add_tags:          createRuleRow.tags,
          }}
          categories={categories}
          availableTags={allTags}
          onSave={() => { setCreateRuleRow(null); setRuleToast(t.createRuleToast) }}
          onClose={() => setCreateRuleRow(null)}
        />
      )}

      {ruleToast && <div className="rule-toast">{ruleToast}</div>}
    </>
  )
}
