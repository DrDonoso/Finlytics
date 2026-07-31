/**
 * Finlytics brand components.
 *
 * The old logo was two PNGs at ~816 KB each. This SVG inline version is <1 KB
 * in the bundle and its gradient comes from `--brand-gradient`, so the mark
 * follows the theme and accent palette instead of being a static image.
 */

/** Unique per-instance id: two <linearGradient> elements cannot share the same id. */
let gradientSeq = 0

interface MarkProps {
  /** Lado en px. */
  size?: number
  className?: string
}

/** The symbol mark: roof + bars. */
export function BrandMark({ size = 28, className }: MarkProps) {
  const gid = `brand-mark-${++gradientSeq}`
  return (
    <svg
      viewBox="0 0 64 64"
      width={size}
      height={size}
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id={gid} x1="6" y1="58" x2="58" y2="6" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="var(--brand-navy, #123a6b)" />
          <stop offset="0.48" stopColor="var(--brand-blue, #21639f)" />
          <stop offset="1" stopColor="var(--brand-teal, #12b886)" />
        </linearGradient>
      </defs>
      <g
        fill="none"
        stroke={`url(#${gid})`}
        strokeWidth="5.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M7 30 32 9l25 21" />
        <path d="M13.5 34.5V54M50.5 34.5V54" />
      </g>
      <g fill={`url(#${gid})`}>
        <rect x="20" y="43" width="6.6" height="11" rx="2.4" />
        <rect x="29.2" y="36" width="6.6" height="18" rx="2.4" />
        <rect x="38.4" y="29.5" width="6.6" height="24.5" rx="2.4" />
      </g>
    </svg>
  )
}

interface WordmarkProps {
  /** `sm` for the top bar, `lg` for authentication screens. */
  size?: 'sm' | 'lg'
  className?: string
}

/** Symbol mark + name. Text is rendered with the real font, not an image. */
export function Wordmark({ size = 'sm', className }: WordmarkProps) {
  const cls = ['brand-wordmark', `brand-wordmark--${size}`, className].filter(Boolean).join(' ')
  return (
    <span className={cls}>
      <BrandMark size={size === 'lg' ? 44 : 28} />
      <span className="brand-wordmark__text">Finlytics</span>
    </span>
  )
}
