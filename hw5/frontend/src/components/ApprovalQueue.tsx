import { useState } from 'react'
import type { PaymentRequest } from '../types'
import { usd } from '../format'

const KIND: Record<PaymentRequest['kind'], string> = { invoice: 'Invoice payment', rent: 'Rent payment', purchase: 'Restock purchase' }

interface Props {
  payments: PaymentRequest[]
  ticketOfRun: (runId: string) => number | null
  onApprove: (id: number, approver: string) => Promise<PaymentRequest>
}

/** Prominent sign-off banner in the workspace whenever Accounting has drafted something.
 *  Only a human approval here moves money. */
export function SignOffBanner({ payments, ticketOfRun, onApprove }: Props) {
  const [approver, setApprover] = useState(() => localStorage.getItem('approver') ?? '')
  const [confirming, setConfirming] = useState<number | null>(null)
  const [busy, setBusy] = useState<number | null>(null)
  const [message, setMessage] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)
  const pending = payments.filter((p) => p.status === 'awaiting_human_approval')
  const nameOk = approver.trim().length > 1
  const ticketOf = (p: PaymentRequest) => p.ticket_id ?? ticketOfRun(p.run_id)

  async function approve(p: PaymentRequest) {
    setBusy(p.id)
    setMessage(null)
    try {
      const res = await onApprove(p.id, approver.trim())
      const r = res.auto_rerun
      const next =
        r?.status === 'started' ? ` The team is re-running ticket #${r.ticket_id} now to close it out.`
        : r?.status === 'queued' ? ` Ticket #${r.ticket_id} re-runs automatically as soon as the current run finishes.`
        : r?.status === 'waiting_for_other_approvals' ? ` Ticket #${r.ticket_id} re-runs automatically after its other sign-off.`
        : ''
      setMessage({ kind: 'ok', text: `Approved: paid ${usd(p.amount)} to ${p.payee}.${next}` })
    } catch (err) {
      setMessage({ kind: 'err', text: err instanceof Error ? err.message : String(err) })
    } finally {
      setBusy(null)
      setConfirming(null)
    }
  }

  if (pending.length === 0 && !message) return null

  return (
    <section id="approvals" className={`signoff ${pending.length ? 'is-pending' : ''}`} aria-labelledby="signoff-title">
      {pending.length > 0 && (
        <div className="signoff-head">
          <h2 id="signoff-title" className="signoff-title">
            <span aria-hidden="true">✋</span> Sign-off needed: Accounting drafted {pending.length} item{pending.length > 1 ? 's' : ''} (
            {usd(pending.reduce((s, p) => s + p.amount, 0))})
          </h2>
          <div className="approver">
            <label htmlFor="approver-name">Approving as</label>
            <input
              id="approver-name"
              type="text"
              autoComplete="name"
              placeholder="Your full name"
              value={approver}
              onChange={(e) => {
                setApprover(e.target.value)
                localStorage.setItem('approver', e.target.value)
              }}
            />
          </div>
        </div>
      )}
      {pending.length === 0 && <h2 id="signoff-title" className="sr-only">Sign-off</h2>}

      {message && (
        <p className={message.kind === 'ok' ? 'notice' : 'alert'} role={message.kind === 'ok' ? 'status' : 'alert'}>
          {message.text}
          {pending.length === 0 && (
            <button type="button" className="link-btn" onClick={() => setMessage(null)}>Dismiss</button>
          )}
        </p>
      )}

      {pending.length > 0 && (
        <ul className="action-cards">
          {pending.map((p) => {
            const ticket = ticketOf(p)
            const noun = p.kind === 'purchase' ? 'Purchase' : 'Payment'
            const others = pending.filter((o) => o.id !== p.id && ticketOf(o) === ticket).length
            return (
              <li key={p.id} className={`action-card kind-${p.kind}`}>
                <p className="action-kind">
                  <span className="badge agent-accounting shape-hex" aria-hidden="true">$</span>
                  {KIND[p.kind]}{ticket ? ` · ticket #${ticket}` : ''}
                </p>
                <p className="action-vendor">{p.payee}</p>
                <p className="action-amount">{usd(p.amount)}</p>
                <p className="action-reason"><span className="muted">Reason:</span> {p.description ?? KIND[p.kind]}</p>
                <p className="action-math">
                  Checking {usd(p.balance_before)} <span aria-hidden="true">→</span><span className="sr-only">would become</span> {usd(p.balance_after)}
                  {p.kind === 'purchase' && typeof p.details.arrival_if_paid_today === 'string' && <> · arrives ~{p.details.arrival_if_paid_today}</>}
                </p>
                {p.blocked_reason && <p className="blocked"><span aria-hidden="true">⚠ </span>{p.blocked_reason}</p>}
                {confirming === p.id ? (
                  <div className="confirm" role="group" aria-label={`Confirm ${noun.toLowerCase()} of ${usd(p.amount)} to ${p.payee}`}>
                    <button type="button" className="btn-approve" onClick={() => approve(p)} disabled={busy === p.id} autoFocus>
                      {busy === p.id ? 'Paying…' : `Yes, approve ${usd(p.amount)}`}
                    </button>
                    <button type="button" className="btn-ghost" onClick={() => setConfirming(null)} disabled={busy === p.id}>Cancel</button>
                  </div>
                ) : (
                  <button type="button" className="btn-approve" onClick={() => setConfirming(p.id)} disabled={!nameOk || busy !== null}>
                    Approve {noun}
                  </button>
                )}
                <p className="action-foot">
                  {!nameOk
                    ? 'Enter your name above to approve.'
                    : ticket
                      ? others
                        ? `↻ Ticket #${ticket} re-runs after its last sign-off (${others} more).`
                        : `↻ The team re-runs ticket #${ticket} automatically after you approve.`
                      : ''}
                </p>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

/** Small paid/refused history for the sidebar. */
export function ApprovalHistory({ payments }: { payments: PaymentRequest[] }) {
  const done = payments.filter((p) => p.status !== 'awaiting_human_approval').slice().reverse()
  if (done.length === 0) return null
  return (
    <section className="side-block" aria-labelledby="history-title">
      <details className="history">
        <summary><h2 id="history-title" className="side-title inline">Payment history ({done.length})</h2></summary>
        <ul>
          {done.map((p) => (
            <li key={p.id} className={p.status}>
              <span aria-hidden="true">{p.status === 'paid' ? '✓' : '✗'} </span>
              {p.status === 'paid' ? 'Paid' : 'Refused'} {usd(p.amount)} · {p.payee}
              {p.approved_by && <span className="muted"> · {p.approved_by}</span>}
              {p.refusal && <span className="muted"> ({p.refusal})</span>}
            </li>
          ))}
        </ul>
      </details>
    </section>
  )
}
