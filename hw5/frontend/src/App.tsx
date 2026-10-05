import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useDesk } from './useDesk'
import { agentSummaries, buildRuns, feedLine, handoffs, lastResetSeq, latestRun } from './derive'
import { agentOf } from './agents'
import { CashLedger } from './components/CashLedger'
import { TicketList } from './components/TicketList'
import { TicketDetail } from './components/TicketDetail'
import { ActivityFeed } from './components/ActivityFeed'
import { AgentCrew } from './components/AgentCrew'
import { ApprovalHistory, SignOffBanner } from './components/ApprovalQueue'
import { ResetDialog } from './components/ResetDialog'
import { DraftDialog } from './components/DraftDialog'
import type { CustomerDraft } from './components/DraftDialog'
import type { Run } from './derive'

export default function App() {
  const desk = useDesk()
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [announcement, setAnnouncement] = useState('')
  const announcedSeq = useRef(0)

  const runs = useMemo(() => buildRuns(desk.events), [desk.events])
  const resetSeq = useMemo(() => lastResetSeq(desk.events), [desk.events])
  const selected = desk.tickets.find((t) => t.id === selectedId) ?? desk.tickets[0] ?? null
  const run = selected ? latestRun(runs, selected.id, resetSeq) : null
  const summaries = useMemo(() => agentSummaries(run), [run])
  const flow = useMemo(() => handoffs(run), [run])
  const ticketOfRun = useCallback((runId: string) => runs.find((r) => r.runId === runId)?.ticketId ?? null, [runs])

  const pending = desk.payments.filter((p) => p.status === 'awaiting_human_approval')
  const pendingByTicket = useMemo(() => {
    const m = new Map<number, number>()
    for (const p of pending) {
      const t = p.ticket_id ?? ticketOfRun(p.run_id)
      if (t !== null) m.set(t, (m.get(t) ?? 0) + p.amount)
    }
    return m
  }, [pending, ticketOfRun])
  const paymentsForTicket = desk.payments.filter((p) => selected && (p.ticket_id ?? ticketOfRun(p.run_id)) === selected.id)

  const announce = useCallback((msg: string) => setAnnouncement(msg), [])

  // Customer Service drafts. A run that finishes with a draft pops it up once, even if another
  // run (e.g. the automatic re-run after an approval) has already started on the same ticket.
  const draftsOf = useCallback(
    (r: Run) => agentSummaries(r).find((s) => s.id === 'customer_service')?.customerDrafts ?? [],
    [],
  )
  const draftRuns = useMemo(
    () => runs.filter((r) => r.startSeq > resetSeq && r.status === 'done' && draftsOf(r).length > 0),
    [runs, resetSeq, draftsOf],
  )
  const ticketDraftRun = selected ? [...draftRuns].reverse().find((r) => r.ticketId === selected.id) ?? null : null
  const [popup, setPopup] = useState<{ ticketId: number; drafts: CustomerDraft[] } | null>(null)
  const draftsPrimed = useRef(false)
  useEffect(() => {
    if (!desk.loaded) return
    const seen = new Set<string>(JSON.parse(localStorage.getItem('seenDraftRuns') ?? '[]'))
    const fresh = draftRuns.filter((r) => !seen.has(r.runId))
    if (fresh.length === 0) {
      draftsPrimed.current = true
      return
    }
    fresh.forEach((r) => seen.add(r.runId))
    localStorage.setItem('seenDraftRuns', JSON.stringify([...seen].slice(-100)))
    // Drafts from runs that finished before this page opened are only marked as seen.
    if (!draftsPrimed.current) {
      draftsPrimed.current = true
      return
    }
    const newest = fresh[fresh.length - 1]
    setPopup({ ticketId: newest.ticketId, drafts: draftsOf(newest) })
  }, [draftRuns, desk.loaded, draftsOf])

  // After an approval the backend may re-run the ticket on its own: follow it on screen.
  const approve = useCallback(
    async (id: number, approver: string) => {
      const res = await desk.approve(id, approver)
      if (res.auto_rerun?.status === 'started') setSelectedId(res.auto_rerun.ticket_id)
      return res
    },
    [desk],
  )

  // Screen readers hear one short line per poll (the newest step), not every event.
  useEffect(() => {
    const newest = desk.events[desk.events.length - 1]
    if (!newest || newest.seq <= announcedSeq.current) return
    const first = announcedSeq.current === 0
    announcedSeq.current = newest.seq
    if (first || !desk.activeRun) return
    const line = feedLine(newest)
    if (line) setAnnouncement(`${agentOf(line.agent).name} ${line.text}`)
  }, [desk.events, desk.activeRun])

  return (
    <div className="app">
      <a className="skip" href="#workspace">Skip to the ticket workspace</a>
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">CC</span>
          <h1>Campus Customs <span className="brand-sub">Operations Desk</span></h1>
        </div>
        <p className="brand-tag">Five AI agents work the tickets. You approve the money.</p>
        <ResetDialog disabled={!!desk.activeRun} onReset={desk.reset} />
      </header>

      <div className="shell">
        <aside className="sidebar" aria-label="Cash and tickets">
          <CashLedger cash={desk.cash} payments={desk.payments} onAnnounce={announce} />
          <TicketList
            tickets={desk.tickets}
            selectedId={selected?.id ?? null}
            runningTicketId={desk.activeRun?.ticket_id ?? null}
            pendingByTicket={pendingByTicket}
            onSelect={setSelectedId}
          />
          <ApprovalHistory payments={desk.payments} />
        </aside>

        <main id="workspace" className="main" aria-busy={!desk.loaded}>
          {desk.offline && <p className="alert" role="alert">{desk.offline} Retrying automatically…</p>}
          {selected ? (
            <TicketDetail
              ticket={selected}
              run={run}
              activeRun={desk.activeRun}
              paymentsForTicket={paymentsForTicket}
              onRun={desk.runTicket}
              hasDraft={!!ticketDraftRun}
              onShowDraft={() => ticketDraftRun && setPopup({ ticketId: ticketDraftRun.ticketId, drafts: draftsOf(ticketDraftRun) })}
            />
          ) : (
            <section className="card"><p className="empty">{desk.loaded ? 'No tickets found.' : 'Loading the desk…'}</p></section>
          )}
          <SignOffBanner payments={desk.payments} ticketOfRun={ticketOfRun} onApprove={approve} />
          <div className="split">
            <ActivityFeed run={run} />
            <AgentCrew summaries={summaries} hasRun={!!run} handoffs={flow} />
          </div>
        </main>
      </div>

      <DraftDialog open={!!popup} ticketId={popup?.ticketId ?? null} drafts={popup?.drafts ?? []} onClose={() => setPopup(null)} />
      <p className="sr-only" role="status" aria-live="polite">{announcement}</p>
    </div>
  )
}
