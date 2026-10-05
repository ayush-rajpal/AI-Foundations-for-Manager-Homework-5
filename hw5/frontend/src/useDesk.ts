import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, api } from './api'
import type { Cash, DeskEvent, PaymentRequest, RunState, Ticket } from './types'

const FAST_POLL_MS = 1200 // while a run is active
const IDLE_POLL_MS = 4000

/** All dashboard state + actions. Every value comes from the FastAPI backend. */
export function useDesk() {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [cash, setCash] = useState<Cash | null>(null)
  const [payments, setPayments] = useState<PaymentRequest[]>([])
  const [events, setEvents] = useState<DeskEvent[]>([])
  const [activeRun, setActiveRun] = useState<RunState | null>(null)
  const [offline, setOffline] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)
  const lastSeq = useRef(0)
  const running = useRef(false)

  const refreshDesk = useCallback(async () => {
    const [t, c, p] = await Promise.all([api.tickets(), api.cash(), api.payments()])
    setTickets(t.tickets)
    setCash(c)
    setPayments(p)
    setActiveRun(t.active_run)
    running.current = !!t.active_run
  }, [])

  const pollEvents = useCallback(async () => {
    const r = await api.events(lastSeq.current)
    if (r.events.length) {
      setEvents((prev) => {
        const top = prev.length ? prev[prev.length - 1].seq : 0
        const fresh = r.events.filter((e) => e.seq > top)
        return fresh.length ? [...prev, ...fresh] : prev
      })
    }
    lastSeq.current = Math.max(lastSeq.current, r.last_seq)
    const nowRunning = !!r.active_run
    const deskChanged = r.events.some(
      (e) => e.event === 'payment_drafted' || (e.event === 'tool_call' && e.tool === 'update_ticket'),
    )
    setActiveRun(r.active_run)
    if ((running.current && !nowRunning) || deskChanged) await refreshDesk()
    running.current = nowRunning
  }, [refreshDesk])

  useEffect(() => {
    let stopped = false
    let timer = 0
    const schedule = () => {
      if (!stopped) timer = window.setTimeout(tick, running.current ? FAST_POLL_MS : IDLE_POLL_MS)
    }
    const tick = async () => {
      try {
        await pollEvents()
        setOffline(null)
      } catch (err) {
        setOffline(err instanceof Error ? err.message : String(err))
      }
      schedule()
    }
    ;(async () => {
      try {
        await refreshDesk()
        await pollEvents()
        setOffline(null)
      } catch (err) {
        setOffline(err instanceof Error ? err.message : String(err))
      } finally {
        setLoaded(true)
        schedule()
      }
    })()
    return () => {
      stopped = true
      window.clearTimeout(timer)
    }
  }, [pollEvents, refreshDesk])

  const runTicket = useCallback(
    async (ticketId: number) => {
      await api.run(ticketId)
      running.current = true
      await pollEvents()
    },
    [pollEvents],
  )

  const approve = useCallback(
    async (id: number, approvedBy: string) => {
      try {
        return await api.approve(id, approvedBy)
      } finally {
        await refreshDesk() // refused/blocked also change what's shown
      }
    },
    [refreshDesk],
  )

  const reset = useCallback(async () => {
    await api.reset()
    await refreshDesk()
    await pollEvents()
  }, [pollEvents, refreshDesk])

  return { tickets, cash, payments, events, activeRun, offline, loaded, runTicket, approve, reset }
}

export { ApiError }
