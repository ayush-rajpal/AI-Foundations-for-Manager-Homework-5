// Shapes returned by the FastAPI backend (backend/models.py).

export type TicketStatus = 'open' | 'in_progress' | 'blocked' | 'awaiting_approval' | 'resolved'

export interface Ticket {
  id: number
  type: string
  requester: string
  subject: string
  status: TicketStatus | string
  resolved: boolean
  sku: string | null
  size: string | null
  qty: number | null
  lease_id: number | null
  invoice_id: number | null
  notes: string | null
  created_at: string
}

export interface RuleCheck {
  rule: string
  satisfied: boolean
  evidence: string
}

export interface TicketResolution {
  ticket_id: number
  status: 'resolved' | 'awaiting_human_approval' | 'blocked' | 'in_progress'
  decision: string
  next_steps?: string[]
}

export interface RunState {
  run_id: string
  ticket_id: number
  status: 'running' | 'done' | 'error'
  started_at: string
  finished_at: string | null
  tokens_used: number | null
  payment_requests: number[]
  decision: { summary: string; tickets: TicketResolution[] } | null
  error: string | null
}

export interface TicketsResponse {
  today: string
  tickets: Ticket[]
  active_run: RunState | null
}

export interface DeskEvent {
  ts: string
  run_id: string
  agent: string
  event: string
  seq: number
  [key: string]: unknown
}

export interface EventsResponse {
  events: DeskEvent[]
  last_seq: number
  active_run: RunState | null
  last_run: RunState | null
}

export interface PaymentRequest {
  id: number
  kind: 'invoice' | 'rent' | 'purchase'
  ref_id: number
  payee: string
  amount: number
  account: string
  description: string | null
  due_date: string | null
  balance_before: number
  balance_after: number
  sku: string | null
  size: string | null
  qty: number | null
  details: Record<string, unknown>
  drafted_by: string
  run_id: string
  ticket_id: number | null
  drafted_at: string
  status: 'awaiting_human_approval' | 'paid' | 'refused'
  approved_by: string | null
  payment: Record<string, unknown> | null
  refusal: string | null
  blocked_reason: string | null
  auto_rerun?: { status: 'started' | 'queued' | 'waiting_for_other_approvals'; ticket_id: number; run_id?: string; pending_request_ids?: number[] } | null
}

export interface Cash {
  today: string
  account: string
  balance: number
  as_of: string
  pending_approvals: number
}
