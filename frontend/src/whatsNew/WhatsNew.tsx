import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useState } from 'react'
import { markWhatsNewSeen } from '../api/client'
import { queryKeys, useWhatsNew } from '../api/queries'
import type { WhatsNewState } from '../api/types'
import { NOTES, byKind, type Note } from './notes'
import { AllNotesDialog, NewsDialog } from './WhatsNewDialog'

/** Ids saved per request (the API takes up to 500). */
const BATCH = 500

interface Plan {
  readonly news: readonly Note[]
  readonly unread: readonly string[]
}

function planFor({ seen }: WhatsNewState): Plan {
  // A new user has nothing to catch up on: only what comes later is news to them.
  if (seen === null) return { news: [], unread: NOTES.map((note) => note.id) }
  const read = new Set(seen)
  const unread = NOTES.filter((note) => !read.has(note.id))
  return { news: byKind(unread), unread: unread.map((note) => note.id) }
}

export interface WhatsNewProps {
  allOpen: boolean
  onAllOpenChange: (isOpen: boolean) => void
}

/**
 * Tells the signed-in user what is new since they last looked. Once the notes they have read are
 * known, the unread ones open in a dialog; closing it (or the list of every note) counts every
 * unread note as read. Failing to save that only means seeing them again next time.
 */
export function WhatsNew({ allOpen, onAllOpenChange }: WhatsNewProps) {
  const queryClient = useQueryClient()
  const seen = useWhatsNew()
  const [plan, setPlan] = useState<Plan | null>(null)
  const [news, setNews] = useState<'pending' | 'open' | 'closed'>('pending')

  // Decided from the first answer: the cached one changes as the notes are marked as read.
  if (plan === null && seen.data) setPlan(planFor(seen.data))
  if (plan && plan.news.length > 0 && news === 'pending' && !allOpen) setNews('open')

  const markRead = useCallback(
    (ids: readonly string[]) => {
      if (ids.length === 0) return
      queryClient.setQueryData<WhatsNewState>(queryKeys.whatsNew, (current) => ({
        seen: [...new Set([...(current?.seen ?? []), ...ids])].sort(),
      }))
      for (let start = 0; start < ids.length; start += BATCH) {
        markWhatsNewSeen(ids.slice(start, start + BATCH)).catch(() => undefined)
      }
    },
    [queryClient],
  )

  const done = plan !== null && (plan.news.length === 0 || news === 'closed')
  useEffect(() => {
    if (done && plan) markRead(plan.unread)
  }, [done, plan, markRead])

  return (
    <>
      {news === 'open' && <NewsDialog onClose={() => setNews('closed')} notes={plan?.news ?? []} />}
      {allOpen && (
        <AllNotesDialog
          onClose={() => {
            onAllOpenChange(false)
            setNews('closed')
          }}
          notes={NOTES}
        />
      )}
    </>
  )
}
