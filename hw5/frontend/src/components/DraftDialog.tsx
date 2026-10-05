import { useEffect, useRef } from 'react'

export interface CustomerDraft {
  to: string
  subject: string
  body: string
}

interface Props {
  open: boolean
  ticketId: number | null
  drafts: CustomerDraft[]
  onClose: () => void
}

/** Pop-up with Customer Service's draft reply. Native <dialog>: focus trap and Esc to close. */
export function DraftDialog({ open, ticketId, drafts, onClose }: Props) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) d.showModal()
    if (!open && d.open) d.close()
  }, [open])

  return (
    <dialog ref={ref} className="dialog draft-dialog" aria-labelledby="draft-title" onClose={onClose}>
      <div className="draft-dialog-head">
        <div>
          <p className="draft-tag">Draft · not sent{ticketId ? ` · ticket #${ticketId}` : ''}</p>
          <h2 id="draft-title">Customer reply from Customer Service</h2>
        </div>
        <button type="button" className="icon-btn" aria-label="Close draft" onClick={() => ref.current?.close()} autoFocus>
          ✕
        </button>
      </div>
      {drafts.map((d, i) => (
        <article key={i} className="draft-letter">
          <p className="draft-meta"><span className="muted">To:</span> {d.to}</p>
          <p className="draft-meta"><span className="muted">Subject:</span> <strong>{d.subject}</strong></p>
          <p className="draft-letter-body">{d.body}</p>
        </article>
      ))}
      <p className="hint">Drafts stay on the board. Nothing is emailed to the customer.</p>
    </dialog>
  )
}
