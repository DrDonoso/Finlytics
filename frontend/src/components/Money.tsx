import type { ReactNode } from 'react'
import { useT } from '../i18n'

interface MoneyProps {
  value: number | null | undefined
  /** Prefix an explicit `+` on non-negative values. */
  signed?: boolean
  /** Rendered when there is no value. Never blurred — it leaks nothing. */
  fallback?: string
  className?: string
}

/**
 * Every monetary figure on screen goes through here, which is what makes the
 * privacy toggle a single CSS rule instead of a per-component concern.
 */
export default function Money({ value, signed, fallback = '—', className }: MoneyProps) {
  const { formatCurrency } = useT()

  if (value == null || !Number.isFinite(value)) {
    return <span className={className}>{fallback}</span>
  }

  const sign = signed && value >= 0 ? '+' : ''
  return (
    <span className={className ? `private ${className}` : 'private'}>
      {sign}{formatCurrency(value)}
    </span>
  )
}

/**
 * Escape hatch for amounts already formatted elsewhere — custom precision,
 * composed strings, or figures that are not plain euros.
 */
export function Private({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={className ? `private ${className}` : 'private'}>{children}</span>
}
