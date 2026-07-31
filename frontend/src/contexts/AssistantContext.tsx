/**
 * Finance assistant state, shared by the launcher and the panel.
 *
 * The answer stream is imperative — it mutates a buffer token by token — so it
 * lives here rather than in react-query, which is built around whole responses.
 * The panel reads `streamingAnswer` on every frame; react-query's cache would
 * have to be rewritten dozens of times a second to do the same job.
 */
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from 'react'
import type { ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import {
  createAssistantConversation,
  deleteAssistantConversation,
  getAssistantConversation,
  streamAssistantMessage,
} from '../api/client'
import { queryKeys } from '../api/queries'
import type { AssistantMessage } from '../api/types'

/** A query the assistant is running right now, shown as an activity chip. */
export interface ActiveTool {
  /** Stable key: the same tool can legitimately run twice in one turn. */
  id: number
  name: string
  label: string
}

interface AssistantContextValue {
  open: boolean
  openPanel: () => void
  closePanel: () => void
  togglePanel: () => void

  conversationId: number | null
  selectConversation: (id: number | null) => void
  startNewConversation: () => void
  removeConversation: (id: number) => Promise<void>

  /** Turns the user has sent that are not yet in the server's copy of the thread. */
  pendingMessages: AssistantMessage[]
  streamingAnswer: string
  activeTools: ActiveTool[]
  sending: boolean
  error: string | null

  send: (content: string) => Promise<void>
  stop: () => void
  clearError: () => void
}

const AssistantContext = createContext<AssistantContextValue | null>(null)

/** Inert fallback used when no provider is above the consumer.
 *
 *  Matching NotificationsContext's convention rather than throwing: the
 *  assistant is optional chrome mounted from Layout, and a missing provider
 *  should leave the panel unopenable, not blank out every page in the app. */
const INERT: AssistantContextValue = {
  open: false,
  openPanel: () => {},
  closePanel: () => {},
  togglePanel: () => {},
  conversationId: null,
  selectConversation: () => {},
  startNewConversation: () => {},
  removeConversation: async () => {},
  pendingMessages: [],
  streamingAnswer: '',
  activeTools: [],
  sending: false,
  error: null,
  send: async () => {},
  stop: () => {},
  clearError: () => {},
}

/** Local id for an optimistic user turn, before the server assigns a real one.
 *  Negative so it can never collide with a database id. */
let nextLocalId = -1

export function AssistantProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()

  const [open, setOpen] = useState(false)
  const [conversationId, setConversationId] = useState<number | null>(null)
  const [pendingMessages, setPendingMessages] = useState<AssistantMessage[]>([])
  const [streamingAnswer, setStreamingAnswer] = useState('')
  const [activeTools, setActiveTools] = useState<ActiveTool[]>([])
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const abortRef = useRef<AbortController | null>(null)

  const resetTurn = useCallback(() => {
    setStreamingAnswer('')
    setActiveTools([])
    setPendingMessages([])
  }, [])

  const selectConversation = useCallback((id: number | null) => {
    abortRef.current?.abort()
    setConversationId(id)
    setError(null)
    setSending(false)
    setStreamingAnswer('')
    setActiveTools([])
    setPendingMessages([])
  }, [])

  const startNewConversation = useCallback(() => {
    selectConversation(null)
  }, [selectConversation])

  const removeConversation = useCallback(async (id: number) => {
    await deleteAssistantConversation(id)
    await queryClient.invalidateQueries({ queryKey: queryKeys.assistantConversations })
    setConversationId(current => (current === id ? null : current))
  }, [queryClient])

  const send = useCallback(async (content: string) => {
    const text = content.trim()
    if (!text || sending) return

    setError(null)
    setSending(true)
    setStreamingAnswer('')
    setActiveTools([])

    // Show the question immediately. Waiting for the server to echo it back
    // would leave the composer looking like it swallowed the message.
    const optimistic: AssistantMessage = {
      id: nextLocalId--,
      role: 'user',
      content: text,
      tool_calls: null,
      created_at: new Date().toISOString(),
    }
    setPendingMessages(current => [...current, optimistic])

    const controller = new AbortController()
    abortRef.current = controller

    /** Whether this turn is still the active one.
     *
     *  Stop() flips `sending` to false immediately, so the user can send again
     *  while the aborted turn is still unwinding its awaits. Without this guard
     *  the old turn's tail would clear the NEW turn's buffers and null its
     *  AbortController, leaving Stop dead and letting two streams interleave. */
    const isCurrent = () => abortRef.current === controller

    try {
      let targetId = conversationId
      if (targetId === null) {
        const created = await createAssistantConversation()
        targetId = created.id
        setConversationId(targetId)
      }

      await streamAssistantMessage(targetId, text, event => {
        if (!isCurrent()) return
        switch (event.type) {
          case 'tool':
            // The backend drops any text emitted alongside a tool request — it
            // is preamble ("let me check…"), not the answer. That text has
            // already been streamed here, so the buffer has to be cleared in
            // step or the visible reply would silently lose its opening line
            // when the stored copy arrives.
            setStreamingAnswer('')
            setActiveTools(current => [
              ...current,
              { id: current.length, name: event.name, label: event.label },
            ])
            break
          case 'token':
            setStreamingAnswer(current => current + event.text)
            break
          case 'error':
            setError(event.detail)
            break
          case 'done':
            break
        }
      }, controller.signal)

      if (!isCurrent()) return

      // The question was persisted before streaming began, so the server's copy
      // is authoritative whether the turn succeeded, failed or was stopped.
      //
      // Fetched and written into the cache by hand rather than through
      // `invalidateQueries` so that the stored copy landing and the optimistic
      // copy being dropped happen in the same React commit. Invalidating leaves
      // a window where both are in state, and the question renders twice.
      const fresh = await getAssistantConversation(targetId)
      if (!isCurrent()) return

      queryClient.setQueryData(queryKeys.assistantConversation(targetId), fresh)
      resetTurn()
      void queryClient.invalidateQueries({ queryKey: queryKeys.assistantConversations })
    } catch (err) {
      if (isCurrent() && !controller.signal.aborted) {
        setError(err instanceof Error ? err.message : String(err))
      }
    } finally {
      if (isCurrent()) {
        abortRef.current = null
        setSending(false)
      }
    }
  }, [conversationId, queryClient, resetTurn, sending])

  const stop = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setSending(false)
  }, [])

  const value = useMemo<AssistantContextValue>(() => ({
    open,
    openPanel: () => setOpen(true),
    closePanel: () => setOpen(false),
    togglePanel: () => setOpen(v => !v),
    conversationId,
    selectConversation,
    startNewConversation,
    removeConversation,
    pendingMessages,
    streamingAnswer,
    activeTools,
    sending,
    error,
    send,
    stop,
    clearError: () => setError(null),
  }), [
    open, conversationId, selectConversation, startNewConversation, removeConversation,
    pendingMessages, streamingAnswer, activeTools, sending, error, send, stop,
  ])

  return <AssistantContext.Provider value={value}>{children}</AssistantContext.Provider>
}

export function useAssistant(): AssistantContextValue {
  return useContext(AssistantContext) ?? INERT
}
