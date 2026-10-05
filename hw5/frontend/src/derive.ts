// Pure helpers that turn the audit-trail events into runs, feed lines, hand-offs, and agent summaries.
import { AGENTS, agentOf } from './agents'
import type { DeskEvent, PaymentRequest, RuleCheck, TicketResolution } from './types'

export interface Run {
  runId: string
  ticketId: number
  startSeq: number
  status: 'running' | 'done' | 'error'
  events: DeskEvent[]
  tokens: number | null
  error: string | null
}

export function lastResetSeq(events: DeskEvent[]): number {
  return events.reduce((max, e) => (e.event === 'db_reset' ? Math.max(max, e.seq) : max), 0)
}

/** API ticket runs (they carry ticket_id), oldest first. */
export function buildRuns(events: DeskEvent[]): Run[] {
  const runs = new Map<string, Run>()
  for (const e of events) {
    if (e.event === 'run_started' && typeof e.ticket_id === 'number') {
      runs.set(e.run_id, { runId: e.run_id, ticketId: e.ticket_id, startSeq: e.seq, status: 'running', events: [], tokens: null, error: null })
    }
    const run = runs.get(e.run_id)
    if (!run) continue
    run.events.push(e)
    if (e.event === 'run_finished') {
      run.status = 'done'
      run.tokens = typeof e.tokens_used === 'number' ? e.tokens_used : null
    }
    if (e.event === 'run_error') {
      run.status = 'error'
      run.error = String(e.error ?? 'Run failed')
    }
  }
  return [...runs.values()]
}

/** The newest run for a ticket since the last database reset. */
export function latestRun(runs: Run[], ticketId: number, sinceSeq: number): Run | null {
  const mine = runs.filter((r) => r.ticketId === ticketId && r.startSeq > sinceSeq)
  return mine.length ? mine[mine.length - 1] : null
}

/** Read a field from an agent_output event: the short field if logged, else the full `output`
 *  (an object, or JSON text cut off at ~4000 chars, from which string fields are recovered). */
export function outputField(e: DeskEvent, key: string): unknown {
  if (e[key] !== undefined) return e[key]
  const out = e.output
  if (out && typeof out === 'object') return (out as Record<string, unknown>)[key]
  if (typeof out === 'string') {
    const m = out.match(new RegExp(`"${key}":\\s*"((?:[^"\\\\]|\\\\.)*)"`))
    if (m) {
      try {
        return JSON.parse(`"${m[1]}"`)
      } catch {
        return m[1]
      }
    }
  }
  return undefined
}

export function bossResolution(run: Run | null): TicketResolution | null {
  if (!run) return null
  const outs = run.events.filter((e) => e.event === 'agent_output' && e.agent === 'boss')
  const last = outs[outs.length - 1]
  if (!last) return null
  const tickets = (outputField(last, 'tickets') as TicketResolution[] | undefined) ?? []
  const mine = Array.isArray(tickets) ? tickets.find((t) => t.ticket_id === run.ticketId) ?? tickets[0] : undefined
  if (mine) return mine
  const decision = outputField(last, 'decision') ?? outputField(last, 'summary')
  return typeof decision === 'string' ? { ticket_id: run.ticketId, status: 'in_progress', decision } : null
}

/** The latest "[date agent: old -> new] note" line the agents appended to a ticket's notes. */
/** True when the desk resolved the ticket after Customer Service drafted the customer reply. */
export function emailAwaitingResponse(status: string, notes: string | null): boolean {
  return status === 'resolved' && /email sent to customer/i.test(latestTicketNote(notes)?.note ?? '')
}

export function latestTicketNote(notes: string | null): { who: string; change: string; note: string } | null {
  const lines = (notes ?? '').split('\n').filter((l) => l.startsWith('['))
  const m = lines[lines.length - 1]?.match(/^\[(\S+) ([^:]+): ([^\]]+)\]\s*(.*)$/)
  return m ? { who: m[2], change: m[3], note: m[4] } : null
}

/** Starting cash for this desk session: balance now + everything paid since the last reset
 *  (cash only goes out, and the approval queue is cleared on every reset). */
export function startingCash(balance: number, payments: PaymentRequest[]): number {
  return balance + payments.filter((p) => p.status === 'paid').reduce((sum, p) => sum + p.amount, 0)
}

// ---------------------------------------------------------------- feed

export type FeedTone = 'speak' | 'tool' | 'money' | 'report' | 'warn' | 'system'

export interface FeedLine {
  seq: number
  ts: string
  agent: string // whose name leads the line (and whose colour it wears)
  tone: FeedTone
  text: string // plain-language action, after the agent's name
  body?: string // plain-language detail (a task, a summary, a refusal reason)
  data?: unknown // raw technical payload, shown only under "View data"
}

function short(value: unknown, max = 160): string {
  if (value == null) return ''
  const text = typeof value === 'string' ? value : JSON.stringify(value)
  return text.length > max ? text.slice(0, max - 1) + '…' : text
}

const money = (n: unknown) =>
  typeof n === 'number' ? n.toLocaleString('en-US', { style: 'currency', currency: 'USD' }) : String(n)

const cleanError = (err: unknown) => String(err ?? '').replace(/^ToolFailed:\s*/, '')

