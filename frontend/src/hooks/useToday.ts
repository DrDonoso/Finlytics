import { useState } from 'react'

/** The local date when the component mounted, read once so every render agrees on "today". */
export function useToday(): Date {
  const [today] = useState(() => new Date())
  return today
}
