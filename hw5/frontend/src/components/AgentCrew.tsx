import type { AgentSummary, Handoff } from '../derive'
import { agentOf } from '../agents'
import { usd } from '../format'
import { DelegationFlow } from './DelegationFlow'

const STATE_LABEL: Record<AgentSummary['state'], string> = {
  idle: 'Not involved',
  working: 'Working…',
  done: 'Done',
  error: "Didn't finish",
}

/** One card per agent: what it did on the selected ticket's latest run. */
export function AgentCrew({ summaries, hasRun, handoffs }: { summaries: AgentSummary[]; hasRun: boolean; handoffs: Handoff[] }) {
  return (
    <section className="card crew" aria-labelledby="crew-title">
      <div className="card-head">
        <h2 id="crew-title" className="card-title">Crew &amp; hand-offs</h2>
        {!hasRun && <span className="hint">Fills in once the team runs</span>}
      </div>
      <div className="scroll-body">
      <h3 className="sub-title">Who handed work to whom</h3>
      <DelegationFlow list={handoffs} working={summaries.filter((s) => s.state === 'working').map((s) => s.id)} />
      <h3 className="sub-title">What each agent did</h3>
      <ul className="crew-grid">
        {summaries.map((s) => {
          const a = agentOf(s.id)
          return (
            <li key={s.id} className={`agent-card agent-${s.id} state-${s.state}`}>
              <div className="agent-head">
                <span className={`badge shape-${a.shape} agent-${s.id}`} aria-hidden="true">{a.glyph}</span>
                <div>
                  <h3 className="agent-name">{a.name}</h3>
                  <p className="agent-role">{a.role}</p>
                </div>
                <span className={`state-pill state-${s.state}`}>
                  {s.state === 'working' && <span className="spin" aria-hidden="true">⟳ </span>}
                  {STATE_LABEL[s.state]}
                </span>
              </div>

              {s.summary ? <p className="agent-summary">{s.summary}</p> : s.state === 'idle' ? (
                <p className="agent-muted">{hasRun ? 'Not called on this run.' : 'Waiting for a run.'}</p>
              ) : null}

              {(s.askedBy.length > 0 || s.delegatedTo.length > 0) && (
                <p className="agent-links">
                  {s.askedBy.length > 0 && <>Asked by {s.askedBy.map((id) => agentOf(id).name).join(', ')}</>}
                  {s.askedBy.length > 0 && s.delegatedTo.length > 0 && ' · '}
                  {s.delegatedTo.length > 0 && <>Handed off to {s.delegatedTo.map((id) => agentOf(id).name).join(', ')}</>}
                </p>
              )}

              {s.tools.length > 0 && (
                <ul className="tool-chips" aria-label={`Tools ${a.name} used`}>
                  {s.tools.map(([tool, n]) => (
                    <li key={tool}><code>{tool}</code>{n > 1 && <span> ×{n}</span>}</li>
                  ))}
                </ul>
              )}

              {s.drafts.length > 0 && (
                <ul className="agent-drafts">
                  {s.drafts.map((d, i) => (
                    <li key={i}>Drafted {usd(d.amount)} {d.kind === 'purchase' ? 'purchase' : 'payment'} to {d.payee}</li>
                  ))}
                </ul>
              )}

              {s.checks.length > 0 && (
                <details className="agent-checks">
                  <summary>
                    {s.checks.filter((c) => c.satisfied).length} rule checks passed
                    {s.checks.some((c) => !c.satisfied) && `, ${s.checks.filter((c) => !c.satisfied).length} not met`}
                  </summary>
                  <ul>
                    {s.checks.map((c, i) => (
                      <li key={i} className={c.satisfied ? 'ok' : 'no'}>
                        <span aria-hidden="true">{c.satisfied ? '✓' : '✗'}</span>
                        <span className="sr-only">{c.satisfied ? 'Met: ' : 'Not met: '}</span>
                        {c.rule}
                      </li>
                    ))}
                  </ul>
                </details>
              )}

              {s.customerDrafts.map((d, i) => (
                <div key={i} className="customer-draft">
                  <p className="draft-tag">Draft · not sent · to {d.to}</p>
                  <p className="draft-subject">{d.subject}</p>
                  <p className="draft-body">{d.body}</p>
                </div>
              ))}

              {s.errors.length > 0 && (
                <p className="agent-errors"><strong>Refused:</strong> {s.errors.join(' · ')}</p>
              )}
            </li>
          )
        })}
      </ul>
      </div>
    </section>
  )
}
