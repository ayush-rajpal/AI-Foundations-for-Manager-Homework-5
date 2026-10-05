import { useState } from 'react'
import type { Run } from '../derive'
import { bossResolution, emailAwaitingResponse, latestTicketNote, outputField } from '../derive'
import type { PaymentRequest, RunState, Ticket } from '../types'
import { TYPE_LABEL, statusOf, usd } from '../format'

interface Props {
  ticket: Ticket
  run: Run | null
  activeRun: RunState | null
  paymentsForTicket: PaymentRequest[]
  onRun: (id: number) => Promise<void>
  hasDraft: boolean
  onShowDraft: () => void
}

const OUTCOME_HEAD: Record<string, string> = {
  resolved: 'Resolved',
  awaiting_approval: 'Waiting on your sign-off',
  blocked: 'Blocked',
  in_progress: 'In progress',
  open: 'Still open',
}

/** The selected ticket: a plain-language outcome card on top, the run button, and the next step. */
export function TicketDetail({ ticket, run, activeRun, paymentsForTicket, onRun, hasDraft, onShowDraft }: Props) {
  const [error, setError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const busyElsewhere = activeRun && activeRun.ticket_id !== ticket.id
  const runningHere = activeRun?.ticket_id === ticket.id
  const decision = bossResolution(run)
  const note = latestTicketNote(ticket.notes)
  const awaitingReply = emailAwaitingResponse(ticket.status, ticket.notes)
  // Shown as a second part next to the status, never merged into it.
  const replyNote = awaitingReply ? (
    <span className="reply-note"><span aria-hidden="true">✉</span> Email sent to customer · awaiting response</span>
  ) : null
  const original = (ticket.notes ?? '').split('\n')[0]
  const paid = paymentsForTicket.filter((p) => p.status === 'paid')
  const pending = paymentsForTicket.filter((p) => p.status === 'awaiting_human_approval')
  const replyDrafted = !!run?.events.some((e) => {
    if (e.event !== 'agent_output' || e.agent !== 'customer_service') return false
    const drafts = outputField(e, 'drafts')
    return Array.isArray(drafts) ? drafts.length > 0 : typeof e.output === 'string' && e.output.includes('"drafts": [{')
  })

  let disabledReason: string | null = null
  if (ticket.resolved) disabledReason = 'This ticket is resolved.'
  else if (busyElsewhere) disabledReason = `The team is busy on ticket ${activeRun.ticket_id}. One run at a time.`
  else if (runningHere) disabledReason = 'The team is working on this ticket now.'

  async function start() {
    setError(null)
    setStarting(true)
    try {
      await onRun(ticket.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setStarting(false)
    }
  }

  let nextStep: string | null = null
  if (runningHere) nextStep = 'Watch the live activity below. Anything the team drafts pops up under Sign-off requests.'
  else if (ticket.resolved) nextStep = null
  else if (pending.length) nextStep = `Approve the ${pending.length} sign-off request${pending.length > 1 ? 's' : ''} on the right. After the last one, the team re-runs this ticket on its own so the Boss can close it.`
  else if (ticket.status === 'blocked') nextStep = 'Clear the blocker named above (for example, approve the invoice payment it waits on), then run the team again.'
  else if (run?.status === 'done') nextStep = 'Run the team again after anything changes (for example, after you approve a payment).'
  else if (!run) nextStep = 'Run the agent team to work this ticket.'

  const outcomeText = note?.note ?? decision?.decision ?? null
  const showOutcome = !runningHere && (outcomeText || paid.length > 0)

  return (
    <section className="card detail" aria-labelledby="detail-title">
      {showOutcome && (
        <div className={`outcome outcome-${ticket.status}`} aria-live="polite">
          <p className="outcome-head">
            <span aria-hidden="true">{statusOf(ticket.status).icon}</span> Outcome: {OUTCOME_HEAD[ticket.status] ?? statusOf(ticket.status).label}
          </p>
          {replyNote && <p className="outcome-reply">{replyNote}</p>}
          {outcomeText && <p className="outcome-text">{outcomeText}</p>}
          <ul className="outcome-facts">
            {paid.map((p) => (
              <li key={p.id}>
                <span aria-hidden="true">✓ </span>Paid {usd(p.amount)} to {p.payee}
                {p.kind === 'purchase' && typeof p.details.arrival_if_paid_today === 'string' ? `. Arrives about ${p.details.arrival_if_paid_today}` : ''}
                {p.approved_by ? ` (approved by ${p.approved_by})` : ''}
              </li>
            ))}
            {pending.map((p) => (
              <li key={p.id} className="warn"><span aria-hidden="true">✋ </span>{usd(p.amount)} to {p.payee} is waiting for your sign-off</li>
            ))}
            {(replyDrafted || hasDraft) && (
              <li>
                <span aria-hidden="true">✉ </span>Customer Service drafted a reply (never sent).{' '}
                {hasDraft && <button type="button" className="link-btn strong" onClick={onShowDraft}>Read the draft</button>}
              </li>
            )}
          </ul>
          {!!decision?.next_steps?.length && !ticket.resolved && (
            <details className="outcome-more">
              <summary>Boss's next steps</summary>
              <ul>{decision.next_steps.map((s, i) => <li key={i}>{s}</li>)}</ul>
            </details>
          )}
        </div>
      )}

      <div className="detail-head">
        <div>
          <p className="eyebrow">{TYPE_LABEL[ticket.type] ?? ticket.type} · ticket #{ticket.id}</p>
          <h2 id="detail-title" className="detail-title">{ticket.subject}</h2>
          <p className="detail-sub">
            From <strong>{ticket.requester}</strong>
            {ticket.sku && <> · {ticket.qty} × {ticket.sku} size {ticket.size}</>}
            {ticket.invoice_id && <> · linked invoice {ticket.invoice_id}</>}
            {ticket.lease_id && <> · lease {ticket.lease_id}</>}
          </p>
          {original && <p className="detail-quote">“{original}”</p>}
        </div>
        <div className="run-box">
          <button type="button" className="btn-run" onClick={start} disabled={!!disabledReason || starting} aria-describedby="run-help">
            {runningHere || starting ? (
              <><span className="spin" aria-hidden="true">⟳</span> Agents working…</>
            ) : run ? 'Run the team again' : 'Run agent team'}
          </button>
          <p id="run-help" className="run-help">{disabledReason ?? 'Starts the Boss on this ticket. Takes 1–4 minutes.'}</p>
        </div>
      </div>

      {error && <p className="alert" role="alert">{error}</p>}

      <div className="decision">
        <p className="decision-status">
          <span className={`status-chip ${ticket.status}`}>
            <span aria-hidden="true">{statusOf(ticket.status).icon}</span> {statusOf(ticket.status).label}
          </span>
          {replyNote}
          <span className="decision-note">Status recorded in the database</span>
        </p>
        {run && run.status !== 'running' && (
          <p className="run-result">
            Last run {run.status === 'done' ? 'finished' : 'failed'} · {run.events.length} steps
            {run.tokens ? ` · ${run.tokens.toLocaleString()} tokens` : ''} · <a href="#feed-title">see every step in Live activity</a>
          </p>
        )}
        {hasDraft && (
          <p className="run-result">
            <span aria-hidden="true">✉ </span>
            <button type="button" className="link-btn strong" onClick={onShowDraft}>Read the latest customer draft</button>
          </p>
        )}
        {run?.status === 'error' && <p className="alert" role="alert">The last run failed: {run.error}</p>}
        {nextStep && <p className="next-step"><strong>Next:</strong> {nextStep}</p>}
      </div>
    </section>
  )
}
