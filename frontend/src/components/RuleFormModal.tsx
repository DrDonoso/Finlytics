import { useState, useEffect, useMemo } from 'react'
import type { Rule, RuleInput, DescriptionMode, AmountSign, Category, Tag } from '../api/types'
import { createRule, updateRule, previewRule, applyRule } from '../api/client'
import { useT, categoryLabel } from '../i18n'
import CategorySelect from './CategorySelect'
import TagTypeahead from './TagTypeahead'
import { IconClose, IconCheck, IconChevronDown, IconChevronRight } from './icons'

interface FormState {
  name: string
  priority: number
  enabled: boolean
  description_mode: DescriptionMode
  description_value: string
  detail_mode: DescriptionMode
  detail_value: string
  amount_sign: AmountSign | null
  amount_min: string
  amount_max: string
  account_ref: string
  currency: string
  set_category: string
  set_merchant: string
  add_tags: string[]
  skip_ai: boolean
}

const DEFAULT_FORM: FormState = {
  name: '',
  priority: 100,
  enabled: true,
  description_mode: 'contains',
  description_value: '',
  detail_mode: 'contains',
  detail_value: '',
  amount_sign: null,
  amount_min: '',
  amount_max: '',
  account_ref: '',
  currency: '',
  set_category: '',
  set_merchant: '',
  add_tags: [],
  skip_ai: false,
}

export interface RuleFormModalProps {
  /** If provided the modal is in edit mode and pre-fills from this rule. */
  editingRule?: Rule
  /** Optional initial values for the create-from-row case. */
  initialValues?: Partial<RuleInput>
  categories: Category[]
  availableTags: Tag[]
  onSave: (rule: Rule) => void
  onClose: () => void
}

