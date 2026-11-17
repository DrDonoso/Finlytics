import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { IconArrowRight, IconClose } from '../components/icons'
import Modal from '../components/Modal'
import { useT } from '../i18n'
import { renderNoteIcon } from './icons'
import { byMonth, type Note } from './notes'

/** News shown before «Show N more». */
export const NEWS_SHOWN = 6

interface NoteCardProps {
  note: Note
  heading: 'h4' | 'h5'
  onLeave: () => void
  focusTitle?: boolean
}

function NoteCard({ note, heading: Heading, onLeave, focusTitle = false }: NoteCardProps) {
  const { t, lang } = useT()
  const title = useRef<HTMLHeadingElement>(null)
  const text = note[lang]
  const kind = { new: t.whatsNewKindNew, improved: t.whatsNewKindImproved, fixed: t.whatsNewKindFixed }[note.kind]
  useEffect(() => {
    if (focusTitle) title.current?.focus()
  }, [focusTitle])
  return (
    <li className={`wn-note wn-${note.kind}`}>
      <span className="wn-icon" aria-hidden="true">{renderNoteIcon(note, 22)}</span>
      <div className="wn-text">
        <p className="wn-kind">{kind}</p>
        <Heading ref={title} className="wn-title" tabIndex={focusTitle ? -1 : undefined}>{text.title}</Heading>
        <p className="wn-body">{text.body}</p>
        {note.link && (
          <Link to={note.link} className="btn-secondary wn-go" onClick={onLeave}>
            {t.whatsNewGoThere}
            <IconArrowRight size={14} />
          </Link>
        )}
      </div>
    </li>
  )
}

interface DialogProps {
  onClose: () => void
  notes: readonly Note[]
}

interface FrameProps {
  onClose: () => void
  children: React.ReactNode
  footer?: React.ReactNode
}

function Frame({ onClose, children, footer }: FrameProps) {
  const { t } = useT()
  return (
    <Modal onDismiss={onClose} labelledBy="whats-new-title" className="wn-modal">
      <div className="modal-header">
        <span className="modal-title" id="whats-new-title">{t.whatsNewTitle}</span>
        <button className="modal-close" type="button" aria-label={t.modalClose} onClick={onClose}>
          <IconClose size={16} />
        </button>
      </div>
      <div className="modal-body">{children}</div>
      {footer && <div className="modal-footer">{footer}</div>}
    </Modal>
  )
}

/** What is new since the user last looked (the first {@link NEWS_SHOWN}, then all of them on request). */
export function NewsDialog({ onClose, notes }: DialogProps) {
  const { t } = useT()
  const [expanded, setExpanded] = useState(false)
  const shown = expanded ? notes : notes.slice(0, NEWS_SHOWN)
  const hidden = notes.length - shown.length
  return (
    <Frame
      onClose={onClose}
      footer={<button type="button" className="btn-primary" onClick={onClose}>{t.whatsNewGotIt}</button>}
    >
      <p className="wn-intro">{t.whatsNewIntro}</p>
      <ul className="wn-notes">
        {shown.map((note, index) => (
          <NoteCard key={note.id} note={note} heading="h4" onLeave={onClose} focusTitle={expanded && index === NEWS_SHOWN} />
        ))}
      </ul>
      {hidden > 0 && (
        <button type="button" className="btn-secondary wn-more" onClick={() => setExpanded(true)}>
          {t.whatsNewShowMore(hidden)}
        </button>
      )}
    </Frame>
  )
}

/** Every note, by month, newest first. */
export function AllNotesDialog({ onClose, notes }: DialogProps) {
  const { t, locale } = useT()
  const months = byMonth(notes)
  const format = new Intl.DateTimeFormat(locale, { month: 'long', year: 'numeric' })
  return (
    <Frame onClose={onClose}>
      <p className="wn-intro">{months.length > 0 ? t.whatsNewAllIntro : t.whatsNewEmpty}</p>
      {months.map(({ month, notes: monthNotes }) => {
        const name = format.format(new Date(`${month}-01T12:00:00`))
        return (
          <div key={month} className="wn-month">
            <h4 className="wn-month-title">{name.charAt(0).toLocaleUpperCase(locale) + name.slice(1)}</h4>
            <ul className="wn-notes">
              {monthNotes.map((note) => (
                <NoteCard key={note.id} note={note} heading="h5" onLeave={onClose} />
              ))}
            </ul>
          </div>
        )
      })}
    </Frame>
  )
}
