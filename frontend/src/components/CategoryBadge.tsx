/**
 * The category colour is user data and can be anything, so it never colours
 * the text: a light yellow label on a white card is unreadable. It marks a dot
 * instead, and the label keeps the body text colour.
 */
export default function CategoryBadge({ label, color }: { label: string; color?: string }) {
  return (
    <span className="badge badge-category">
      {color && <span className="badge-dot" style={{ background: color }} aria-hidden="true" />}
      <span className="badge-label">{label}</span>
    </span>
  )
}