export default function RuleFormModal({
  editingRule,
  initialValues,
  categories,
  availableTags,
  onSave,
  onClose,
}: RuleFormModalProps) {
  const { t, lang } = useT()

  const baseCategories = useMemo(
    () => [...categories.filter(c => c.is_base)].sort((a, b) =>
      categoryLabel(a.name, lang).localeCompare(categoryLabel(b.name, lang), lang)
    ),
    [categories, lang],
  )

  const extraCategories = useMemo(
    () => categories.filter(c => !c.is_base).map(c => c.name),
    [categories],
  )

  function makeInitialForm(): FormState {
    if (editingRule) {
      return {
        name: editingRule.name,
        priority: editingRule.priority,
        enabled: editingRule.enabled,
        description_mode: editingRule.description_mode,
        description_value: editingRule.description_value,
        detail_mode: editingRule.detail_mode ?? DEFAULT_FORM.detail_mode,
        detail_value: editingRule.detail_value ?? '',
        amount_sign: editingRule.amount_sign,
        amount_min: editingRule.amount_min != null ? String(editingRule.amount_min) : '',
        amount_max: editingRule.amount_max != null ? String(editingRule.amount_max) : '',
        account_ref: editingRule.account_ref ?? '',
        currency: editingRule.currency ?? '',
        set_category: editingRule.set_category ?? '',
        set_merchant: editingRule.set_merchant ?? '',
        add_tags: editingRule.add_tags,
        skip_ai: editingRule.skip_ai,
      }
    }
    if (initialValues) {
      return {
        ...DEFAULT_FORM,
        name:              initialValues.name              ?? DEFAULT_FORM.name,
        priority:          initialValues.priority          ?? DEFAULT_FORM.priority,
        enabled:           initialValues.enabled           ?? DEFAULT_FORM.enabled,
        description_mode:  initialValues.description_mode  ?? DEFAULT_FORM.description_mode,
        description_value: initialValues.description_value ?? DEFAULT_FORM.description_value,
        detail_mode:       initialValues.detail_mode       ?? DEFAULT_FORM.detail_mode,
        detail_value:      initialValues.detail_value      ?? DEFAULT_FORM.detail_value,
        amount_sign:       initialValues.amount_sign       ?? DEFAULT_FORM.amount_sign,
        amount_min:        initialValues.amount_min != null ? String(initialValues.amount_min) : DEFAULT_FORM.amount_min,
        amount_max:        initialValues.amount_max != null ? String(initialValues.amount_max) : DEFAULT_FORM.amount_max,
        account_ref:       initialValues.account_ref       ?? DEFAULT_FORM.account_ref,
        currency:          initialValues.currency          ?? DEFAULT_FORM.currency,
        set_category:      initialValues.set_category      ?? DEFAULT_FORM.set_category,
        set_merchant:      initialValues.set_merchant      ?? DEFAULT_FORM.set_merchant,
        add_tags:          initialValues.add_tags          ?? DEFAULT_FORM.add_tags,
        skip_ai:           initialValues.skip_ai           ?? DEFAULT_FORM.skip_ai,
      }
    }
    return DEFAULT_FORM
  }

  const [form, setForm] = useState<FormState>(makeInitialForm)
  const [open, setOpen] = useState({ identity: true, conditions: true, actions: true })
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  // Preview / apply state
  const [previewCount, setPreviewCount] = useState<number | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewErr, setPreviewErr] = useState(false)
  const [applying, setApplying] = useState(false)
  const [applyOnSave, setApplyOnSave] = useState(false)
  const [applyToast, setApplyToast] = useState<string | null>(null)

  function toggleSection(section: 'identity' | 'conditions' | 'actions') {
    setOpen(prev => ({ ...prev, [section]: !prev[section] }))
  }

  function patchForm<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm(prev => ({ ...prev, [key]: value }))
  }

  function validate(): string | null {
    if (!form.name.trim()) return t.rulesValidationName
    if (!form.description_value.trim()) return t.rulesValidationPattern
    if (form.skip_ai && !form.set_category.trim()) return t.rulesValidationCategory
    if (form.description_mode === 'regex') {
      try { new RegExp(form.description_value) }
      catch (e) { return t.rulesValidationRegex(String(e)) }
    }
    if (form.detail_value.trim() && form.detail_mode === 'regex') {
      try { new RegExp(form.detail_value) }
      catch (e) { return t.rulesValidationRegex(String(e)) }
    }
    const minNum = form.amount_min.trim() !== '' ? Number(form.amount_min) : null
    const maxNum = form.amount_max.trim() !== '' ? Number(form.amount_max) : null
    if (minNum !== null && (isNaN(minNum) || minNum < 0)) return t.rulesValidationAmount
    if (maxNum !== null && (isNaN(maxNum) || maxNum < 0)) return t.rulesValidationAmount
    if (minNum !== null && maxNum !== null && minNum > maxNum) return t.rulesValidationAmount
    return null
  }

  function buildPayload(): RuleInput {
    return {
      name:              form.name.trim(),
      priority:          form.priority,
      enabled:           form.enabled,
      description_mode:  form.description_mode,
      description_value: form.description_value.trim(),
      detail_mode:       form.detail_value.trim() ? form.detail_mode : null,
      detail_value:      form.detail_value.trim() || null,
      amount_sign:       form.amount_sign,
      amount_min:        form.amount_min.trim() !== '' ? Number(form.amount_min) : null,
      amount_max:        form.amount_max.trim() !== '' ? Number(form.amount_max) : null,
      account_ref:       form.account_ref.trim()    || null,
      currency:          form.currency.trim()        || null,
      set_category:      form.set_category.trim()   || null,
      set_merchant:      form.set_merchant.trim()   || null,
      add_tags:          form.add_tags,
      skip_ai:           form.skip_ai,
    }
  }

  const conditionsEmpty = !form.description_value.trim()

  // Debounced preview: re-query when condition fields change
  useEffect(() => {
    if (conditionsEmpty) {
      setPreviewCount(null)
      setPreviewLoading(false)
      setPreviewErr(false)
      return
    }
    setPreviewLoading(true)
    setPreviewErr(false)
    const payload = buildPayload()
    const timer = setTimeout(async () => {
      try {
        const res = await previewRule(payload)
        setPreviewCount(res.count)
      } catch {
        setPreviewErr(true)
      } finally {
        setPreviewLoading(false)
      }
    }, 400)
    return () => clearTimeout(timer)
  }, [form.description_value, form.description_mode, form.detail_value, form.detail_mode, form.amount_sign, form.amount_min, form.amount_max, form.account_ref, form.currency]) // eslint-disable-line react-hooks/exhaustive-deps

  async function handleSave() {
    const validErr = validate()
    if (validErr) { setFormError(validErr); return }

    setSaving(true)
    setFormError(null)

    const payload = buildPayload()
    try {
      const result = editingRule !== undefined
        ? await updateRule(editingRule.id, payload)
        : await createRule(payload)

      if (applyOnSave && !conditionsEmpty && (previewCount ?? 0) > 0) {
        setApplying(true)
        try {
          const applyResult = await applyRule(payload)
          setApplyToast(t.rulesSaveAndApplyToast(applyResult.applied))
        } catch {
          onSave(result)   // apply failed — rule was saved, close immediately
          return
        } finally {
          setApplying(false)
        }
        setTimeout(() => onSave(result), 1500)
      } else {
        onSave(result)
      }
    } catch (e) {
      setFormError(String(e))
      setSaving(false)
    }
  }

  const title = editingRule ? t.rulesEditTitle : t.rulesAddTitle

  return (
    <div className="modal-backdrop modal-backdrop-rule">
      <div className="modal modal-rule-form" role="dialog" aria-modal="true" aria-labelledby="rfm-title">

        <div className="modal-header">
          <h2 className="modal-title" id="rfm-title">{title}</h2>
          <button className="modal-close" onClick={onClose} disabled={saving} aria-label={t.modalClose}><IconClose size={16} /></button>
        </div>

        <div className="modal-body">
          {formError && (
            <div className="import-error" style={{ marginBottom: 12 }}>{formError}</div>
          )}

          <div className="rules-sections-container">

            {/* ── ① Identity ──────────────────────────────────────────────── */}
            <button
              type="button"
              className="rules-section-heading"
              aria-expanded={open.identity}
              onClick={() => toggleSection('identity')}
            >
              <span>{t.rulesSectionIdentity}</span>
              <span className="rules-section-chevron" aria-hidden="true">
                {open.identity ? <IconChevronDown size={14} /> : <IconChevronRight size={14} />}
              </span>
            </button>
            <div className="rules-section" style={open.identity ? undefined : { display: 'none' }}>
              <div className="rules-enabled-top">
                <input
                  type="checkbox"
                  className="rules-checkbox"
                  id="rfm-enabled"
                  checked={form.enabled}
                  onChange={e => patchForm('enabled', e.target.checked)}
                  disabled={saving}
                />
                <label htmlFor="rfm-enabled" className="rules-toggle-label">
                  {t.rulesFieldEnabled}
                </label>
              </div>
              <div className="rules-form-grid">
                <div className="rules-field-group rules-span-2">
                  <label className="rules-label">{t.rulesFieldName} *</label>
                  <input
                    type="text"
                    className="form-input"
                    value={form.name}
                    onChange={e => patchForm('name', e.target.value)}
                    placeholder={t.rulesFieldNamePlaceholder}
                    disabled={saving}
                    autoFocus
                  />
                </div>
                <div className="rules-field-group">
                  <label className="rules-label">{t.rulesFieldPriority}</label>
                  <input
                    type="number"
                    className="form-input"
                    value={form.priority}
                    onChange={e => patchForm('priority', Number(e.target.value))}
                    min={0}
                    max={9999}
                    disabled={saving}
                  />
                  <span className="rules-field-hint">{t.rulesFieldPriorityHint}</span>
                </div>
              </div>
            </div>

            {/* ── ② Conditions ────────────────────────────────────────────── */}
            <button
              type="button"
              className="rules-section-heading"
              aria-expanded={open.conditions}
              onClick={() => toggleSection('conditions')}
            >
              <span>{t.rulesSectionMatch}</span>
              <span className="rules-section-chevron" aria-hidden="true">
                {open.conditions ? <IconChevronDown size={14} /> : <IconChevronRight size={14} />}
              </span>
            </button>
            <div className="rules-section" style={open.conditions ? undefined : { display: 'none' }}>

              {/* Sub-block: Title / description (required) */}
              <div className="rules-condition-block">
                <div className="rules-condition-label">
                  {t.rulesConditionTitle} <span className="rules-required">*</span>
                </div>
                <div className="rules-form-grid">
                  <div className="rules-field-group">
                    <label className="rules-label">{t.rulesFieldDescMode}</label>
                    <select
                      className="form-input"
                      value={form.description_mode}
                      onChange={e => patchForm('description_mode', e.target.value as DescriptionMode)}
                      disabled={saving}
                    >
                      <option value="contains">{t.rulesModeContains}</option>
                      <option value="starts_with">{t.rulesModeStartsWith}</option>
                      <option value="exact">{t.rulesModeExact}</option>
                      <option value="regex">{t.rulesModeRegex}</option>
                    </select>
                  </div>
                  <div className="rules-field-group">
                    <label className="rules-label">{t.rulesFieldDescValue} *</label>
                    <input
                      type="text"
                      className="form-input"
                      value={form.description_value}
                      onChange={e => patchForm('description_value', e.target.value)}
                      placeholder={t.rulesFieldDescValuePlaceholder}
                      disabled={saving}
                    />
                  </div>
                </div>
              </div>

              {/* Sub-block: Detail (optional inset card) */}
              <div className="rules-optional-block">
                <div className="rules-condition-label">{t.rulesFieldDetailLabel}</div>
                <div className="rules-form-grid">
                  <div className="rules-field-group">
                    <label className="rules-label">{t.rulesFieldDescMode}</label>
                    <select
                      className="form-input"
                      value={form.detail_mode}
                      onChange={e => patchForm('detail_mode', e.target.value as DescriptionMode)}
                      disabled={saving}
                    >
                      <option value="contains">{t.rulesModeContains}</option>
                      <option value="starts_with">{t.rulesModeStartsWith}</option>
                      <option value="exact">{t.rulesModeExact}</option>
                      <option value="regex">{t.rulesModeRegex}</option>
                    </select>
                  </div>
                  <div className="rules-field-group">
                    <label className="rules-label">{t.rulesFieldDescValue}</label>
                    <input
                      type="text"
                      className="form-input"
                      value={form.detail_value}
                      onChange={e => patchForm('detail_value', e.target.value)}
                      placeholder={t.rulesFieldDetailValuePlaceholder}
                      disabled={saving}
                    />
                  </div>
                </div>
                <span className="rules-field-hint">{t.rulesFieldDetailHint}</span>
              </div>

              {/* Sub-block: Narrow filters */}
              <div className="rules-condition-block">
                <div className="rules-condition-label">{t.rulesConditionFilters}</div>
                <div className="rules-form-grid">
                  <div className="rules-field-group">
                    <label className="rules-label">{t.rulesFieldAmountSign}</label>
                    <select
                      className="form-input"
                      value={form.amount_sign ?? ''}
                      onChange={e => patchForm('amount_sign', (e.target.value || null) as AmountSign | null)}
                      disabled={saving}
                    >
                      <option value="">{t.rulesFieldAmountAny}</option>
                      <option value="negative">{t.rulesFieldAmountExpense}</option>
                      <option value="positive">{t.rulesFieldAmountIncome}</option>
                    </select>
                  </div>
                  <div className="rules-field-group">
                    <label className="rules-label">{t.rulesFieldAmountMin}</label>
                    <input
                      type="number"
                      className="form-input"
                      value={form.amount_min}
                      onChange={e => patchForm('amount_min', e.target.value)}
                      placeholder="0"
                      min={0}
                      step="any"
                      disabled={saving}
                    />
                  </div>
                  <div className="rules-field-group">
                    <label className="rules-label">{t.rulesFieldAmountMax}</label>
                    <input
                      type="number"
                      className="form-input"
                      value={form.amount_max}
                      onChange={e => patchForm('amount_max', e.target.value)}
                      placeholder="—"
                      min={0}
                      step="any"
                      disabled={saving}
                    />
                    <span className="rules-field-hint">{t.rulesFieldAmountHint}</span>
                  </div>
                  <div className="rules-field-group">
                    <label className="rules-label">{t.rulesFieldAccount}</label>
                    <input
                      type="text"
                      className="form-input"
                      value={form.account_ref}
                      onChange={e => patchForm('account_ref', e.target.value)}
                      placeholder={t.rulesFieldAccountPlaceholder}
                      disabled={saving}
                    />
                  </div>
                  <div className="rules-field-group">
                    <label className="rules-label">{t.rulesFieldCurrency}</label>
                    <input
                      type="text"
                      className="form-input"
                      value={form.currency}
                      onChange={e => patchForm('currency', e.target.value)}
                      placeholder={t.rulesFieldCurrencyPlaceholder}
                      maxLength={3}
                      disabled={saving}
                    />
                  </div>
                </div>
              </div>

            </div>

            {/* ── ③ Actions ───────────────────────────────────────────────── */}
            <button
              type="button"
              className="rules-section-heading"
              aria-expanded={open.actions}
              onClick={() => toggleSection('actions')}
            >
              <span>{t.rulesSectionActions}</span>
              <span className="rules-section-chevron" aria-hidden="true">
                {open.actions ? <IconChevronDown size={14} /> : <IconChevronRight size={14} />}
              </span>
            </button>
            <div className="rules-section" style={open.actions ? undefined : { display: 'none' }}>
              <div className="rules-form-grid">
                <div className="rules-field-group rules-span-2">
                  <label className="rules-label">
                    {t.rulesFieldCategory}
                    {form.skip_ai && <span className="rules-required"> *</span>}
                  </label>
                  <CategorySelect
                    value={form.set_category}
                    baseCategories={baseCategories}
                    extraCategories={extraCategories}
                    lang={lang}
                    t={t}
                    onChange={v => patchForm('set_category', v)}
                  />
                </div>
                <div className="rules-field-group">
                  <label className="rules-label">{t.rulesFieldMerchant}</label>
                  <input
                    type="text"
                    className="form-input"
                    value={form.set_merchant}
                    onChange={e => patchForm('set_merchant', e.target.value)}
                    placeholder={t.rulesFieldMerchantPlaceholder}
                    disabled={saving}
                  />
                </div>
                <div className="rules-field-group">
                  <label className="rules-label">{t.rulesFieldSkipAi}</label>
                  <div className="rules-toggle-row">
                    <input
                      type="checkbox"
                      className="rules-checkbox"
                      id="rfm-skip-ai"
                      checked={form.skip_ai}
                      onChange={e => patchForm('skip_ai', e.target.checked)}
                      disabled={saving}
                    />
                    <label htmlFor="rfm-skip-ai" className="rules-toggle-label">
                      {form.skip_ai ? <IconCheck size={14} /> : '—'}
                    </label>
                  </div>
                  <span className="rules-field-hint">{t.rulesFieldSkipAiHint}</span>
                </div>
                <div className="rules-field-group rules-span-2">
                  <label className="rules-label">{t.rulesFieldTags}</label>
                  <TagTypeahead
                    tags={form.add_tags}
                    availableTags={availableTags}
                    suggestedColors={{}}
                    onChange={tags => patchForm('add_tags', tags)}
                    placeholder={t.tagTypeaheadPlaceholder}
                  />
                </div>
              </div>
            </div>

          </div>
        </div>

        <div className="modal-footer">
          {/* ── Left: loading / error / none hint ────────────── */}
          <div className="rule-preview-bar">
            {applyToast ? (
              <span className="rule-preview-text rule-preview-text--ok">{applyToast}</span>
            ) : !conditionsEmpty ? (
              previewLoading ? (
                <span className="rule-preview-text rule-preview-text--loading">{t.rulesPreviewLoading}</span>
              ) : previewErr ? (
                <span className="rule-preview-text rule-preview-text--error">{t.rulesPreviewError}</span>
              ) : previewCount === 0 ? (
                <span className="rule-preview-text rule-preview-text--none">{t.rulesPreviewNone}</span>
              ) : null
            ) : null}
          </div>

          {/* ── Apply-on-save checkbox ────────────────────────── */}
          {!conditionsEmpty && !previewLoading && previewCount !== null && previewCount > 0 && (
            <label className="rules-apply-checkbox-label">
              <input
                type="checkbox"
                className="rules-checkbox"
                checked={applyOnSave}
                onChange={e => setApplyOnSave(e.target.checked)}
                disabled={saving || applying}
              />
              {t.rulesApplyCheckbox(previewCount)}
            </label>
          )}

          <button type="button" className="btn-secondary" onClick={onClose} disabled={saving || applying}>
            {t.rulesBtnCancel}
          </button>
          <button type="button" className="btn-primary" onClick={handleSave} disabled={saving || applying}>
            {saving || applying ? '…' : applyOnSave ? t.rulesBtnSaveAndApply : t.rulesBtnSave}
          </button>
        </div>

      </div>
    </div>
  )
}
