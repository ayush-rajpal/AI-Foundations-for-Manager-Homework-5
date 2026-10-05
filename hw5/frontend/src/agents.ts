// Each agent has a colour, a glyph, and a badge shape, so they stay distinguishable without colour.

export interface AgentIdentity {
  id: string
  name: string
  short?: string
  glyph: string
  shape: 'square' | 'round' | 'hex' | 'house' | 'bubble' | 'plain'
  role: string
}

export const AGENTS: AgentIdentity[] = [
  { id: 'boss', name: 'Boss', glyph: '♛', shape: 'square', role: 'Triages tickets, delegates, makes the final call' },
  { id: 'inventory', name: 'Inventory', glyph: '▦', shape: 'round', role: 'Stock, shortfalls, vendors, lead times' },
  { id: 'accounting', name: 'Accounting', glyph: '$', shape: 'hex', role: 'Cash, margins, drafts payments & purchases' },
  { id: 'facilities', name: 'Facilities', glyph: '⌂', shape: 'house', role: 'Lease, rent amount and due date' },
  { id: 'customer_service', name: 'Customer Service', short: 'Cust. Service', glyph: '✉', shape: 'bubble', role: 'Drafts customer replies (never sent)' },
]

const EXTRA: Record<string, AgentIdentity> = {
  runner: { id: 'runner', name: 'Desk', glyph: '●', shape: 'plain', role: 'Run start and finish' },
  human: { id: 'human', name: 'You', glyph: '✍', shape: 'plain', role: 'Human approvals and resets' },
}

export function agentOf(id: string): AgentIdentity {
  return AGENTS.find((a) => a.id === id) ?? EXTRA[id] ?? { id, name: id, glyph: '•', shape: 'plain', role: '' }
}
