import { readdirSync, readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { NOTE_ICONS, renderNoteIcon } from './icons'
import { NOTES, NOTE_ID, byKind, byMonth, type Note } from './notes'

const LANGS = ['es', 'en']
const at = (path: string) => new URL(path, import.meta.url)
const FILE_NAMES = readdirSync(at('./notes/'))
const TITLE_MAX = 70
const BODY_MAX = 300

function realDate(date: string): boolean {
  const parsed = new Date(`${date}T00:00:00Z`)
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === date
}

/** Problems of one note file (an empty list when it is fine). */
function problems(name: string, raw: string): string[] {
  const found: string[] = []
  const id = name.replace(/\.json$/, '')
  if (!name.endsWith('.json') || !NOTE_ID.test(id) || id.length > 80) found.push('name: YYYY-MM-DD-slug.json (a-z, 0-9, -)')
  else if (!realDate(id.slice(0, 10))) found.push(`name: ${id.slice(0, 10)} is not a date`)
  let note: Record<string, unknown>
  try {
    note = JSON.parse(raw) as Record<string, unknown>
  } catch {
    return [...found, 'not valid JSON']
  }
  const allowed = new Set(['kind', 'icon', 'link', ...LANGS])
  found.push(...Object.keys(note).filter((key) => !allowed.has(key)).map((key) => `unknown field "${key}"`))
  if (!['new', 'improved', 'fixed'].includes(note.kind as string)) found.push('kind: new, improved or fixed')
  if ('icon' in note && !(typeof note.icon === 'string' && Object.prototype.hasOwnProperty.call(NOTE_ICONS, note.icon))) {
    found.push(`icon: one of ${Object.keys(NOTE_ICONS).join(', ')}`)
  }
  if ('link' in note && (typeof note.link !== 'string' || !/^\/[a-z0-9/-]*$/.test(note.link))) {
    found.push('link: a page of the app, such as /settings/backup')
  }
  for (const lang of LANGS) {
    const text = note[lang] as Record<string, unknown> | undefined
    if (typeof text !== 'object' || text === null || Object.keys(text).sort().join() !== 'body,title') {
      found.push(`${lang}: { "title", "body" }`)
      continue
    }
    for (const [field, max] of [['title', TITLE_MAX], ['body', BODY_MAX]] as const) {
      const value = text[field]
      if (typeof value !== 'string' || !value.trim()) found.push(`${lang}.${field}: missing`)
      else if (value !== value.trim() || /\s{2,}|[\n\r\t]/.test(value)) found.push(`${lang}.${field}: one line, no extra spaces`)
      else if (value.length > max) found.push(`${lang}.${field}: ${value.length} characters (${max} at most)`)
    }
  }
  return found
}

const NOTE = (id: string, kind: Note['kind']): Note => {
  const text = { title: id, body: id }
  return { id, date: id.slice(0, 10), kind, es: text, en: text }
}

describe("what's new notes", () => {
  it.each(FILE_NAMES)('%s is a valid note', (name) => {
    expect(problems(name, readFileSync(at(`./notes/${name}`), 'utf8'))).toEqual([])
  })

  it('are all bundled, newest first', () => {
    expect(NOTES.map((note) => note.id)).toEqual(FILE_NAMES.map((name) => name.replace(/\.json$/, '')).sort().reverse())
  })

  it('finds what is wrong with a note', () => {
    const text = { title: 'Dark mode', body: 'Switch it in Settings.' }
    const fine = { kind: 'new', es: text, en: text }
    expect(problems('2026-12-01-dark.json', JSON.stringify(fine))).toEqual([])
    expect(problems('2026-02-30-dark.json', JSON.stringify(fine))).toEqual(['name: 2026-02-30 is not a date'])
    expect(problems('2026-12-01-Dark.md', '{')).toEqual(['name: YYYY-MM-DD-slug.json (a-z, 0-9, -)', 'not valid JSON'])
    expect(
      problems('2026-12-01-dark.json', JSON.stringify({ ...fine, kind: 'feature', icon: 'unicorn', link: 'https://x.dev', en: { title: 'x' } })),
    ).toEqual([
      'kind: new, improved or fixed',
      `icon: one of ${Object.keys(NOTE_ICONS).join(', ')}`,
      'link: a page of the app, such as /settings/backup',
      'en: { "title", "body" }',
    ])
    const long = { title: 'x'.repeat(TITLE_MAX + 1), body: ' Switch  it. ' }
    expect(problems('2026-12-01-dark.json', JSON.stringify({ ...fine, en: long }))).toEqual([
      `en.title: ${TITLE_MAX + 1} characters (${TITLE_MAX} at most)`,
      'en.body: one line, no extra spaces',
    ])
  })

  it('orders notes by kind and groups them by month', () => {
    const notes = [NOTE('2026-11-02-a', 'fixed'), NOTE('2026-12-20-b', 'improved'), NOTE('2026-11-20-c', 'new'), NOTE('2026-11-10-d', 'new')]
    expect(byKind(notes).map((note) => note.id)).toEqual(['2026-11-20-c', '2026-11-10-d', '2026-12-20-b', '2026-11-02-a'])
    expect(byMonth(notes).map(({ month, notes: items }) => [month, items.map((note) => note.id)])).toEqual([
      ['2026-12', ['2026-12-20-b']],
      ['2026-11', ['2026-11-20-c', '2026-11-10-d', '2026-11-02-a']],
    ])
  })

  it('falls back to the icon of the kind', () => {
    expect(renderNoteIcon({ kind: 'improved', icon: 'toString' }, 16).type).toBe(renderNoteIcon({ kind: 'improved' }, 16).type)
  })
})
