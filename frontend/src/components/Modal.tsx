import { useCallback, useLayoutEffect, useRef, type ReactNode } from 'react'
import { useModalToastHost } from '../contexts/ToastContext'

interface ModalProps {
  onDismiss: () => void
  /** Ignores Escape and backdrop clicks, e.g. while a save is in flight. */
  disabled?: boolean
  labelledBy?: string
  label?: string
  /** Extra classes for the `.modal` box. */
  className?: string
  children: ReactNode
}

/**
 * A modal on the native `<dialog>`, opened with `showModal()`: the browser makes the rest of
 * the page inert, keeps focus inside, draws it in the top layer and hands focus back when it
 * closes. Mount it to open it, unmount it to close it.
 *
 * It dismisses on Escape, or on a click that both starts and ends on its backdrop. A plain
 * `onClick` is not enough: a text selection dragged out of an input and released outside the
 * box dispatches its click on the dialog — their common ancestor — and threw the whole form
 * away. An Escape that an inner widget already claimed with `preventDefault()` (an open date
 * picker, say) is left to that widget instead of closing the modal.
 */
export default function Modal({ onDismiss, disabled = false, labelledBy, label, className, children }: ModalProps) {
  const registerToastHost = useModalToastHost()
  const dialogRef = useRef<HTMLDialogElement>(null)
  const onDismissRef = useRef(onDismiss)
  const disabledRef = useRef(disabled)
  const openerRef = useRef<Element | null>(null)
  const lastFocusedInsideRef = useRef<HTMLElement | null>(null)
  const pressedOnBackdrop = useRef(false)
  const releasedOnBackdrop = useRef(false)

  useLayoutEffect(() => {
    onDismissRef.current = onDismiss
    disabledRef.current = disabled
  })

  // The ref of the dialog's first child runs before any descendant's autoFocus, which would
  // otherwise lose to showModal() focusing the first focusable element.
  const openOnMount = useCallback((node: HTMLSpanElement | null) => {
    const dialog = node?.parentElement
    if (!(dialog instanceof HTMLDialogElement)) return
    if (!dialog.open) {
      openerRef.current = document.activeElement
      dialog.showModal()
      // StrictMode reopens the dialog without re-running autoFocus.
      const last = lastFocusedInsideRef.current
      if (last?.isConnected && dialog.contains(last)) last.focus()
    }
    return registerToastHost?.(dialog)
  }, [registerToastHost])

  useLayoutEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    lastFocusedInsideRef.current = null
    const dismiss = () => {
      if (!disabledRef.current) onDismissRef.current()
    }
    // Native listeners: React's onCancel/onClose would also reach an enclosing Modal.
    const onCancel = (e: Event) => {
      if (!e.cancelable) return
      e.preventDefault()
      dismiss()
    }
    // A repeated Escape without user activation cannot be cancelled and closes the dialog
    // anyway. Reopen it, so a disabled or declined dismissal leaves the modal in place. An
    // open dialog here means this is the stale event of a StrictMode remount's own close().
    const onClose = () => {
      if (dialog.open || !dialog.isConnected) return
      dialog.showModal()
      dismiss()
    }
    dialog.addEventListener('cancel', onCancel)
    dialog.addEventListener('close', onClose)
    return () => {
      dialog.removeEventListener('cancel', onCancel)
      dialog.removeEventListener('close', onClose)
      const active = document.activeElement
      if (active instanceof HTMLElement && dialog.contains(active)) lastFocusedInsideRef.current = active
      dialog.close()
      const opener = openerRef.current
      const focused = document.activeElement
      if (
        opener instanceof HTMLElement && opener.isConnected
        && (!focused || focused === document.body || dialog.contains(focused))
      ) {
        opener.focus({ preventScroll: true })
      }
    }
  }, [])

  return (
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-noninteractive-element-interactions -- Escape reaches the dialog as its native cancel event; the click only detects the backdrop
    <dialog
      ref={dialogRef}
      className="modal-dialog"
      aria-labelledby={labelledBy}
      aria-label={label}
      onPointerDown={e => { pressedOnBackdrop.current = e.target === e.currentTarget }}
      onPointerUp={e => { releasedOnBackdrop.current = e.target === e.currentTarget }}
      onClick={e => {
        const onBackdrop = pressedOnBackdrop.current && releasedOnBackdrop.current
        pressedOnBackdrop.current = false
        releasedOnBackdrop.current = false
        if (onBackdrop && e.target === e.currentTarget && !disabled) onDismiss()
      }}
    >
      <span ref={openOnMount} hidden />
      <div className={className ? `modal ${className}` : 'modal'}>{children}</div>
    </dialog>
  )
}
