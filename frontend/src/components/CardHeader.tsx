import type { ReactNode } from 'react'

interface CardHeaderProps {
  title: ReactNode
  /** Right-aligned controls, a link or a secondary figure; wraps under the title on narrow cards. */
  action?: ReactNode
  className?: string
}

/** The one card heading: an h2 under the page's h1, so the outline never skips a level. */
export default function CardHeader({ title, action, className }: CardHeaderProps) {
  const heading = <h2 className="card-title">{title}</h2>
  if (action == null || action === false) {
    return className ? <div className={`card-header ${className}`}>{heading}</div> : heading
  }
  return (
    <div className={className ? `card-header ${className}` : 'card-header'}>
      {heading}
      {action}
    </div>
  )
}
