/**
 * What's new: short notes about the changes people will notice. Each one is a JSON file in
 * ./notes/ named `YYYY-MM-DD-slug.json`: the name is the note's id and gives its date. A published
 * note is never renamed (it would be shown again). How to write them: AGENTS.md ("What's new
 * notes"); notes.test.ts checks every file.
 */
import type { Lang } from '../i18n'

/** `new`: something you can do now · `improved`: works better · `fixed`: a problem is gone. */
export type NoteKind = 'new' | 'improved' | 'fixed'

export interface NoteText {
  readonly title: string
  readonly body: string
}

/** Contents of a note file: its texts in every language. */
export type NoteFile = Readonly<Record<Lang, NoteText>> & {
  readonly kind: NoteKind
  /** A key of `NOTE_ICONS` (./icons.ts); without it, the icon of its kind. */
  readonly icon?: string
  /** A page of the app to go and try it, such as `/settings/backup`. */
  readonly link?: string
}

export type Note = NoteFile & {
  /** The file name without `.json`. */
  readonly id: string
  /** `YYYY-MM-DD`, the start of the id. */
  readonly date: string
}

/** A note's id (the API checks the same pattern, up to 80 characters). */
export const NOTE_ID = /^\d{4}-\d{2}-\d{2}-[a-z0-9]+(-[a-z0-9]+)*$/

// Without a type argument: Vitest keeps transformed files in a cache unless they contain the exact
// text `import.meta.glob(`, and a cached copy would miss the notes added since.
const FILES = import.meta.glob('./notes/*.json', { eager: true, import: 'default' }) as Record<string, NoteFile>

/** `./notes/2026-11-17-novedades.json` → `2026-11-17-novedades`. */
export function noteId(path: string): string {
  return path.slice(path.lastIndexOf('/') + 1).replace(/\.json$/, '')
}

/** Newest first (ids start with their date). */
function newestFirst(a: Note, b: Note): number {
  return a.id < b.id ? 1 : a.id > b.id ? -1 : 0
}

/** Every note in this version, newest first. */
export const NOTES: readonly Note[] = Object.entries(FILES)
  .map(([path, file]): Note => {
    const id = noteId(path)
    return { ...file, id, date: id.slice(0, 10) }
  })
  .sort(newestFirst)

const KIND_ORDER: Readonly<Record<NoteKind, number>> = { new: 0, improved: 1, fixed: 2 }

/** What is new first, then what works better, then the fixes; newest first within each kind. */
export function byKind(notes: readonly Note[]): Note[] {
  return [...notes].sort((a, b) => KIND_ORDER[a.kind] - KIND_ORDER[b.kind] || newestFirst(a, b))
}

export interface NoteMonth {
  /** `YYYY-MM`. */
  readonly month: string
  readonly notes: readonly Note[]
}

/** Notes by month, newest month first, each month {@link byKind}. */
export function byMonth(notes: readonly Note[]): NoteMonth[] {
  const months = new Map<string, Note[]>()
  for (const note of [...notes].sort(newestFirst)) {
    const month = note.date.slice(0, 7)
    months.set(month, [...(months.get(month) ?? []), note])
  }
  return Array.from(months, ([month, items]) => ({ month, notes: byKind(items) }))
}
