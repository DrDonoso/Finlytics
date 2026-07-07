import { useState, useMemo } from 'react'
import type { Rule, RuleInput, DescriptionMode, AmountSign, Category, Tag } from '../api/types'
import { createRule, updateRule } from '../api/client'
import { useT, categoryLabel } from '../i18n'
import CategorySelect from './CategorySelect'
import TagTypeahead from './TagTypeahead'

interface FormState {
  name: string
  priority: number
  enabled: boolean
  description_mode: DescriptionMode
  description_value: string
  amount_sign: AmountSign | null
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
  amount_sign: null,
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
        amount_sign: editingRule.amount_sign,
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
        amount_sign:       initialValues.amount_sign       ?? DEFAULT_FORM.amount_sign,
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
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

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
    return null
  }

  async function handleSave() {
    const validErr = validate()
    if (validErr) { setFormError(validErr); return }

    setSaving(true)
    setFormError(null)

    const payload: RuleInput = {
      name:              form.name.trim(),
      priority:          form.priority,
      enabled:           form.enabled,
      description_mode:  form.description_mode,
      description_value: form.description_value.trim(),
      amount_sign:       form.amount_sign,
      account_ref:       form.account_ref.trim()    || null,
      currency:          form.currency.trim()        || null,
      set_category:      form.set_category.trim()   || null,
      set_merchant:      form.set_merchant.trim()   || null,
      add_tags:          form.add_tags,
      skip_ai:           form.skip_ai,
    }
    try {
      const result = editingRule !== undefined
        ? await updateRule(editingRule.id, payload)
        : await createRule(payload)
      onSave(result)
    } catch (e) {
      setFormError(String(e))
    } finally {
      setSaving(false)
    }
  }

  const title = editingRule ? t.rulesEditTitle : t.rulesAddTitle

  return (
    <div className="modal-backdrop modal-backdrop-rule">
      <div className="modal modal-rule-form" role="dialog" aria-modal="true" aria-labelledby="rfm-title">

        <div className="modal-header">
          <h2 className="modal-title" id="rfm-title">{title}</h2>
          <button className="modal-close" onClick={onClose} disabled={saving} aria-label={t.modalClose}>✕</button>
        </div>

        <div className="modal-body">
          {formError && (
            <div className="import-error" style={{ marginBottom: 12 }}>{formError}</div>
          )}

          <div className="rules-form-grid">
            {/* Name */}
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

            {/* Description mode */}
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

            {/* Description value */}
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

            {/* Set category */}
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

            {/* Set merchant */}
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

            {/* Priority */}
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

            {/* Amount sign */}
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

            {/* Account ref */}
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

            {/* Currency */}
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

            {/* Add tags */}
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

            {/* Enabled */}
            <div className="rules-field-group">
              <label className="rules-label">{t.rulesFieldEnabled}</label>
              <div className="rules-toggle-row">
                <input
                  type="checkbox"
                  className="rules-checkbox"
                  id="rfm-enabled"
                  checked={form.enabled}
                  onChange={e => patchForm('enabled', e.target.checked)}
                  disabled={saving}
                />
                <label htmlFor="rfm-enabled" className="rules-toggle-label">
                  {form.enabled ? '✓' : '—'}
                </label>
              </div>
            </div>

            {/* Skip AI */}
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
                  {form.skip_ai ? '✓' : '—'}
                </label>
              </div>
              <span className="rules-field-hint">{t.rulesFieldSkipAiHint}</span>
            </div>
          </div>
        </div>

        <div className="modal-footer">
          <button type="button" className="btn-secondary" onClick={onClose} disabled={saving}>
            {t.rulesBtnCancel}
          </button>
          <button type="button" className="btn-primary" onClick={handleSave} disabled={saving}>
            {saving ? '…' : t.rulesBtnSave}
          </button>
        </div>

      </div>
    </div>
  )
}
