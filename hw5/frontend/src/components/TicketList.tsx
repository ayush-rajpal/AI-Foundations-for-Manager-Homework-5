import type { Ticket } from '../types'
import { TYPE_LABEL, usd } from '../format'
import { emailAwaitingResponse } from '../derive'

const TAGS: Record<string, { label: string; icon: string; tone: string }> = {
  open: { label: 'Open', icon: '○', tone: 'open' },
  in_progress: { label: 'In progress', icon: '⟳', tone: 'working' },
  blocked: { label: 'Blocked', icon: '⛔', tone: 'blocked' },
  awaiting_approval: { label: 'Awaiting sign-off', icon: '✋', tone: 'signoff' },
  resolved: { label: 'Resolved', icon: '✓', tone: 'resolved' },
}

interface Props {
  tickets: Ticket[]
  selectedId: number | null
  runningTicketId: number | null
  pendingByTicket: Map<number, number>
  onSelect: (id: number) => void
}

/** Sidebar ticket list. Cards are native radios, so arrow keys move the selection. */
export function TicketList({ tickets, selectedId, runningTicketId, pendingByTicket, onSelect }: Props) {
  return (
    <section className="side-block" aria-labelledby="tickets-title">
      <h2 id="tickets-title" className="side-title">Tickets</h2>
      {tickets.length === 0 ? (
        <p className="empty">No tickets loaded yet.</p>
      ) : (
        <fieldset className="ticket-list">
          <legend className="sr-only">Choose a ticket</legend>
          {tickets.map((t) => {
            const running = t.id === runningTicketId
            const tag = running ? { label: 'Agents working', icon: '⟳', tone: 'working' } : TAGS[t.status] ?? TAGS.open
            const pending = pendingByTicket.get(t.id)
            return (
              <label key={t.id} className={`tcard tone-${tag.tone}`}>
                <input type="radio" name="ticket" value={t.id} checked={selectedId === t.id} onChange={() => onSelect(t.id)} className="sr-only" />
                <span className="tcard-top">
                  <span className="tcard-id">#{t.id}</span>
                  <span className="tcard-type">{TYPE_LABEL[t.type] ?? t.type}</span>
                </span>
                <span className="tcard-subject">{t.subject}</span>
                <span className="tcard-who">{t.requester}{t.sku ? ` · ${t.qty} × ${t.sku} ${t.size}` : ''}</span>
                <span className="tcard-tags">
                  <span className={`tag tag-${tag.tone}`}>
                    <span aria-hidden="true" className={tag.tone === 'working' ? 'spin' : ''}>{tag.icon}</span> {tag.label}
                  </span>
                  {pending ? <span className="tag tag-money">✋ {usd(pending)} to sign</span> : null}
                  {!running && emailAwaitingResponse(t.status, t.notes) ? (
                    <span className="tag tag-email"><span aria-hidden="true">✉</span> Email sent · awaiting response</span>
                  ) : null}
                </span>
              </label>
            )
          })}
        </fieldset>
      )}
    </section>
  )
}
