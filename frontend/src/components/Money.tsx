import type { ReactNode } from 'react'
import { useT } from '../i18n'
import type { PercentOptions } from '../i18n'

interface MoneyProps {
  value: number | null | undefined
  /** Prefix an explicit `+` on non-negative values. */
  signed?: boolean
  /** Rendered when there is no value. Never blurred — it leaks nothing. */
  fallback?: string
  className?: string
}

function classes(base: string, extra?: string): string {
  return extra ? `${base} ${extra}` : base
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
    <span className={classes('private num', className)}>
      {sign}{formatCurrency(value)}
    </span>
  )
}

/**
 * Escape hatch for amounts already formatted elsewhere — custom precision,
 * composed strings, or figures that are not plain euros.
 */
export function Private({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={classes('private num', className)}>{children}</span>
}

interface PercentProps extends PercentOptions {
  value: number | null | undefined
  fallback?: string
  className?: string
}

/** Percentages say nothing about the size of someone's savings, so they are never blurred. */
export function Percent({ value, fallback = '—', className, ...opts }: PercentProps) {
  const { formatPercent } = useT()
  if (value == null || !Number.isFinite(value)) {
    return <span className={className}>{fallback}</span>
  }
  return <span className={classes('num', className)}>{formatPercent(value, opts)}</span>
}
