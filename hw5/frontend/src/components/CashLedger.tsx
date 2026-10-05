import { useEffect, useRef, useState } from 'react'
import type { Cash, PaymentRequest } from '../types'
import { usd } from '../format'
import { startingCash } from '../derive'

const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

interface Props {
  cash: Cash | null
  payments: PaymentRequest[]
  onAnnounce: (msg: string) => void
}

/** The checking balance, big, with a meter: paid out, awaiting sign-off, and what's left after. */
export function CashLedger({ cash, payments, onAnnounce }: Props) {
  const [shown, setShown] = useState<number | null>(null)
  const [delta, setDelta] = useState<number | null>(null)
  const prev = useRef<number | null>(null)

  useEffect(() => {
    if (!cash) return
    const from = prev.current
    const to = cash.balance
    prev.current = to
    if (from === null || from === to) {
      setShown(to)
      return
    }
    const change = to - from
    setDelta(change)
    onAnnounce(`Checking balance is now ${usd(to)}, ${change < 0 ? 'down' : 'up'} ${usd(Math.abs(change))}.`)
    if (reducedMotion()) {
      setShown(to)
      return
    }
    const start = performance.now()
    let frame = 0
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / 1100)
      setShown(from + change * (1 - Math.pow(1 - t, 3)))
      if (t < 1) frame = requestAnimationFrame(step)
    }
    frame = requestAnimationFrame(step)
    return () => cancelAnimationFrame(frame)
  }, [cash, onAnnounce])

  const start = cash ? startingCash(cash.balance, payments) : 0
  const paid = cash ? start - cash.balance : 0
  const pending = cash?.pending_approvals ?? 0
  const left = cash ? cash.balance - pending : 0
  const over = left < 0
  const pct = (n: number) => (start > 0 ? `${Math.max(0, Math.min(100, (n / start) * 100))}%` : '0%')
  const meterLabel = cash
    ? `Started at ${usd(start)}. Paid out ${usd(paid)}. ${usd(pending)} awaiting your sign-off. ${over ? `Short by ${usd(-left)}` : `${usd(left)} left after approval`}.`
    : 'Loading balance'

  return (
    <section className="ledger" aria-labelledby="ledger-title">
      <div className="ledger-row">
        <h2 id="ledger-title" className="ledger-label">Checking account</h2>
        {cash && <span className="asof">as of {cash.as_of}</span>}
      </div>
      <p className="ledger-balance">{shown === null ? '—' : usd(shown)}</p>
      {delta !== null && delta !== 0 && (
        <p className={`delta ${delta < 0 ? 'down' : 'up'}`}>
          <span aria-hidden="true">{delta < 0 ? '▼' : '▲'}</span> {usd(Math.abs(delta))} {delta < 0 ? 'paid out just now' : 'restored'}
        </p>
      )}

      {cash && (
        <>
          <div className="meter" role="img" aria-label={meterLabel}>
            <span className="seg seg-paid" style={{ width: pct(paid) }} />
            <span className={`seg seg-pending ${over ? 'over' : ''}`} style={{ width: pct(Math.min(pending, cash.balance)) }} />
            <span className="seg seg-left" style={{ width: pct(Math.max(0, left)) }} />
          </div>
          <ul className="meter-legend" aria-hidden="true">
            <li><span className="key key-start" />Start {usd(start)}</li>
            {paid > 0 && <li><span className="key key-paid" />Paid {usd(paid)}</li>}
            {pending > 0 && <li className={over ? 'bad' : 'warn'}><span className={`key key-pending ${over ? 'over' : ''}`} />Awaiting sign-off −{usd(pending)}</li>}
            <li className={over ? 'bad' : ''}><span className="key key-left" />{over ? `Short ${usd(-left)}` : `Left after approval ${usd(left)}`}</li>
          </ul>
        </>
      )}
    </section>
  )
}
