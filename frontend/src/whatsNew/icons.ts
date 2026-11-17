import { createElement, type ComponentType, type ReactElement } from 'react'
import {
  IconBell, IconBuilding, IconChartLine, IconChat, IconCoins, IconDownload, IconFilter, IconGlobe,
  IconKey, IconLock, IconSparkles, IconTag, IconTrash, IconTrendingUp, IconWallet,
  type IconProps,
} from '../components/icons'
import type { Note, NoteKind } from './notes'

type NoteIcon = ComponentType<IconProps>

/** Icons a note can name in its `icon` field. */
export const NOTE_ICONS: Readonly<Record<string, NoteIcon>> = {
  bell: IconBell,
  building: IconBuilding,
  chart: IconChartLine,
  chat: IconChat,
  coins: IconCoins,
  download: IconDownload,
  filter: IconFilter,
  globe: IconGlobe,
  key: IconKey,
  lock: IconLock,
  sparkles: IconSparkles,
  tag: IconTag,
  trash: IconTrash,
  'trending-up': IconTrendingUp,
  wallet: IconWallet,
}

const KIND_ICONS: Readonly<Record<NoteKind, NoteIcon>> = {
  new: IconSparkles,
  improved: IconTrendingUp,
  fixed: IconKey,
}

function pick(note: Pick<Note, 'icon' | 'kind'>): NoteIcon {
  const named = note.icon && Object.prototype.hasOwnProperty.call(NOTE_ICONS, note.icon) ? NOTE_ICONS[note.icon] : undefined
  return named ?? KIND_ICONS[note.kind]
}

export function renderNoteIcon(note: Pick<Note, 'icon' | 'kind'>, size: number): ReactElement {
  return createElement(pick(note), { size })
}
