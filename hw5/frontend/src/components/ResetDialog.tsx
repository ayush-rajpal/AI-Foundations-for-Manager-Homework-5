import { useRef, useState } from 'react'

/** "Reset desk" button + confirmation dialog (native <dialog>: focus trap and Esc for free). */
export function ResetDialog({ disabled, onReset }: { disabled: boolean; onReset: () => Promise<void> }) {
  const ref = useRef<HTMLDialogElement>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function confirm() {
    setBusy(true)
    setError(null)
    try {
      await onReset()
      ref.current?.close()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <button
        type="button"
        className="btn-reset"
        onClick={() => ref.current?.showModal()}
        disabled={disabled}
        title={disabled ? 'Wait for the current run to finish' : undefined}
      >
        Reset desk
      </button>
      <dialog ref={ref} className="dialog" aria-labelledby="reset-title" aria-describedby="reset-desc">
        <h2 id="reset-title">Reset the desk?</h2>
        <p id="reset-desc">
          This copies the clean database over the working copy: all three tickets reopen, checking goes back to
          its starting balance, and the approval queue is cleared. The audit trail is kept.
        </p>
        {error && <p className="alert" role="alert">{error}</p>}
        <div className="dialog-actions">
          <button type="button" className="btn-ghost" onClick={() => ref.current?.close()} disabled={busy}>
            Cancel
          </button>
          <button type="button" className="btn-danger" onClick={confirm} disabled={busy}>
            {busy ? 'Resetting…' : 'Reset desk'}
          </button>
        </div>
      </dialog>
    </>
  )
}
