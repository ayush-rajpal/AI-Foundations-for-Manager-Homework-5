import type { Cash, EventsResponse, PaymentRequest, RunState, TicketsResponse } from './types'

export const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(API_BASE + path, { headers: { 'Content-Type': 'application/json' }, ...init })
  } catch {
    throw new ApiError(0, `Can't reach the backend at ${API_BASE}. Is uvicorn running?`)
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  tickets: () => request<TicketsResponse>('/api/tickets'),
  run: (ticketId: number) =>
    request<{ run_id: string; ticket_id: number; message: string }>(`/api/tickets/${ticketId}/run`, { method: 'POST' }),
  events: (since: number) => request<EventsResponse>(`/api/events?since=${since}&limit=1000`),
  payments: () => request<PaymentRequest[]>('/api/payments'),
  approve: (id: number, approvedBy: string) =>
    request<PaymentRequest>(`/api/payments/${id}/approve`, {
      method: 'POST',
      body: JSON.stringify({ approved_by: approvedBy }),
    }),
  cash: () => request<Cash>('/api/cash'),
  reset: () => request<{ balance: number; open_tickets: number; cleared_payment_requests: number }>('/api/reset', { method: 'POST' }),
}

export type { RunState }
