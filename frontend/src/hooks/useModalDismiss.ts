import { useEffect, useRef } from 'react'
import type { MouseEvent, PointerEvent } from 'react'

/**
 * Dismisses a modal on Escape, or on a click that both starts and ends on its
 * backdrop. Spread the result on the backdrop element.
 *
 * A plain `onClick` on the backdrop is not enough: a text selection dragged out
 * of an input and released outside the dialog dispatches its click on the
 * backdrop — their common ancestor — and threw the whole form away.
 *
 * Escape that an inner widget already claimed with `preventDefault()` (an open
 * date picker, say) is left to that widget instead of closing the modal.
 */
export function useModalDismiss(onDismiss: () => void, disabled = false) {
  const pressedOnBackdrop = useRef(false)
  const releasedOnBackdrop = useRef(false)

  useEffect(() => {
    if (disabled) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape' && !e.defaultPrevented) onDismiss()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [disabled, onDismiss])

  return {
    role: 'presentation' as const,
    onPointerDown: (e: PointerEvent<HTMLElement>) => {
      pressedOnBackdrop.current = e.target === e.currentTarget
    },
    onPointerUp: (e: PointerEvent<HTMLElement>) => {
      releasedOnBackdrop.current = e.target === e.currentTarget
    },
    onClick: (e: MouseEvent<HTMLElement>) => {
      const onBackdrop = pressedOnBackdrop.current && releasedOnBackdrop.current
      pressedOnBackdrop.current = false
      releasedOnBackdrop.current = false
      if (!disabled && onBackdrop && e.target === e.currentTarget) onDismiss()
    },
  }
}
