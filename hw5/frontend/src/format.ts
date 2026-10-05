export const usd = (n: number) => n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })

export const clock = (iso: string) =>
  new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })

export const STATUS: Record<string, { label: string; icon: string }> = {
  open: { label: 'Open', icon: '○' },
  in_progress: { label: 'In progress', icon: '◐' },
  blocked: { label: 'Blocked', icon: '⛔' },
  awaiting_approval: { label: 'Awaiting sign-off', icon: '✋' },
  awaiting_human_approval: { label: 'Awaiting sign-off', icon: '✋' },
  resolved: { label: 'Resolved', icon: '✓' },
  running: { label: 'Agents working', icon: '⟳' },
}

export const statusOf = (s: string) => STATUS[s] ?? { label: s.replace(/_/g, ' '), icon: '•' }

export const TYPE_LABEL: Record<string, string> = {
  customer_order: 'Customer order',
  rent_notice: 'Rent notice',
  price_override: 'Bulk discount',
}
