import { useState, useEffect, useRef } from 'react'
import type { Account } from '../api/types'
import { getAccounts, deleteAccount } from '../api/client'
import { useT } from '../i18n'

export default function AccountsPage() {
  const { t } = useT()
  const [accounts, setAccounts] = useState<Account[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)

  const [deleteTarget, setDeleteTarget] = useState<Account | null>(null)
  const [deleting, setDeleting] = useState(false)

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

  return (
    <>
      <div className="card settings-card">
        <h2 className="settings-section-title">{t.accountsPageTitle}</h2>

        {error && <div className="import-error" style={{ marginBottom: 16 }}>{error}</div>}

        {loading ? (
          <div className="state-box">
            <span className="icon">⏳</span>
            <span>{t.loading}</span>
          </div>
        ) : accounts.length === 0 ? (
          <div className="state-box">
            <span className="icon">🏦</span>
            <span>{t.accountsEmpty}</span>
          </div>
        ) : (
          <div className="settings-cats-list">
            {accounts.map(account => (
              <div key={account.id} className="settings-cat-row">
                <span className="settings-cat-label">{account.name}</span>
                <span className="settings-count">{t.settingsCountLabel(account.tx_count)}</span>
                <div className="settings-cat-actions">
                  <button
                    className="btn-row-icon btn-row-delete"
                    onClick={() => setDeleteTarget(account)}
                    title={t.accountsDeleteBtn}
                    aria-label={t.accountsDeleteBtn}
                  >🗑</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

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
          >✕</button>
        </div>

        <div className="modal-body">
          <p style={{ fontSize: 14, lineHeight: 1.65, color: 'var(--text)', margin: 0 }}>
            {t.accountsDeleteBody(account.name, account.tx_count)}
          </p>
        </div>

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
            {t.accountsDeleteOk}
          </button>
        </div>
      </div>
    </div>
  )
}
