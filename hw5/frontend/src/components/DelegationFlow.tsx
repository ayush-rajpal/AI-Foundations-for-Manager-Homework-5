import type { Handoff } from '../derive'
import { AGENTS, agentOf } from '../agents'

// Boss on top, the four specialists in a row below (SVG user units).
const POS: Record<string, { x: number; y: number }> = {
  boss: { x: 320, y: 34 },
  inventory: { x: 80, y: 150 },
  accounting: { x: 240, y: 150 },
  facilities: { x: 400, y: 150 },
  customer_service: { x: 560, y: 150 },
}
const W = 150
const H = 44

function edgePath(from: string, to: string): string {
  const a = POS[from]
  const b = POS[to]
  if (!a || !b) return ''
  if (a.y < b.y) return `M ${a.x} ${a.y + H / 2} L ${b.x} ${b.y - H / 2 - 4}` // Boss -> specialist
  if (a.y > b.y) return `M ${a.x} ${a.y - H / 2} L ${b.x} ${b.y + H / 2 + 4}` // specialist -> Boss
  const dip = 22 + Math.abs(b.x - a.x) * 0.08 // specialist -> specialist: arc underneath
  return `M ${a.x} ${a.y + H / 2} Q ${(a.x + b.x) / 2} ${a.y + H / 2 + dip * 2} ${b.x} ${b.y + H / 2 + 4}`
}

const STATUS_TEXT: Record<Handoff['status'], string> = {
  active: 'working now',
  done: 'reported back',
  error: "didn't finish",
  refused: 'refused (loop guard)',
}

/** Arrows between the agents for every hand-off in this run. Live hand-offs glow and animate. */
export function DelegationFlow({ list, working }: { list: Handoff[]; working: string[] }) {
  // One arrow per pair; it takes the latest hand-off's status and lights up again on each new one.
  const pairs = new Map<string, Handoff & { count: number }>()
  for (const h of list) {
    const key = `${h.from}>${h.to}`
    const prev = pairs.get(key)
    pairs.set(key, { ...h, count: (prev?.count ?? 0) + 1 })
  }
  const lastSeq = list.length ? list[list.length - 1].seq : -1

  return (
    <div className="flow">
      <svg className="flow-svg" viewBox="0 0 640 240" aria-hidden="true" focusable="false">
        <defs>
          {AGENTS.map((a) => (
            <marker key={a.id} id={`arrow-${a.id}`} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" className={`agent-${a.id} arrow-head`} />
            </marker>
          ))}
        </defs>
        {/* faint possible routes from the Boss, so the chart reads even before a run */}
        {AGENTS.filter((a) => a.id !== 'boss').map((a) => (
          <path key={`base-${a.id}`} d={edgePath('boss', a.id)} className="edge-base" />
        ))}
        {[...pairs.values()].map((h) => (
          <g key={`${h.from}>${h.to}-${h.seq}`} className={`edge edge-${h.status} agent-${h.from} ${h.seq === lastSeq ? 'edge-latest' : ''}`}>
            <path d={edgePath(h.from, h.to)} markerEnd={`url(#arrow-${h.from})`} />
            {h.count > 1 && (() => {
              const a = POS[h.from], b = POS[h.to]
              return a && b ? <text x={(a.x + b.x) / 2 + 6} y={(a.y + b.y) / 2 + (a.y === b.y ? 44 : 0)} className="edge-count">×{h.count}</text> : null
            })()}
          </g>
        ))}
        {AGENTS.map((a) => {
          const p = POS[a.id]
          const involved = list.some((h) => h.from === a.id || h.to === a.id)
          return (
            <g key={a.id} className={`node agent-${a.id} ${involved ? 'node-on' : ''} ${working.includes(a.id) ? 'node-working' : ''}`}>
              <rect x={p.x - W / 2} y={p.y - H / 2} width={W} height={H} rx={12} />
              <text x={p.x - W / 2 + 20} y={p.y + 5} className="node-glyph">{a.glyph}</text>
              <text x={p.x - W / 2 + 36} y={p.y + 5} className="node-name">{a.short ?? a.name}</text>
            </g>
          )
        })}
      </svg>

      {list.length === 0 ? (
        <p className="empty">No hand-offs yet. Arrows light up as agents pass work to each other.</p>
      ) : (
        <ol className="handoffs" aria-label="Hand-offs in order">
          {list.map((h, i) => (
            <li key={h.seq} className={`handoff status-${h.status}`}>
              <span className="handoff-n" aria-hidden="true">{i + 1}</span>
              <span className={`who agent-${h.from}`}>{agentOf(h.from).name}</span>
              <span aria-hidden="true"> → </span>
              <span className="sr-only"> handed off to </span>
              <span className={`who agent-${h.to}`}>{agentOf(h.to).name}</span>
              <span className="handoff-status">{STATUS_TEXT[h.status]}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
