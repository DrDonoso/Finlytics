import { useRef, useEffect } from 'react'
import { useT } from '../i18n'
import { IconClose, IconTrash } from './icons'
import Modal from './Modal'

interface Props {
  monthLabel: string
  count: number
  deleting: boolean
  onConfirm: () => void
  onCancel: () => void
}

export default function StatementsDeleteModal({ monthLabel, count, deleting, onConfirm, onCancel }: Props) {
  const { t } = useT()
  const cancelRef = useRef<HTMLButtonElement>(null)

  // Focus cancel on open (safe initial focus)
  useEffect(() => { cancelRef.current?.focus() }, [])

  return (
    <Modal onDismiss={onCancel} disabled={deleting} labelledBy="stmt-delete-title" className="stmt-delete-modal">
      <div className="modal-header">
        <span className="modal-title" id="stmt-delete-title">
          {t.stmtsDeleteTitle(monthLabel)}
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
          {t.stmtsDeleteBody(count, monthLabel)}
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
          {!deleting && <IconTrash size={15} />}
          {t.stmtsDeleteBtn}
        </button>
      </div>
    </Modal>
  )
}
