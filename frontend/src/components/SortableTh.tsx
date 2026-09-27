import type { ReactNode } from 'react'
import { IconChevronDown, IconChevronUp } from './icons'

interface SortableThProps {
  label: ReactNode
  active: boolean
  direction: 'asc' | 'desc'
  onSort: () => void
  className?: string
  /** Trailing controls (an info tip). Rendered beside the button, never inside it. */
  children?: ReactNode
}

/** A sortable column header: the button takes the pointer and the keyboard, the th reports the order. */
export default function SortableTh({ label, active, direction, onSort, className, children }: SortableThProps) {
  const Arrow = direction === 'asc' ? IconChevronUp : IconChevronDown
  return (
    <th
      className={['th-sortable', active ? 'th-sort-active' : '', className ?? ''].filter(Boolean).join(' ')}
      aria-sort={active ? (direction === 'asc' ? 'ascending' : 'descending') : undefined}
    >
      <button type="button" className="th-sort-btn" onClick={onSort}>
        {label}
        {active && <span className="th-sort-arrow" aria-hidden="true"><Arrow size={12} /></span>}
      </button>
      {children}
    </th>
  )
}