export function feedLine(e: DeskEvent): FeedLine | null {
  const name = (id: unknown) => agentOf(String(id)).name
  const base = { seq: e.seq, ts: e.ts, agent: e.agent }
  switch (e.event) {
    case 'run_started':
      return { ...base, tone: 'system', text: `started the agent team on ticket #${e.ticket_id}` }
    case 'agent_started': {
      const chain = (e.chain as string[] | undefined) ?? []
      return chain.length <= 1 ? { ...base, tone: 'speak', text: 'picked up the ticket', body: short(e.task, 260) } : null
    }
    case 'delegation_started':
      return { ...base, tone: 'speak', text: `handed a task to ${name(e.to_agent)}`, body: short(e.task, 300) }
    case 'delegation_done':
      return { ...base, agent: String(e.to_agent), tone: 'report', text: `reported back to ${name(e.agent)}`, data: e.report }
    case 'delegation_refused':
      return { ...base, tone: 'warn', text: `couldn't hand off to ${name(e.to_agent)}`, body: short(e.reason, 220) }
    case 'delegation_error':
      return { ...base, tone: 'warn', text: `got no answer from ${name(e.to_agent)}`, body: short(e.error, 220) }
    case 'tool_call':
      if (e.tool === 'read_board') return { ...base, tone: 'tool', text: 'read the team board', data: e.result }
      return { ...base, tone: 'tool', text: `ran ${e.tool}`, data: { args: e.args, result: e.result } }
    case 'tool_error':
      return { ...base, tone: 'warn', text: `was refused by ${e.tool}`, body: short(cleanError(e.error), 240), data: { args: e.args, error: e.error } }
    case 'payment_drafted': {
      const d = (e.draft ?? {}) as Record<string, unknown>
      const what = d.kind === 'purchase' ? 'purchase' : 'payment'
      return { ...base, tone: 'money', text: `drafted a ${money(d.amount)} ${what} to ${d.payee}. It needs your sign-off.`, body: short(d.description, 200), data: d }
    }
    case 'agent_output':
      return { ...base, tone: 'report', text: 'finished and reported', body: short(outputField(e, 'summary'), 360), data: e.output }
    case 'run_finished':
      return { ...base, tone: 'system', text: 'run finished', body: `${e.delegations ?? 0} hand-offs · ${e.payment_drafts ?? 0} drafts · ${Number(e.tokens_used ?? 0).toLocaleString()} tokens` }
    case 'run_error':
      return { ...base, tone: 'warn', text: 'run failed', body: short(e.error, 240) }
    default:
      return null
  }
}

// ---------------------------------------------------------------- hand-offs (delegation flowchart)

export interface Handoff {
  seq: number
  from: string
  to: string
  status: 'active' | 'done' | 'error' | 'refused'
}

/** Every hand-off in a run, in order, with whether it finished. */
export function handoffs(run: Run | null): Handoff[] {
  if (!run) return []
  const list: Handoff[] = []
  for (const e of run.events) {
    const to = String(e.to_agent ?? '')
    if (e.event === 'delegation_started') list.push({ seq: e.seq, from: e.agent, to, status: 'active' })
    if (e.event === 'delegation_refused') list.push({ seq: e.seq, from: e.agent, to, status: 'refused' })
    if (e.event === 'delegation_done' || e.event === 'delegation_error') {
      const open = list.find((h) => h.from === e.agent && h.to === to && h.status === 'active')
      if (open) open.status = e.event === 'delegation_done' ? 'done' : 'error'
    }
  }
  if (run.status !== 'running') for (const h of list) if (h.status === 'active') h.status = 'error'
  return list
}

// ---------------------------------------------------------------- agent summaries

export interface AgentSummary {
  id: string
  state: 'idle' | 'working' | 'done' | 'error'
  summary: string | null
  askedBy: string[]
  delegatedTo: string[]
  tools: [string, number][]
  drafts: { amount: number; payee: string; kind: string }[]
  customerDrafts: { to: string; subject: string; body: string }[]
  checks: RuleCheck[]
  errors: string[]
}

export function agentSummaries(run: Run | null): AgentSummary[] {
  return AGENTS.map((a) => {
    const s: AgentSummary = { id: a.id, state: 'idle', summary: null, askedBy: [], delegatedTo: [], tools: [], drafts: [], customerDrafts: [], checks: [], errors: [] }
    if (!run) return s
    const toolCounts = new Map<string, number>()
    let started = 0
    let finished = 0
    for (const e of run.events) {
      if (e.event === 'delegation_started' && e.to_agent === a.id && !s.askedBy.includes(e.agent)) s.askedBy.push(e.agent)
      if (e.agent !== a.id) continue
      if (e.event === 'agent_started') started++
      if (e.event === 'agent_output') {
        finished++
        const summary = outputField(e, 'summary')
        const checks = outputField(e, 'rule_checks')
        const drafts = outputField(e, 'drafts')
        if (typeof summary === 'string') s.summary = summary
        if (Array.isArray(checks)) s.checks = checks as RuleCheck[]
        if (Array.isArray(drafts)) s.customerDrafts = drafts as AgentSummary['customerDrafts']
      }
      if (e.event === 'delegation_started' && !s.delegatedTo.includes(String(e.to_agent))) s.delegatedTo.push(String(e.to_agent))
      if (e.event === 'tool_call' && e.tool !== 'read_board') toolCounts.set(String(e.tool), (toolCounts.get(String(e.tool)) ?? 0) + 1)
      if (e.event === 'tool_error') s.errors.push(short(cleanError(e.error), 160))
      if (e.event === 'payment_drafted') {
        const d = (e.draft ?? {}) as Record<string, unknown>
        s.drafts.push({ amount: Number(d.amount), payee: String(d.payee), kind: String(d.kind) })
      }
    }
    s.tools = [...toolCounts.entries()]
    if (started > finished) s.state = run.status === 'running' ? 'working' : 'error'
    else if (finished > 0) s.state = 'done'
    return s
  })
}
