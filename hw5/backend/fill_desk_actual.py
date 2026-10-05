"""Fill the "Actual" side of output/desk_tickets.html from output/audit_trail.json.

For each ticket it uses every run since the last database reset (the run you started plus
any automatic re-runs after your approvals) and writes: the outcome the Boss recorded, which
agents ran, the Boss's first call, every hand-off in order (with payment drafts and your
approvals between runs), and the MCP tools called, compared with the Expected tools.
The Expected sections are never touched. Safe to run any number of times.
Pass `--reset <ticket>` to clear one ticket's Actual section: it appends a desk_page_reset
marker to the audit trail, and only that ticket's later runs are shown.

The backend calls fill() after every ticket run, approval, and reset. Run by hand with:
  C:\\venvs\\hw5\\Scripts\\python.exe backend\\fill_desk_actual.py
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import audit
from audit import AUDIT_PATH, append
from safe_write import atomic_write_text

PAGE = Path(__file__).resolve().parent.parent / "output" / "desk_tickets.html"

NAMES = {
    "boss": "Boss", "inventory": "Inventory", "accounting": "Accounting",
    "facilities": "Facilities", "customer_service": "Customer Service", "runner": "Desk",
}
TOOL_ONLY_AGENT = {"read_board"}  # team tool, not MCP
STATUS_LABEL = {
    "open": "Open", "in_progress": "In progress", "blocked": "Blocked",
    "awaiting_approval": "Awaiting sign-off", "resolved": "Resolved",
}

CSS = """
<style id="actual-styles">
  .area.actual.filled { background: var(--surface); border-top-color: #1f7a5a; }
  .area.actual.filled .dot { background: #1f7a5a; border: 0; }
  .run-head { display: flex; align-items: center; gap: 8px; margin: 12px 0 6px; font-size: 12.5px; font-weight: 650; color: var(--muted); }
  .run-head:first-child { margin-top: 0; }
  .run-head .run-pill { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 999px; background: #eef1f5; color: var(--ink); }
  .run-head .run-pill.auto { background: #e9f2ff; color: #1f4f9a; }
  .steps li.human::before { content: "\\270D"; background: #39424e; }
  .steps li.money::before { content: "$"; background: #9a5b00; }
  .steps li.record::before { content: "\\2713"; background: #0f2a4a; }
  .steps li.warn::before { content: "!"; background: #b02a2a; }
  .step-note { font-size: 12.5px; color: var(--muted); margin-top: 2px; }
  .status-tag { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; font-weight: 700; padding: 3px 10px; border-radius: 999px; background: #eef1f5; }
  .status-tag.resolved { background: #e3f4ea; color: #1d6b4f; }
  .status-tag.awaiting_approval { background: #fff4dd; color: #7a5200; }
  .status-tag.blocked { background: #fdecec; color: #a02323; }
  .status-tag.in_progress { background: #e6effb; color: #1f5fa8; }
  .outcome-note { margin: 8px 0 0; font-size: 14px; }
  .tool .count { font-weight: 500; opacity: .75; margin-left: 4px; }
  .tool.missing { background: #fdecec; border-color: #f3c4c4; color: #a02323; text-decoration: line-through; }
  .tool.extra { background: #fff4dd; border-color: #f0dca6; color: #7a5200; }
  .tool-legend { margin-top: 8px; font-size: 12.5px; color: var(--muted); }
  .by-agent { margin-top: 8px; display: grid; gap: 4px; font-size: 12.5px; }
  .steps li.email::before { content: "\\2709"; background: #b8325a; }
  .email-draft { margin-top: 6px; background: #fff; border: 1px solid var(--line); border-left: 4px solid #b8325a; border-radius: 8px; padding: 10px 12px; }
  .email-meta { margin: 0; font-size: 13px; }
  .email-meta span { color: var(--muted); }
  .email-body { margin: 8px 0 0; white-space: pre-wrap; font-size: 13.5px; line-height: 1.5; }
</style>
"""


def esc(v: Any) -> str:
    return html.escape(str(v), quote=True)


def short(text: Any, n: int | None = None) -> str:
    """Full text on one line (whitespace collapsed). Never cut off: the page shows everything."""
    return " ".join(str(text or "").split())


def chip(agent: str) -> str:
    return f'<span class="agent {esc(agent)}">{esc(NAMES.get(agent, agent))}</span>'


def money(n: Any) -> str:
    try:
        return f"${float(n):,.2f}"
    except (TypeError, ValueError):
        return str(n)


def load_events() -> list[dict[str, Any]]:
    with audit._lock:  # same lock and lock-tolerant reader as audit.append
        return audit._read(AUDIT_PATH)


def runs_for_ticket(events: list[dict], ticket_id: int, since: int) -> list[tuple[dict, list[dict]]]:
    starts = [e for e in events if e.get("event") == "run_started" and e.get("ticket_id") == ticket_id and e["seq"] > since]
    return [(s, [e for e in events if e.get("run_id") == s["run_id"]]) for s in starts]


def run_steps(evs: list[dict]) -> list[tuple[int, str]]:
    """Ordered hand-offs, drafts, refusals, and the Boss's ticket update for one run."""
    steps: list[tuple[int, str]] = []
    done = {(e["agent"], e.get("to_agent"), i) for i, e in enumerate(evs) if e.get("event") == "delegation_done"}
    for i, e in enumerate(evs):
        kind = e.get("event")
        if kind == "delegation_started":
            ok = any(a == e["agent"] and t == e.get("to_agent") and j > i for a, t, j in done)
            note = "" if ok else '<p class="step-note">did not report back</p>'
            steps.append((e["seq"],
                f'<li data-agent="{esc(e.get("to_agent"))}"><div><div class="step-who">{chip(e["agent"])}'
                f'<span class="arrow">→</span>{chip(e.get("to_agent", ""))}</div>'
                f'<p class="step-text">{esc(short(e.get("task")))}</p>{note}</div></li>'
            ))
        elif kind == "delegation_refused":
            steps.append((e["seq"],
                f'<li class="warn"><div><div class="step-who">{chip(e["agent"])}<span class="arrow">↛</span>'
                f'{chip(e.get("to_agent", ""))}</div><p class="step-text">Hand-off refused: {esc(short(e.get("reason"), 200))}</p></div></li>'
            ))
        elif kind == "payment_drafted":
            d = e.get("draft") or {}
            what = "restock purchase" if d.get("kind") == "purchase" else f"{d.get('kind', '')} payment"
            steps.append((e["seq"],
                f'<li class="money"><div><div class="step-who">{chip(e["agent"])}</div>'
                f'<p class="step-text">Drafted a {money(d.get("amount"))} {esc(what)} to {esc(d.get("payee"))}'
                f' ({esc(short(d.get("description"), 90))}).</p>'
                f'<span class="approval">⚑ Sent to the human for approval</span></div></li>'
            ))
        elif kind == "agent_output" and e.get("agent") == "customer_service" and e.get("drafts"):
            for d in e["drafts"]:
                steps.append((e["seq"],
                    f'<li class="email"><div><div class="step-who">{chip("customer_service")}</div>'
                    f'<p class="step-text">Drafted the customer email (not sent):</p>'
                    f'<div class="email-draft"><p class="email-meta"><span>To:</span> {esc(d.get("to"))}</p>'
                    f'<p class="email-meta"><span>Subject:</span> <strong>{esc(d.get("subject"))}</strong></p>'
                    f'<p class="email-body">{esc(d.get("body"))}</p></div></div></li>'
                ))
        elif kind == "customer_draft_withheld":
            steps.append((e["seq"],
                f'<li class="warn"><div><div class="step-who">{chip("customer_service")}</div>'
                f'<p class="step-text">Customer reply held back: {esc(short(e.get("reason"), 180))}</p></div></li>'
            ))
        elif kind == "tool_call" and e.get("tool") == "update_ticket":
            a = e.get("args") or {}
            steps.append((e["seq"],
                f'<li class="record"><div><div class="step-who">{chip(e["agent"])}</div>'
                f'<p class="step-text">Recorded the ticket as <strong>{esc(STATUS_LABEL.get(a.get("status"), a.get("status")))}</strong>: '
                f'{esc(short(a.get("note"), 260))}</p></div></li>'
            ))
    return steps


def approvals_between(events: list[dict], drafts: list[dict], after: int, before: int | None) -> list[tuple[int, str]]:
    keys = {(d.get("kind"), d.get("ref_id"), d.get("sku")) for d in drafts}
    out = []
    for e in events:
        if e.get("event") != "payment_approved" or e["seq"] <= after or (before is not None and e["seq"] >= before):
            continue
        r = e.get("result") or {}
        sku = (r.get("updated") or {}).get("ordered", "").split(" x ")[-1].split(" ")[0] if r.get("kind") == "purchase" else None
        if (r.get("kind"), r.get("ref_id"), sku) in keys or (r.get("kind"), r.get("ref_id"), None) in keys:
            out.append((e["seq"],
                f'<li class="human"><div><div class="step-who"><span class="agent human">You</span></div>'
                f'<p class="step-text">Approved {money(r.get("amount"))} to {esc(r.get("payee"))} '
                f'(approved by {esc(e.get("approved_by"))}). Checking {money(r.get("balance_before"))} → {money(r.get("balance_after"))}.</p></div></li>'
            ))
    return out


def actual_article(ticket_id: int, runs: list[tuple[dict, list[dict]]], events: list[dict], expected: list[str]) -> str:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    all_evs = [e for _, evs in runs for e in evs]
    drafts = [e.get("draft") or {} for e in all_evs if e.get("event") == "payment_drafted"]

    # outcome: the Boss's last update_ticket
    updates = [e.get("args") or {} for e in all_evs if e.get("event") == "tool_call" and e.get("tool") == "update_ticket"]
    if updates:
        last = updates[-1]
        status = last.get("status", "")
        outcome = (
            f'<span class="status-tag {esc(status)}">{esc(STATUS_LABEL.get(status, status))}</span>'
            f'<p class="outcome-note">{esc(short(last.get("note"), 400))}</p>'
        )
    else:
        outcome = '<p class="step-note">The Boss has not recorded a status yet.</p>'

    # agents that ran (first appearance order)
    ran: list[str] = []
    for e in all_evs:
        if e.get("event") == "agent_started" and e["agent"] not in ran:
            ran.append(e["agent"])
    ran_html = " ".join(chip(a) for a in ran) or '<p class="step-note">None yet.</p>'

    # Boss first call (first hand-off of the first run)
    first = next((e for e in runs[0][1] if e.get("event") == "delegation_started" and e["agent"] == "boss"), None)
    first_html = (
        f'<div class="first-call">{chip("boss")}<span class="arrow">→</span>{chip(first.get("to_agent", ""))}</div>'
        f'<p class="reason">{esc(short(first.get("task"), 320))}</p>'
        if first else '<p class="step-note">The Boss made no hand-off.</p>'
    )

    # delegation flow per run, with your approvals in between
    flow_parts = []
    for i, (start, evs) in enumerate(runs):
        auto = start.get("trigger") == "auto_after_approval"
        label = "Automatic re-run after your approval" if auto else "Run started by you"
        flow_parts.append(
            f'<p class="run-head"><span class="run-pill{" auto" if auto else ""}">Run {i + 1}</span>{label}</p>'
        )
        chain: list[str] = ["boss"]
        for e in evs:
            if e.get("event") == "delegation_started" and e.get("to_agent") not in chain:
                chain.append(e["to_agent"])
        flow_parts.append('<div class="chain">' + '<span class="arrow">→</span>'.join(chip(a) for a in chain) + "</div>")
        next_start = runs[i + 1][0]["seq"] if i + 1 < len(runs) else None
        steps = [h for _, h in sorted(run_steps(evs) + approvals_between(events, drafts, start["seq"], next_start))]
        flow_parts.append(f'<ol class="steps">{"".join(steps)}</ol>' if steps else '<p class="step-note">No hand-offs.</p>')
    flow_html = "".join(flow_parts)

    # MCP tools: counts, by agent, vs expected
    counts: dict[str, int] = {}
    by_agent: dict[str, dict[str, int]] = {}
    for e in all_evs:
        if e.get("event") == "tool_call" and e.get("tool") not in TOOL_ONLY_AGENT:
            t = e["tool"]
            counts[t] = counts.get(t, 0) + 1
            by_agent.setdefault(e["agent"], {}).setdefault(t, 0)
            by_agent[e["agent"]][t] += 1
    chips = []
    for t in expected:
        if t in counts:
            chips.append(f'<code class="tool">✓ {esc(t)}<span class="count">×{counts[t]}</span></code>')
        else:
            chips.append(f'<code class="tool missing" title="expected, not called">{esc(t)}</code>')
    for t, n in counts.items():
        if t not in expected:
            chips.append(f'<code class="tool extra" title="called, not in the expected list">+ {esc(t)}<span class="count">×{n}</span></code>')
    agent_lines = "".join(
        f'<div>{chip(a)} {esc(", ".join(f"{t} ×{n}" if n > 1 else t for t, n in tools.items()))}</div>'
        for a, tools in by_agent.items()
    )
    tools_html = (
        f'<div class="tools">{"".join(chips)}</div>'
        '<p class="tool-legend">✓ expected and called · <span style="text-decoration:line-through">struck</span> expected but not called · + called but not expected</p>'
        f'<div class="by-agent">{agent_lines}</div>'
    )

    return (
        f'<article class="area actual filled" aria-label="Actual" data-ticket="{ticket_id}">\n'
        f'        <div class="area-head"><span class="dot"></span><h3>Actual</h3><span class="hint">From the audit trail · {len(runs)} run{"s" if len(runs) != 1 else ""} · updated {stamp}</span></div>\n'
        f'        <div class="block"><h4>Outcome</h4>{outcome}</div>\n'
        f'        <div class="block"><h4>Agents that ran</h4><div class="chain">{ran_html}</div></div>\n'
        f'        <div class="block"><h4>Boss first call</h4>{first_html}</div>\n'
        f'        <div class="block"><h4>Delegation flow</h4>{flow_html}</div>\n'
        f'        <div class="block"><h4>MCP tools called</h4>{tools_html}</div>\n'
        f'      </article>'
    )


def empty_article(ticket_id: int) -> str:
    return (
        f'<article class="area actual" aria-label="Actual" data-ticket="{ticket_id}">\n'
        '        <div class="area-head"><span class="dot"></span><h3>Actual</h3><span class="hint">Filled in after the full run</span></div>\n'
        '        <div class="block"><h4>Boss first call</h4><div class="empty" data-slot="first-call"></div></div>\n'
        '        <div class="block"><h4>Delegation flow</h4><div class="empty" data-slot="delegations"></div></div>\n'
        '        <div class="block"><h4>MCP tools called</h4><div class="empty" data-slot="tools"></div></div>\n'
        '      </article>'
    )


def fill(page: Path = PAGE, cash: dict | None = None) -> dict[int, int]:
    """Rewrite the three Actual articles and the Cash tab. Returns {ticket_id: runs used}.

    `cash` is the MCP check_cash result; when not given it is fetched through MCP."""
    from cash_tab import CASH_CSS, cash_section, fetch_cash

    doc = page.read_text(encoding="utf-8")
    # always swap in the current style blocks (so style changes reach an existing page)
    doc = re.sub(r'\n?<style id="(actual|cash)-styles">.*?</style>\n?', "", doc, flags=re.S)
    doc = doc.replace("</head>", CSS + CASH_CSS + "</head>", 1)
    events = load_events()
    subjects = {int(m[0]): m[1] for m in re.findall(r"<h2>Ticket (\d+) · ([^<]+)</h2>", doc)}
    cash_html = cash_section(events, cash if cash is not None else fetch_cash(), subjects)
    doc = re.sub(
        r'(<section role="tabpanel" id="panel-cash"[^>]*>).*?(</section>)',
        lambda m: m.group(1) + "\n    " + cash_html + "\n  " + m.group(2), doc, count=1, flags=re.S,
    )
    since = max((e["seq"] for e in events if e.get("event") == "db_reset"), default=0)
    used = {}
    for tid in (101, 102, 103):
        panel = re.search(rf'<section role="tabpanel" id="panel-t{tid}".*?</section>', doc, re.S)
        expected = re.findall(r'<code class="tool">([a-z_]+)</code>', panel.group(0).split('class="area actual')[0]) if panel else []
        page_reset = max(
            (e["seq"] for e in events if e.get("event") == "desk_page_reset" and e.get("ticket_id") == tid), default=0
        )
        runs = runs_for_ticket(events, tid, max(since, page_reset))
        used[tid] = len(runs)
        new = actual_article(tid, runs, events, expected) if runs else empty_article(tid)
        doc = re.sub(rf'<article class="area actual[^"]*" aria-label="Actual" data-ticket="{tid}">.*?</article>', lambda _m: new, doc, count=1, flags=re.S)
    atomic_write_text(page, doc)
    return used


if __name__ == "__main__":
    import sys

    # --reset <ticket>: clear that ticket's Actual section; only runs after this marker count.
    if len(sys.argv) == 3 and sys.argv[1] == "--reset":
        append("api", "human", "desk_page_reset", ticket_id=int(sys.argv[2]))
    print(fill())
