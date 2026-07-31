/**
 * The slide-out assistant panel.
 *
 * Mounted from Layout so it is reachable from every route without each page
 * having to know about it. Rendered through a portal so the sidebar's stacking
 * context cannot trap it behind the page chrome.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

import {
  useAssistantConversation,
  useAssistantConversations,
  useAssistantSuggestions,
} from '../api/queries'
import type { AssistantMessage } from '../api/types'
import { useAssistant } from '../contexts/AssistantContext'
import { assistantSuggestion, assistantToolLabel, useT } from '../i18n'
import AssistantMessageView from './AssistantMessage'
import {
  IconChat, IconClose, IconPlus, IconSend, IconSparkles, IconSpinner, IconTrash,
} from './icons'

/** Id for the in-flight answer bubble. Zero can never be a real row id, and the
 *  optimistic user turns count downwards from -1, so it collides with neither. */
const STREAMING_MESSAGE_ID = 0

export default function AssistantPanel() {
  const { t } = useT()
  const {
    open, closePanel,
    conversationId, selectConversation, startNewConversation, removeConversation,
    pendingMessages, streamingAnswer, activeTools, sending, error, send, stop, clearError,
  } = useAssistant()

  const [draft, setDraft] = useState('')
  const [showThreads, setShowThreads] = useState(false)

  const panelRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const conversationsQuery = useAssistantConversations({ enabled: open })
  const suggestionsQuery = useAssistantSuggestions({ enabled: open })
  const conversationQuery = useAssistantConversation(conversationId, { enabled: open })

  const messages: AssistantMessage[] = useMemo(() => {
    const stored = conversationQuery.data?.messages ?? []
    // The server persists the question before it starts streaming, so the stored
    // copy can land while the optimistic one is still pending. Drop the
    // optimistic copy only when it is the LAST stored message: comparing against
    // the whole thread would hide a legitimately repeated question — the
    // suggestion chips send fixed strings — behind its own earlier copy.
    const last = stored[stored.length - 1]
    const pending = pendingMessages.filter(
      m => !(last !== undefined && last.role === m.role && last.content === m.content),
    )
    return [...stored, ...pending]
  }, [conversationQuery.data, pendingMessages])

  const suggestions = useMemo(() => {
    const keys = suggestionsQuery.data?.suggestions ?? []
    return keys
      .map(key => ({ key, text: assistantSuggestion(key, t) }))
      .filter((s): s is { key: string; text: string } => s.text !== null)
  }, [suggestionsQuery.data, t])

  // Esc closes, focus moves into the composer on open, and Tab is kept inside
  // the panel: it is aria-modal, so letting focus wander behind it would put
  // the keyboard user somewhere a screen reader says does not exist.
  useEffect(() => {
    if (!open) return

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        closePanel()
        return
      }
      if (e.key !== 'Tab' || panelRef.current === null) return

      const focusable = panelRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), textarea, input, a[href], [tabindex]:not([tabindex="-1"])',
      )
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]

      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    const timer = window.setTimeout(() => inputRef.current?.focus(), 50)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      window.clearTimeout(timer)
    }
  }, [open, closePanel])

  useEffect(() => {
    // Guarded rather than called directly: autoscroll is a nicety, and an
    // environment without scrollIntoView (jsdom, older engines) should not take
    // the whole panel down with it from inside an effect.
    bottomRef.current?.scrollIntoView?.({ block: 'end' })
  }, [messages.length, streamingAnswer, activeTools.length])

  if (!open) return null

  async function submit(text: string) {
    setDraft('')
    await send(text)
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    void submit(draft)
  }

  function onComposerKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    // Enter sends, Shift+Enter breaks the line — the convention every chat uses.
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void submit(draft)
    }
  }

  async function onDelete(id: number) {
    if (!window.confirm(t.assistantDeleteConfirm)) return
    await removeConversation(id)
  }

  const conversations = conversationsQuery.data ?? []
  const isEmptyThread = messages.length === 0 && !sending && streamingAnswer === ''

  return createPortal(
    <>
      <div className="assistant-overlay" onClick={closePanel} aria-hidden="true" />
      <aside
        className="assistant-panel"
        role="dialog"
        aria-modal="true"
        aria-label={t.assistantTitle}
        ref={panelRef}
      >
        <header className="assistant-header">
          <span className="assistant-header-title">
            <IconSparkles size={16} />
            {t.assistantTitle}
          </span>
          <div className="assistant-header-actions">
            <button
              type="button"
              className="assistant-icon-btn"
              onClick={() => setShowThreads(v => !v)}
              aria-expanded={showThreads}
              aria-label={t.assistantThreads}
              title={t.assistantThreads}
            >
              <IconChat size={15} />
            </button>
            <button
              type="button"
              className="assistant-icon-btn"
              onClick={() => { startNewConversation(); setShowThreads(false) }}
              aria-label={t.assistantNewChat}
              title={t.assistantNewChat}
            >
              <IconPlus size={15} />
            </button>
            <button
              type="button"
              className="assistant-icon-btn"
              onClick={closePanel}
              aria-label={t.assistantClose}
              title={t.assistantClose}
            >
              <IconClose size={15} />
            </button>
          </div>
        </header>

        {showThreads && (
          <div className="assistant-threads">
            {conversations.length === 0 ? (
              <p className="assistant-threads-empty">{t.assistantNoThreads}</p>
            ) : conversations.map(conversation => (
              <div
                key={conversation.id}
                className={`assistant-thread${conversation.id === conversationId ? ' active' : ''}`}
              >
                <button
                  type="button"
                  className="assistant-thread-btn"
                  onClick={() => { selectConversation(conversation.id); setShowThreads(false) }}
                >
                  {conversation.title || t.assistantUntitled}
                </button>
                <button
                  type="button"
                  className="assistant-icon-btn assistant-thread-delete"
                  onClick={() => { void onDelete(conversation.id) }}
                  aria-label={t.assistantDeleteThread}
                  title={t.assistantDeleteThread}
                >
                  <IconTrash size={13} />
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="assistant-messages">
          {isEmptyThread && (
            <div className="assistant-empty">
              <IconSparkles size={26} className="assistant-empty-icon" />
              <h3 className="assistant-empty-title">{t.assistantEmptyTitle}</h3>
              <p className="assistant-empty-body">{t.assistantEmptyBody}</p>
              <div className="assistant-suggestions">
                {suggestions.map(s => (
                  <button
                    key={s.key}
                    type="button"
                    className="assistant-suggestion"
                    onClick={() => { void submit(s.text) }}
                  >
                    {s.text}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map(message => (
            <AssistantMessageView key={message.id} message={message} />
          ))}

          {activeTools.length > 0 && streamingAnswer === '' && (
            <div className="assistant-tools" aria-live="polite">
              {activeTools.map(tool => (
                <span className="assistant-tool-chip" key={tool.id}>
                  <IconSpinner size={12} className="icon-spin" />
                  {assistantToolLabel(tool.name, tool.label, t)}
                </span>
              ))}
            </div>
          )}

          {streamingAnswer !== '' && (
            <AssistantMessageView
              message={{
                id: STREAMING_MESSAGE_ID,
                role: 'assistant',
                content: streamingAnswer,
                tool_calls: null,
                created_at: '',
              }}
            />
          )}

          {sending && streamingAnswer === '' && activeTools.length === 0 && (
            <p className="assistant-thinking" aria-live="polite">
              <IconSpinner size={13} className="icon-spin" />
              {t.assistantThinking}
            </p>
          )}

          {error !== null && (
            <div className="assistant-error" role="alert">
              <span>{error}</span>
              <button type="button" className="assistant-icon-btn" onClick={clearError} aria-label={t.modalClose}>
                <IconClose size={13} />
              </button>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* aria-live so a screen reader hears the answer arrive rather than
            being left with a silently changing region. */}
        <div className="assistant-sr-live" aria-live="polite" aria-atomic="false">
          {streamingAnswer}
        </div>

        <form className="assistant-composer" onSubmit={onSubmit}>
          <textarea
            ref={inputRef}
            className="assistant-input"
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onKeyDown={onComposerKeyDown}
            placeholder={t.assistantPlaceholder}
            rows={2}
            aria-label={t.assistantPlaceholder}
          />
          {sending ? (
            <button
              type="button"
              className="assistant-send-btn"
              onClick={stop}
              aria-label={t.assistantStop}
              title={t.assistantStop}
            >
              <IconClose size={15} />
            </button>
          ) : (
            <button
              type="submit"
              className="assistant-send-btn"
              disabled={draft.trim() === ''}
              aria-label={t.assistantSend}
              title={t.assistantSend}
            >
              <IconSend size={15} />
            </button>
          )}
        </form>

        <p className="assistant-disclaimer">{t.assistantDisclaimer}</p>
      </aside>
    </>,
    document.body,
  )
}
