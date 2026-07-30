import { useState, useEffect, useRef } from 'react'
import type { Account, AccountCreatePayload } from '../api/types'
import { getAccounts, deleteAccount, patchAccount, createAccount } from '../api/client'
import { useT } from '../i18n'
import { IconLoading, IconBank, IconPencil, IconTrash, IconClose, IconChevronDown, IconChevronRight } from '../components/icons'

export default function AccountsPage() {
  const { t } = useT()
  const [accounts, setAccounts] = useState<Account[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)

  const [deleteTarget, setDeleteTarget] = useState<Account | null>(null)
  const [deleting, setDeleting] = useState(false)

  const [editTarget, setEditTarget] = useState<Account | null>(null)
  const [editName,   setEditName]   = useState('')
  const [editSaving, setEditSaving] = useState(false)

  const [createOpen, setCreateOpen] = useState(false)

  useEffect(() => {
    setLoading(true)
    getAccounts()
      .then(data => { setAccounts(data); setLoading(false) })
      .catch(e => { setError(String(e)); setLoading(false) })
  }, [])

  function showToast(msg: string) {
    setToast(msg)
    setTimeout(() => setToast(null), 6000)
  }

  async function handleDeleteConfirm() {
    if (!deleteTarget) return
    const target = deleteTarget
    setDeleting(true)
    try {
      const result = await deleteAccount(target.id)
      setAccounts(prev => prev.filter(a => a.id !== target.id))
      setDeleteTarget(null)
      showToast(t.accountsDeleteToast(target.name, result.deleted))
    } catch (e) {
      setError(String(e))
    } finally {
      setDeleting(false)
    }
  }

  async function handleEditSave() {
    if (!editTarget || !editName.trim()) return
    setEditSaving(true)
    try {
      const updated = await patchAccount(editTarget.id, editName.trim())
      setAccounts(prev => prev.map(a => a.id === updated.id ? updated : a))
      setEditTarget(null)
      showToast(t.accountsEditToast(updated.name))
    } catch (e) {
      setError(String(e))
    } finally {
      setEditSaving(false)
    }
  }

  function handleCreateSuccess(account: Account) {
    setCreateOpen(false)
    setAccounts(prev => [...prev, account])
    showToast(t.accountsCreateToast(account.name))
  }

  return (
    <>
      <div className="card settings-card">
        <h2 className="settings-section-title">{t.accountsPageTitle}</h2>

        {error && <div className="import-error" style={{ marginBottom: 16 }}>{error}</div>}

        <div className="settings-add-form">
          <button className="btn-primary" type="button" onClick={() => setCreateOpen(true)}>
            {t.accountsCreateBtn}
          </button>
        </div>

        {loading ? (
          <div className="state-box">
            <IconLoading size={18} />
            <span>{t.loading}</span>
          </div>
        ) : accounts.length === 0 ? (
          <div className="state-box">
            <IconBank size={18} />
            <span>{t.accountsEmpty}</span>
          </div>
        ) : (
          <div className="settings-cats-list">
            {accounts.map(account => (
              <div key={account.id} className="settings-cat-row">
                <div className="settings-cat-label">
                  <span>{account.name}</span>
                  {account.account_number_masked && (
                    <span className="acct-number-chip">{account.account_number_masked}</span>
                  )}
                </div>
                <span className="settings-count">{t.settingsCountLabel(account.tx_count)}</span>
                <div className="settings-cat-actions">
                  <button
                    className="btn-row-icon"
                    onClick={() => { setEditTarget(account); setEditName(account.name) }}
                    title={t.accountsEditBtn}
                    aria-label={t.accountsEditBtn}
                  ><IconPencil size={15} /></button>
                  <button
                    className="btn-row-icon btn-row-delete"
                    onClick={() => setDeleteTarget(account)}
                    title={t.accountsDeleteBtn}
                    aria-label={t.accountsDeleteBtn}
                  ><IconTrash size={15} /></button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {createOpen && (
        <AccountCreateModal
          onSuccess={handleCreateSuccess}
          onCancel={() => setCreateOpen(false)}
        />
      )}

      {editTarget && (
        <AccountEditModal
          account={editTarget}
          name={editName}
          saving={editSaving}
          onChangeName={setEditName}
          onConfirm={handleEditSave}
          onCancel={() => { if (!editSaving) setEditTarget(null) }}
        />
      )}

      {deleteTarget && (
        <AccountDeleteModal
          account={deleteTarget}
          deleting={deleting}
          onConfirm={handleDeleteConfirm}
          onCancel={() => { if (!deleting) setDeleteTarget(null) }}
        />
      )}

      {toast && (
        <div className="toast" role="status">
          {toast}
          <button type="button" className="toast-close" onClick={() => setToast(null)}>
            {t.toastClose}
          </button>
        </div>
      )}
    </>
  )
}

// ── Create account modal ───────────────────────────────────────────────────────

interface CreateModalProps {
  onSuccess: (account: Account) => void
  onCancel: () => void
}

function AccountCreateModal({ onSuccess, onCancel }: CreateModalProps) {
  const { t } = useT()
  const nameRef = useRef<HTMLInputElement>(null)

  const [name, setName] = useState('')
  const [type, setType] = useState('bank')
  const [currency, setCurrency] = useState('EUR')
  const [iban, setIban] = useState('')
  const [showOpening, setShowOpening] = useState(false)
  const [amount, setAmount] = useState('')
  const [date, setDate] = useState('')
  const [saving, setSaving] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)
  const [attempted, setAttempted] = useState(false)

  const nameValid = name.trim().length > 0
  const hasAmount = amount.trim() !== '' && !isNaN(parseFloat(amount))
  const dateValid = !hasAmount || date.trim() !== ''

  useEffect(() => { nameRef.current?.focus() }, [])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape' && !saving) onCancel()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [saving, onCancel])

  async function handleConfirm() {
    setAttempted(true)
    if (!nameValid || !dateValid) return
    setSaving(true)
    setServerError(null)

    const payload: AccountCreatePayload = {
      name: name.trim(),
      type,
      currency: currency.trim() || 'EUR',
      account_number: iban.trim() || null,
      opening_balance: hasAmount ? parseFloat(amount) : null,
      opening_date: date.trim() || null,
    }

    try {
      const account = await createAccount(payload)
      onSuccess(account)
    } catch (e) {
      const err = e as { status?: number }
      if (err.status === 409) {
        setServerError(t.accountsCreateErr409)
      } else if (err.status === 422) {
        setServerError(t.accountsCreateErrDate)
      } else {
        setServerError(String(e))
      }
      setSaving(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={() => { if (!saving) onCancel() }}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="acct-create-title"
        onClick={e => e.stopPropagation()}
      >
        <div className="modal-header">
          <span className="modal-title" id="acct-create-title">
            {t.accountsCreateTitle}
          </span>
          <button
            className="modal-close"
            type="button"
            aria-label={t.modalClose}
            onClick={onCancel}
            disabled={saving}
          ><IconClose size={16} /></button>
        </div>

        <div className="modal-body">
          {serverError && (
            <div className="import-error" style={{ marginBottom: 14 }}>{serverError}</div>
          )}

          <div className="acct-create-form">
            {/* Nombre */}
            <div className="form-group">
              <label htmlFor="acct-create-name">
                {t.accountsCreateLabelName} <span className="rules-required">*</span>
              </label>
              <input
                ref={nameRef}
                id="acct-create-name"
                type="text"
                className={`form-input${attempted && !nameValid ? ' form-input--error' : ''}`}
                value={name}
                onChange={e => setName(e.target.value)}
                disabled={saving}
              />
              {attempted && !nameValid && (
                <span className="form-field-error">{t.accountsCreateErrName}</span>
              )}
            </div>

            {/* Tipo */}
            <div className="form-group">
              <label htmlFor="acct-create-type">{t.accountsCreateLabelType}</label>
              <select
                id="acct-create-type"
                className="form-input"
                value={type}
                onChange={e => setType(e.target.value)}
                disabled={saving}
              >
                <option value="bank">{t.accountsCreateTypeBank}</option>
                <option value="broker">{t.accountsCreateTypeBroker}</option>
                <option value="savings">{t.accountsCreateTypeSavings}</option>
              </select>
            </div>

            {/* Moneda */}
            <div className="form-group">
              <label htmlFor="acct-create-currency">{t.accountsCreateLabelCurrency}</label>
              <input
                id="acct-create-currency"
                type="text"
                className="form-input"
                value={currency}
                onChange={e => setCurrency(e.target.value.toUpperCase())}
                maxLength={3}
                disabled={saving}
              />
            </div>

            {/* Nº cuenta / IBAN */}
            <div className="form-group">
              <label htmlFor="acct-create-iban">{t.accountsCreateLabelIban}</label>
              <input
                id="acct-create-iban"
                type="text"
                className="form-input"
                value={iban}
                onChange={e => setIban(e.target.value)}
                disabled={saving}
              />
            </div>

            {/* Saldo inicial — collapsible */}
            <div>
              <button
                type="button"
                className="acct-opening-toggle-btn"
                onClick={() => setShowOpening(v => !v)}
                disabled={saving}
                aria-expanded={showOpening}
              >
                {showOpening ? <IconChevronDown size={13} /> : <IconChevronRight size={13} />}
                {t.accountsCreateOpeningTitle}
              </button>

              {showOpening && (
                <div className="acct-opening-section">
                  <p className="form-hint">{t.accountsCreateOpeningHint}</p>

                  {/* Importe */}
                  <div className="form-group">
                    <label htmlFor="acct-create-amount">{t.accountsCreateLabelAmount}</label>
                    <input
                      id="acct-create-amount"
                      type="number"
                      step="0.01"
                      className="form-input"
                      value={amount}
                      onChange={e => setAmount(e.target.value)}
                      disabled={saving}
                    />
                  </div>

                  {/* Fecha del saldo */}
                  <div className="form-group">
                    <label htmlFor="acct-create-date">
                      {t.accountsCreateLabelDate}
                      {hasAmount && <span className="rules-required"> *</span>}
                    </label>
                    <input
                      id="acct-create-date"
                      type="date"
                      className={`form-input${attempted && !dateValid ? ' form-input--error' : ''}`}
                      value={date}
                      onChange={e => setDate(e.target.value)}
                      disabled={saving}
                    />
                    {attempted && !dateValid && (
                      <span className="form-field-error">{t.accountsCreateErrDate}</span>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="modal-footer">
          <button
            type="button"
            className="btn-secondary"
            onClick={onCancel}
            disabled={saving}
          >
            {t.modalBtnCancel}
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={handleConfirm}
            disabled={saving}
          >
            {saving && <span className="btn-spinner" aria-hidden="true" />}
            {t.accountsCreateSubmit}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Edit name modal ────────────────────────────────────────────────────────────

interface EditModalProps {
  account: Account
  name: string
  saving: boolean
  onChangeName: (v: string) => void
  onConfirm: () => void
  onCancel: () => void
}

function AccountEditModal({ account, name, saving, onChangeName, onConfirm, onCancel }: EditModalProps) {
  const { t } = useT()
  const inputRef = useRef<HTMLInputElement>(null)
  const [attempted, setAttempted] = useState(false)
  const nameValid = name.trim().length > 0

  useEffect(() => { inputRef.current?.focus() }, [])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape' && !saving) onCancel()
      if (e.key === 'Enter' && !saving) { setAttempted(true); if (nameValid) onConfirm() }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [saving, nameValid, onCancel, onConfirm])

  function handleConfirm() {
    setAttempted(true)
    if (!nameValid) return
    onConfirm()
  }

  return (
    <div className="modal-backdrop" onClick={() => { if (!saving) onCancel() }}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="acct-edit-title"
        onClick={e => e.stopPropagation()}
      >
        <div className="modal-header">
          <span className="modal-title" id="acct-edit-title">
            {t.accountsEditTitle(account.name)}
          </span>
          <button
            className="modal-close"
            type="button"
            aria-label={t.modalClose}
            onClick={onCancel}
            disabled={saving}
          ><IconClose size={16} /></button>
        </div>

        <div className="modal-body">
          <div className="form-group">
            <label htmlFor="acct-edit-name">
              {t.accountsEditLabel} <span className="rules-required">*</span>
            </label>
            <input
              ref={inputRef}
              id="acct-edit-name"
              type="text"
              className={`form-input${attempted && !nameValid ? ' form-input--error' : ''}`}
              value={name}
              onChange={e => onChangeName(e.target.value)}
              disabled={saving}
            />
            {attempted && !nameValid && (
              <span className="form-field-error">{t.accountsEditNameRequired}</span>
            )}
            {account.account_number_masked && (
              <span className="form-hint">
                {account.account_number_masked}
              </span>
            )}
          </div>
        </div>

        <div className="modal-footer">
          <button
            type="button"
            className="btn-secondary"
            onClick={onCancel}
            disabled={saving}
          >
            {t.modalBtnCancel}
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={handleConfirm}
            disabled={saving || !nameValid}
          >
            {saving && <span className="btn-spinner" aria-hidden="true" />}
            {t.accountsEditSave}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Delete modal ───────────────────────────────────────────────────────────────

interface DeleteModalProps {
  account: Account
  deleting: boolean
  onConfirm: () => void
  onCancel: () => void
}

function AccountDeleteModal({ account, deleting, onConfirm, onCancel }: DeleteModalProps) {
  const { t } = useT()
  const cancelRef = useRef<HTMLButtonElement>(null)

  useEffect(() => { cancelRef.current?.focus() }, [])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape' && !deleting) onCancel()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [deleting, onCancel])

  return (
    <div
      className="modal-backdrop"
      onClick={() => { if (!deleting) onCancel() }}
    >
      <div
        className="modal stmt-delete-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="acct-delete-title"
        onClick={e => e.stopPropagation()}
      >
        <div className="modal-header">
          <span className="modal-title" id="acct-delete-title">
            {t.accountsDeleteTitle(account.name)}
          </span>
          <button
            className="modal-close"
            type="button"
            aria-label={t.modalClose}
            onClick={onCancel}
            disabled={deleting}
          ><IconClose size={16} /></button>
        </div>

        <div className="modal-body">
          <p style={{ fontSize: 14, lineHeight: 1.65, color: 'var(--text)', margin: 0 }}>
            {t.accountsDeleteBody(account.name, account.tx_count)}
          </p>        </div>

        <div className="modal-footer">
          <button
            ref={cancelRef}
            type="button"
            className="btn-secondary"
            onClick={onCancel}
            disabled={deleting}
          >
            {t.modalBtnCancel}
          </button>
          <button
            type="button"
            className="btn-danger"
            onClick={onConfirm}
            disabled={deleting}
          >
            {deleting && <span className="btn-spinner" aria-hidden="true" />}
            {!deleting && <IconTrash size={15} />}
            {t.accountsDeleteOk}
          </button>
        </div>
      </div>
    </div>
  )
}
