import { useState, useEffect } from 'react'
import type { Category, Tag, Transaction } from '../api/types'
import { updateTransaction } from '../api/client'
import { useT, categoryLabel, formatDate, DEFAULT_TAG_COLOR, tagTextColor } from '../i18n'
import CategorySelect from './CategorySelect'
import TagEditor from './TagEditor'
import { IconClose } from './icons'

interface EditData {
  description: string
  category: string
  sign: '-' | '+'
  absAmount: string
  tags: string[]
  merchant: string
}

interface Props {
  tx: Transaction
  sortedBaseCategories: Category[]
  dbExtraCategories: string[]
  allTags: Tag[]
  categoryColorMap: Record<string, string>
  dynamicEs: Record<string, string>
  onClose: () => void
  onSaved: (updated: Transaction) => void
}

export default function TransactionDetailModal({
  tx,
  sortedBaseCategories,
  dbExtraCategories,
  allTags,
  categoryColorMap,
  dynamicEs,
  onClose,
  onSaved,
}: Props) {
  const { t, lang, formatCurrency } = useT()

  const [editData, setEditData] = useState<EditData>({
    description: tx.description,
    category: tx.category,
    sign: tx.amount <= 0 ? '-' : '+',
    absAmount: String(Math.abs(tx.amount)),
    tags: tx.tags,
    merchant: tx.merchant ?? '',
  })
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  // Reset form when tx changes
  useEffect(() => {
    setEditData({
      description: tx.description,
      category: tx.category,
      sign: tx.amount <= 0 ? '-' : '+',
      absAmount: String(Math.abs(tx.amount)),
      tags: tx.tags,
      merchant: tx.merchant ?? '',
    })
    setSaveError(null)
  }, [tx.id]) // eslint-disable-line react-hooks/exhaustive-deps

  // Close on Escape
  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  async function handleSave() {
    setSaving(true)
    setSaveError(null)
    const signedAmount =
      editData.sign === '-'
        ? -Math.abs(Number(editData.absAmount))
        : Math.abs(Number(editData.absAmount))
    try {
      const updated = await updateTransaction(tx.id, {
        description: editData.description,
        category: editData.category,
        amount: signedAmount,
        tags: editData.tags,
        merchant: editData.merchant,
      })
      onSaved(updated)
    } catch (e) {
      setSaveError(t.tableSaveError)
    } finally {
      setSaving(false)
    }
  }

  const amountColor = editData.sign === '-' ? 'var(--expense)' : 'var(--income)'
  const catColor = categoryColorMap[editData.category]

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal modal-tx-detail"
        role="dialog"
        aria-modal="true"
        onClick={e => e.stopPropagation()}
      >
        <div className="modal-header">
          <h2 className="modal-title">{t.txDetailModalTitle}</h2>
          <button
            className="modal-close"
            onClick={onClose}
            disabled={saving}
            aria-label={t.modalClose}
          ><IconClose size={16} /></button>
        </div>

        <div className="modal-body tx-detail-body">
          {/* ── Read-only fields ─────────────────────────────────── */}
          <div className="tx-detail-field">
            <span className="tx-detail-label">{t.tableColDate}</span>
            <span className="tx-detail-value">{formatDate(tx.transaction_date, lang)}</span>
          </div>
          <div className="tx-detail-field">
            <span className="tx-detail-label">{t.tableColAccount}</span>
            <span className="tx-detail-value">{tx.account}</span>
          </div>

          {/* ── Editable: description ────────────────────────────── */}
          <div className="tx-detail-field tx-detail-field--editable">
            <label className="tx-detail-label">{t.tableColDesc}</label>
            <input
              type="text"
              className="td-edit-input"
              value={editData.description}
              disabled={saving}
              onChange={e => setEditData(d => ({ ...d, description: e.target.value }))}
            />
            {tx.detail && (
              <div className="tx-detail-subline-note">{tx.detail}</div>
            )}
          </div>

          {/* ── Editable: merchant ───────────────────────────────── */}
          <div className="tx-detail-field tx-detail-field--editable">
            <label className="tx-detail-label">{t.colMerchant}</label>
            <input
              type="text"
              className="td-edit-input"
              value={editData.merchant}
              disabled={saving}
              placeholder={t.colMerchant}
              onChange={e => setEditData(d => ({ ...d, merchant: e.target.value }))}
            />
          </div>

          {/* ── Editable: category ───────────────────────────────── */}
          <div className="tx-detail-field tx-detail-field--editable">
            <label className="tx-detail-label">{t.tableColCategory}</label>
            <div className="tx-detail-cat-row">
              {catColor && (
                <span
                  className="badge"
                  style={{
                    background: catColor + '22',
                    color: catColor,
                    borderColor: catColor + '66',
                  }}
                >
                  {categoryLabel(editData.category, lang, dynamicEs)}
                </span>
              )}
              <CategorySelect
                value={editData.category}
                baseCategories={sortedBaseCategories}
                extraCategories={dbExtraCategories}
                lang={lang}
                t={t}
                onChange={val => setEditData(d => ({ ...d, category: val }))}
              />
            </div>
          </div>

          {/* ── Editable: amount ─────────────────────────────────── */}
          <div className="tx-detail-field tx-detail-field--editable">
            <label className="tx-detail-label">{t.tableColAmount}</label>
            <div className="amount-cell">
              <select
                className="cell-sign"
                value={editData.sign}
                disabled={saving}
                onChange={e =>
                  setEditData(d => ({ ...d, sign: e.target.value as '-' | '+' }))
                }
              >
                <option value="-">{t.previewSignExpense}</option>
                <option value="+">{t.previewSignIncome}</option>
              </select>
              <input
                type="number"
                className="td-edit-input"
                style={{ color: amountColor, flex: 1 }}
                value={editData.absAmount}
                min="0"
                step="0.01"
                disabled={saving}
                onChange={e =>
                  setEditData(d => ({ ...d, absAmount: e.target.value }))
                }
              />
            </div>
          </div>

          {/* ── Editable: tags ───────────────────────────────────── */}
          <div className="tx-detail-field tx-detail-field--editable">
            <label className="tx-detail-label">{t.tableColTags}</label>
            <TagEditor
              tags={editData.tags}
              availableTags={allTags}
              disabled={saving}
              onChange={tags => setEditData(d => ({ ...d, tags }))}
              placeholder={t.tagEditorPlaceholder}
            />
          </div>

          {saveError && <div className="save-error" style={{ marginTop: 8 }}>{saveError}</div>}
        </div>

        <div className="modal-footer">
          <button className="btn-secondary" onClick={onClose} disabled={saving}>
            {t.tableCancelEdit}
          </button>
          <button className="btn-primary" onClick={handleSave} disabled={saving}>
            {t.tableSaveRow}
          </button>
        </div>
      </div>
    </div>
  )
}
