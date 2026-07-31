/**
 * One turn in the assistant thread, plus the minimal markdown it may contain.
 *
 * There is no markdown dependency in this project and this is not worth adding
 * one for: the prompt asks for `**bold**`, `-` bullets and plain paragraphs, and
 * that is all this renders. Everything else is shown verbatim.
 *
 * Crucially it builds React elements rather than HTML strings — LLM output is
 * untrusted, and `dangerouslySetInnerHTML` on it would be an injection vector
 * fed by whatever the model decided to echo back from a bank statement.
 */
import type { ReactNode } from 'react'

import { useT } from '../i18n'
import type { AssistantMessage as AssistantMessageType } from '../api/types'
import { IconSparkles, IconUser } from './icons'

/** Split a line on `**bold**` runs, leaving the rest as plain text. */
function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = []
  const pattern = /\*\*(.+?)\*\*/g
  let cursor = 0
  let match: RegExpExecArray | null
  let index = 0

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > cursor) nodes.push(text.slice(cursor, match.index))
    nodes.push(<strong key={`${keyPrefix}-b${index++}`}>{match[1]}</strong>)
    cursor = match.index + match[0].length
  }
  if (cursor < text.length) nodes.push(text.slice(cursor))
  return nodes
}

function isBullet(line: string): boolean {
  return /^\s*[-*•]\s+/.test(line)
}

/** Group consecutive bullet lines into lists, everything else into paragraphs. */
export function renderMarkdown(content: string): ReactNode[] {
  const blocks: ReactNode[] = []
  const lines = content.split('\n')
  let bullets: string[] = []
  let paragraph: string[] = []
  let key = 0

  function flushBullets() {
    if (bullets.length === 0) return
    const items = bullets
    bullets = []
    const listKey = key++
    blocks.push(
      <ul className="assistant-md-list" key={`ul${listKey}`}>
        {items.map((item, i) => (
          <li key={`${listKey}-${item.slice(0, 32)}-${i}`}>
            {renderInline(item, `li${listKey}-${i}`)}
          </li>
        ))}
      </ul>,
    )
  }

  function flushParagraph() {
    if (paragraph.length === 0) return
    const text = paragraph.join(' ')
    paragraph = []
    blocks.push(
      <p className="assistant-md-p" key={`p${key++}`}>{renderInline(text, `p${key}`)}</p>,
    )
  }

  for (const line of lines) {
    if (isBullet(line)) {
      flushParagraph()
      bullets.push(line.replace(/^\s*[-*•]\s+/, ''))
    } else if (line.trim() === '') {
      flushBullets()
      flushParagraph()
    } else {
      flushBullets()
      paragraph.push(line.trim())
    }
  }
  flushBullets()
  flushParagraph()

  return blocks
}

interface Props {
  message: AssistantMessageType
}

export default function AssistantMessageView({ message }: Props) {
  const { t } = useT()
  const isUser = message.role === 'user'
  const toolCount = message.tool_calls?.length ?? 0

  return (
    <div className={`assistant-msg assistant-msg--${isUser ? 'user' : 'assistant'}`}>
      <span className="assistant-msg-avatar" aria-hidden="true">
        {isUser ? <IconUser size={14} /> : <IconSparkles size={14} />}
      </span>
      <div className="assistant-msg-body">
        {isUser
          ? <p className="assistant-md-p">{message.content}</p>
          : renderMarkdown(message.content)}
        {toolCount > 0 && (
          <p className="assistant-msg-tools">{t.assistantToolsUsed(toolCount)}</p>
        )}
      </div>
    </div>
  )
}
