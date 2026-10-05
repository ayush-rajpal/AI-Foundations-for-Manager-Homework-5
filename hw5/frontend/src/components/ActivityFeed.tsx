import { useEffect, useRef, useState } from 'react'
import type { Run } from '../derive'
import { feedLine } from '../derive'
import { agentOf } from '../agents'
import { clock } from '../format'

function pretty(data: unknown): string {
  if (typeof data === 'string') {
    try {
      return JSON.stringify(JSON.parse(data), null, 2)
    } catch {
      return data // e.g. a long payload the audit trail cut off
    }
  }
  return JSON.stringify(data, null, 2)
}

/** Live activity for the selected ticket's latest run, oldest first, with optional auto-scroll. */
export function ActivityFeed({ run }: { run: Run | null }) {
  const [autoScroll, setAutoScroll] = useState(true)
  const listRef = useRef<HTMLOListElement>(null)
  const lines = run ? run.events.map(feedLine).filter((l) => l !== null) : []
  const running = run?.status === 'running'

  useEffect(() => {
    const el = listRef.current
    if (!autoScroll || !el) return
    // Instant jump: smooth scrolling gets cut off when new lines keep arriving every poll.
    el.scrollTop = el.scrollHeight
  }, [lines.length, autoScroll, run?.runId])

  return (
    <section className="card feed" aria-labelledby="feed-title" aria-busy={running}>
      <div className="card-head">
        <h2 id="feed-title" className="card-title">Live activity</h2>
        <div className="feed-tools">
          {running && <span className="hint live"><span className="pulse" aria-hidden="true" /> Live</span>}
          <button
            type="button"
            className="toggle"
            aria-pressed={autoScroll}
            onClick={() => setAutoScroll((v) => !v)}
          >
            <span aria-hidden="true">{autoScroll ? '⏬' : '⏸'}</span> Auto-scroll {autoScroll ? 'on' : 'paused'}
          </button>
        </div>
      </div>
      {lines.length === 0 ? (
        <p className="empty">No activity yet. Run the agent team and each agent's messages and tool calls appear here as they happen.</p>
      ) : (
        <ol className="feed-list" ref={listRef} tabIndex={0} aria-label="Agent activity, oldest first">
          {lines.map((l) => {
            const who = agentOf(l.agent)
            return (
              <li key={l.seq} className={`feed-item tone-${l.tone} agent-${who.id}`}>
                <span className={`badge shape-${who.shape} agent-${who.id}`} aria-hidden="true">{who.glyph}</span>
                <div className="feed-body">
                  <p className="feed-title">
                    <strong className="who">{who.name}</strong> {l.text}
                  </p>
                  {l.body && <p className="feed-text">{l.body}</p>}
                  {l.data !== undefined && l.data !== null && (
                    <details className="raw">
                      <summary>View data</summary>
                      <pre>{pretty(l.data)}</pre>
                    </details>
                  )}
                </div>
                <time className="feed-time" dateTime={l.ts}>{clock(l.ts)}</time>
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}
