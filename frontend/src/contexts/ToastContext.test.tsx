import { StrictMode, useState } from 'react'
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider, useToast } from './ToastContext'
import Modal from '../components/Modal'
import es from '../i18n/es'

function Trigger() {
  const showToast = useToast()
  return (
    <>
      <button type="button" onClick={() => showToast('First message')}>First</button>
      <button type="button" onClick={() => showToast('Second message')}>Second</button>
    </>
  )
}

beforeEach(() => vi.useFakeTimers())
afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe('ToastProvider', () => {
  it('announces messages in a persistent status region', () => {
    render(<ToastProvider><Trigger /></ToastProvider>)
    const status = screen.getByRole('status')
    expect(status).toBeEmptyDOMElement()
    fireEvent.click(screen.getByRole('button', { name: 'First' }))
    expect(screen.getByRole('status')).toBe(status)
    expect(status).toHaveTextContent('First message')
  })

  it('automatically dismisses a message after six seconds', () => {
    render(<ToastProvider><Trigger /></ToastProvider>)
    fireEvent.click(screen.getByRole('button', { name: 'First' }))
    act(() => vi.advanceTimersByTime(5999))
    expect(screen.getByRole('status')).toHaveTextContent('First message')
    act(() => vi.advanceTimersByTime(1))
    expect(screen.getByRole('status')).toBeEmptyDOMElement()
  })

  it.each(['First', 'Second'])('replaces the message and restarts its timer with %s', replacement => {
    render(<ToastProvider><Trigger /></ToastProvider>)
    fireEvent.click(screen.getByRole('button', { name: 'First' }))
    act(() => vi.advanceTimersByTime(3000))
    fireEvent.click(screen.getByRole('button', { name: replacement }))
    expect(vi.getTimerCount()).toBe(1)
    act(() => vi.advanceTimersByTime(3000))
    expect(screen.getByRole('status')).toHaveTextContent(`${replacement} message`)
    act(() => vi.advanceTimersByTime(3000))
    expect(screen.getByRole('status')).toBeEmptyDOMElement()
  })

  it('clears the timer on manual dismissal', () => {
    render(<ToastProvider><Trigger /></ToastProvider>)
    fireEvent.click(screen.getByRole('button', { name: 'First' }))
    fireEvent.click(screen.getByRole('button', { name: es.toastClose }))
    expect(screen.getByRole('status')).toBeEmptyDOMElement()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('clears the timer and removes the portal on unmount', () => {
    const { unmount } = render(<ToastProvider><Trigger /></ToastProvider>)
    fireEvent.click(screen.getByRole('button', { name: 'First' }))
    expect(vi.getTimerCount()).toBe(1)
    unmount()
    expect(vi.getTimerCount()).toBe(0)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('keeps toasts inside the active dialog and restores the host as dialogs close', () => {
    function NestedDialogs() {
      const [outer, setOuter] = useState(true)
      const [inner, setInner] = useState(true)
      return outer && (
        <Modal label="Outer" onDismiss={() => setOuter(false)}>
          {inner && (
            <Modal label="Inner" onDismiss={() => setInner(false)}>
              <Trigger />
            </Modal>
          )}
        </Modal>
      )
    }
    render(<StrictMode><ToastProvider><NestedDialogs /></ToastProvider></StrictMode>)
    const inner = screen.getByRole('dialog', { name: 'Inner' })
    fireEvent.click(within(inner).getByRole('button', { name: 'First' }))
    expect(screen.getByRole('status').closest('dialog')).toBe(inner)
    act(() => vi.advanceTimersByTime(2000))
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.getByRole('status').closest('dialog')).toBe(screen.getByRole('dialog', { name: 'Outer' }))
    act(() => vi.advanceTimersByTime(2000))
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.getByRole('status').closest('dialog')).toBeNull()
    act(() => vi.advanceTimersByTime(2000))
    expect(screen.getByRole('status')).toBeEmptyDOMElement()
  })
})
