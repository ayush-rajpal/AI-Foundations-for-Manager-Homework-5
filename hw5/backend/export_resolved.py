"""Export the resolved-ticket record after a full run.

Writes:
  output/resolved_tickets.json : for each ticket: id, final status, short outcome, a plain-language
                                 timeline, what each agent contributed, every human approval, the
                                 customer email draft, and the dashboard screenshot path
  output/resolved_board.html   : the same as an accessible three-tab board (one tab per ticket)
                                 with the dashboard screenshot (output/screenshots/ticket_<id>.png)

Sources: output/audit_trail.json (runs since the last reset) and the running backend's API for
ticket status and cash (both read from the database through the MCP server).
Run from Homework 5:  C:\\venvs\\hw5\\Scripts\\python.exe backend\\export_resolved.py
"""

from __future__ import annotations

import html
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import audit
from audit import AUDIT_PATH

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"
API = "http://127.0.0.1:8000"
NAMES = {"boss": "Boss", "inventory": "Inventory", "accounting": "Accounting",
         "facilities": "Facilities", "customer_service": "Customer Service"}
WHO = {**NAMES, "runner": "Desk"}  # "Desk" = the backend step that marks a finished ticket resolved
STATUS = {"open": "Open", "in_progress": "In progress", "blocked": "Blocked",
          "awaiting_approval": "Awaiting sign-off", "resolved": "Resolved"}
STATUS_ICON = {"open": "○", "in_progress": "◐", "blocked": "⛔", "awaiting_approval": "✋", "resolved": "✓"}
KIND = {"invoice": "invoice payment", "rent": "rent payment", "purchase": "restock purchase"}
TYPE = {"customer_order": "Customer order", "rent_notice": "Rent notice", "price_override": "Bulk discount request"}


def get(path: str) -> Any:
    with urllib.request.urlopen(API + path, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def money(n: Any) -> str:
    return f"${float(n):,.2f}"


def png_size(path: Path) -> tuple[int, int]:
    """Width and height from a PNG header (so the page reserves the right space), or a default."""
    try:
        head = path.read_bytes()[:24]
        return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
    except OSError:
        return 1900, 980


def local_time(iso: str | None) -> str:
    """Same clock as the dashboard screenshots: this machine's local time, 12-hour."""
    if not iso:
        return ""
    dt = datetime.fromisoformat(iso).astimezone()
    tz = dt.tzname() or ""
    if " " in tz:  # Windows gives "Eastern Daylight Time"; show EDT like other platforms
        tz = "".join(w[0] for w in tz.split())
    return dt.strftime("%I:%M:%S %p").lstrip("0") + " " + tz


def build() -> dict[str, Any]:
    events = audit._read(AUDIT_PATH)
    reset = [e for e in events if e.get("event") == "db_reset"][-1]
    since = reset["seq"]
    tickets = {t["id"]: t for t in get("/api/tickets")["tickets"]}
    cash = get("/api/cash")
    requests = {r["id"]: r for r in get("/api/payments")}  # the sign-off queue: exact ticket per request
    start_balance = next(a["balance"] for a in reset["result"]["cash_accounts"] if a["name"] == "checking")
    after = [e for e in events if e["seq"] > since]

    out_tickets = []
    for tid in sorted(tickets):
        t = tickets[tid]
        starts = [e for e in after if e.get("event") == "run_started" and e.get("ticket_id") == tid]
        run_ids = [s["run_id"] for s in starts]
        evs = [e for e in after if e.get("run_id") in run_ids]
        run_no = {rid: i + 1 for i, rid in enumerate(run_ids)}
        mine = {rid: r for rid, r in requests.items() if r.get("ticket_id") == tid}

        # human decisions on this ticket's requests (joined by request_id, so never the wrong ticket)
        approvals, not_paid = [], []
        for e in after:
            rid = e.get("request_id")
            if rid not in mine:
                continue
            req = mine[rid]
            if e.get("event") == "payment_approved":
                r = e.get("result") or {}
                approvals.append({
                    "seq": e["seq"], "request_id": rid, "approved_by": e.get("approved_by"), "approved_at": e.get("ts"),
                    "kind": req["kind"], "payee": req["payee"], "amount": req["amount"], "what": req.get("description"),
                    "balance_before": r.get("balance_before"), "balance_after": r.get("balance_after"),
                    "payment_id": r.get("payment_id"), "updated": r.get("updated"),
                })
            elif e.get("event") in ("payment_blocked", "payment_refused"):
                not_paid.append({"seq": e["seq"], "request_id": rid, "at": e.get("ts"), "event": e["event"],
                                 "kind": req["kind"], "payee": req["payee"], "amount": req["amount"],
                                 "what": req.get("description"), "reason": e.get("error")})
        pending = [{"request_id": r["id"], "kind": r["kind"], "payee": r["payee"], "amount": r["amount"], "what": r.get("description")}
                   for r in mine.values() if r["status"] == "awaiting_human_approval"]
        approval_seqs = [a["seq"] for a in approvals]

        # who asked each agent for each report (the delegation_done that follows names the requester)
        def asked_by(i: int, agent: str) -> str | None:
            for e in evs[i + 1:]:
                if e.get("event") == "delegation_done" and e.get("to_agent") == agent:
                    return NAMES.get(e["agent"], e["agent"])
            return None

        contrib: dict[str, dict[str, Any]] = {}
        for i, e in enumerate(evs):
            a = e.get("agent")
            if a not in NAMES:
                continue
            c = contrib.setdefault(a, {"id": a, "agent": NAMES[a], "reports": [], "handed_off_to": [], "tools": {}, "drafted": [], "refused": []})
            if e.get("event") == "agent_output" and e.get("summary"):
                run_start = next(s["seq"] for s in starts if s["run_id"] == e["run_id"])
                written_after_approval = any(run_start < s < e["seq"] for s in approval_seqs)
                c["reports"].append({"run": run_no[e["run_id"]], "seq": e["seq"], "asked_by": asked_by(i, a) if a != "boss" else None,
                                     "after_approval": written_after_approval, "summary": e["summary"]})
            elif e.get("event") == "delegation_started":
                to = NAMES.get(e.get("to_agent"), e.get("to_agent"))
                if to not in c["handed_off_to"]:
                    c["handed_off_to"].append(to)
            elif e.get("event") in ("tool_call", "tool_error") and e.get("tool") != "read_board":
                c["tools"][e["tool"]] = c["tools"].get(e["tool"], 0) + 1
                if e.get("event") == "tool_error":
                    c["refused"].append(f"{e['tool']}: {str(e.get('error', '')).replace('ToolFailed: ', '')}")
            elif e.get("event") == "payment_drafted":
                d = e.get("draft") or {}
                c["drafted"].append(f"{KIND.get(d.get('kind'), d.get('kind'))} {money(d.get('amount'))} to {d.get('payee')} ({d.get('description')})")

        # plain-language timeline, in true time order
        timeline: list[dict[str, Any]] = []
        for e in evs:
            k = e.get("event")
            who = WHO.get(e.get("agent"), e.get("agent"))
            to = NAMES.get(e.get("to_agent"), e.get("to_agent"))
            item: dict[str, Any] | None = None
            if k == "run_started":
                n = run_no[e["run_id"]]
                if e.get("trigger") == "auto_after_approval":
                    text = f"Run {n} started automatically to pick up the approval(s) made during the earlier run"
                else:
                    text = f"Run {n} started when the operator pressed Run"
                item = {"kind": "run", "actor": "desk", "text": text}
            elif k == "delegation_started":
                item = {"kind": "handoff", "actor": e["agent"], "to": e.get("to_agent"),
                        "text": f"{who} handed work to {to}", "detail": e.get("task")}
            elif k == "delegation_refused":
                item = {"kind": "refused", "actor": e["agent"], "to": e.get("to_agent"),
                        "text": f"{who}'s hand-off to {to} was refused by a guardrail", "detail": e.get("reason")}
            elif k == "tool_error" and str(e.get("tool", "")).startswith("draft"):
                err = str(e.get("error", "")).replace("ToolFailed: ", "")
                already = any(s < e["seq"] for s in approval_seqs)
                item = {"kind": "refused", "actor": e["agent"],
                        "text": f"{who}'s second draft was blocked by the safety check"
                        + (" because the bill was already paid (the duplicate guard working, not a failure)" if already else ""),
                        "detail": err}
            elif k == "payment_drafted":
                d = e.get("draft") or {}
                item = {"kind": "draft", "actor": e["agent"],
                        "text": f"{who} drafted a {money(d.get('amount'))} {KIND.get(d.get('kind'), d.get('kind'))} to {d.get('payee')} and sent it for human approval",
                        "detail": d.get("description")}
            elif k == "customer_draft_withheld":
                item = {"kind": "refused", "actor": "customer_service", "text": "A customer email was held back until the money was settled",
                        "detail": e.get("reason")}
            elif k == "agent_output" and e.get("agent") == "customer_service" and e.get("drafts"):
                d = e["drafts"][-1]
                item = {"kind": "email", "actor": "customer_service",
                        "text": f"Customer Service drafted the email to {d.get('to')} (not sent)", "detail": d.get("subject")}
            elif k == "tool_call" and e.get("tool") == "update_ticket":
                a = e.get("args") or {}
                text = f"{who} recorded the ticket as {STATUS.get(a.get('status'), a.get('status'))}"
                run_start = next(s["seq"] for s in starts if s["run_id"] == e["run_id"])
                earlier = [x for x in approvals if run_start < x["seq"] < e["seq"]]
                if a.get("status") == "awaiting_approval" and earlier:
                    text += (f" (the approval at {local_time(earlier[-1]['approved_at'])} arrived while this run was still working; "
                             "the Boss hadn't re-checked yet, so the automatic next run updated the status)")
                item = {"kind": "status", "actor": e["agent"], "text": text, "detail": a.get("note")}
            elif k == "run_finished":
                item = {"kind": "run", "actor": "desk", "text": f"Run {run_no[e['run_id']]} finished"}
            if item:
                item.update(seq=e["seq"], at=e.get("ts"))
                timeline.append(item)
        for a in approvals:
            timeline.append({"kind": "approval", "actor": "human", "seq": a["seq"], "at": a["approved_at"],
                             "text": f"{a['approved_by']} (human) approved {money(a['amount'])} to {a['payee']}",
                             "detail": f"{a['what']}. Checking {money(a['balance_before'])} → {money(a['balance_after'])}."})
        for n in not_paid:
            verb = "was blocked" if n["event"] == "payment_blocked" else "was refused"
            timeline.append({"kind": "refused", "actor": "human", "seq": n["seq"], "at": n["at"],
                             "text": f"Approving {money(n['amount'])} to {n['payee']} {verb}", "detail": n["reason"]})
        timeline.sort(key=lambda x: x["seq"])

        updates = [e.get("args") or {} for e in evs if e.get("event") == "tool_call" and e.get("tool") == "update_ticket"]
        drafts = [d for e in evs if e.get("event") == "agent_output" and e.get("agent") == "customer_service" for d in (e.get("drafts") or [])]
        out_tickets.append({
            "id": tid,
            "type": t["type"],
            "subject": t["subject"],
            "requester": t["requester"],
            "request": (t.get("notes") or "").split("\n")[0],
            "final_status": t["status"],
            "final_status_label": STATUS.get(t["status"], t["status"]),
            "short_outcome": updates[-1].get("note") if updates else None,
            "runs": [{"run": run_no[s["run_id"]], "run_id": s["run_id"], "trigger": s.get("trigger"), "started_at": s["ts"]} for s in starts],
            "timeline": timeline,
            "agents": list(contrib.values()),
            "human_approvals": approvals,
            "not_paid": not_paid,
            "pending_approvals": pending,
            "money_spent": round(sum(a["amount"] for a in approvals), 2),
            "customer_draft": drafts[-1] if drafts else None,
            "screenshot": f"screenshots/ticket_{tid}.png",
        })

    end_balance = cash["balance"]
    spent = round(sum(t["money_spent"] for t in out_tickets), 2)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "reset_at": reset["ts"],
        "desk_date": cash["today"],
        "screenshots_note": "All three dashboard screenshots were captured after all three tickets finished, with each ticket selected.",
        "cash": {
            "starting_balance": start_balance,
            "total_approved_payments": spent,
            "ending_balance_cash_accounts": end_balance,
            "matches": round(start_balance - spent, 2) == round(end_balance, 2),
        },
        "tickets": out_tickets,
    }


# ---------------------------------------------------------------- HTML board


def esc(v: Any) -> str:
    return html.escape(str(v if v is not None else ""), quote=True)


STEP_ICON = {"run": "▶", "handoff": "→", "draft": "$", "approval": "✍", "email": "✉", "status": "✓", "refused": "!"}


def _panel(t: dict[str, Any], hidden: bool) -> str:
    tid = t["id"]
    st = t["final_status"]
    approved = ", ".join(f"{money(a['amount'])} to {esc(a['payee'])}" for a in t["human_approvals"])
    waiting = ", ".join(f"{money(p['amount'])} to {esc(p['payee'])}" for p in t["pending_approvals"])
    approved_cell = approved or ("none yet" if (waiting or t["not_paid"]) else "none needed")
    outcome = f'''
      <section class="outcome {esc(st)}" aria-labelledby="t{tid}-outcome">
        <h3 id="t{tid}-outcome"><span aria-hidden="true">{STATUS_ICON.get(st, "•")}</span> Outcome: {esc(t["final_status_label"])}</h3>
        <p class="outcome-text">{esc(t["short_outcome"])}</p>
        <dl class="facts">
          <div><dt>Request</dt><dd>“{esc(t["request"])}” from {esc(t["requester"])}</dd></div>
          <div><dt>Runs</dt><dd>{len(t["runs"])} ({"; ".join("run " + str(r["run"]) + (" automatic after approval" if r["trigger"] == "auto_after_approval" else " started by the operator") for r in t["runs"])})</dd></div>
          <div><dt>Human approved</dt><dd>{approved_cell}</dd></div>
          {f'<div><dt>Still waiting</dt><dd>{waiting}</dd></div>' if waiting else ''}
          <div><dt>Money spent</dt><dd>{money(t["money_spent"])}</dd></div>
        </dl>
      </section>'''

    w, h = png_size(OUT / t["screenshot"])
    shot = f'''
      <section aria-labelledby="t{tid}-shot">
        <h3 id="t{tid}-shot">Dashboard screenshot</h3>
        <figure class="shot">
          <a href="{esc(t["screenshot"])}" target="_blank" rel="noopener">
            <img src="{esc(t["screenshot"])}" alt="Operations Desk dashboard with ticket #{tid} selected. Opens full size in a new tab." width="{w}" height="{h}">
          </a>
          <figcaption>Captured after <strong>all three</strong> tickets finished, with ticket #{tid} selected. The $20.00 balance and the green
          “ticket #103” banner show the final state of the desk, not this ticket alone; this ticket's own money is listed below.
          Select the image to open it full size.</figcaption>
        </figure>
      </section>'''

    steps = []
    for s in t["timeline"]:
        actor = s.get("actor", "desk")
        detail = ""
        if s.get("detail"):
            label = {"handoff": "What was asked", "status": "Note recorded", "refused": "Why", "email": "Subject",
                     "draft": "For", "approval": "Details"}.get(s["kind"], "Details")
            detail = (f'<details><summary>{label}</summary><p>{esc(s["detail"])}</p></details>'
                      if s["kind"] in ("handoff", "status", "refused") else f'<p class="step-detail"><span class="muted">{label}:</span> {esc(s["detail"])}</p>')
        steps.append(
            f'<li class="step k-{esc(s["kind"])} a-{esc(actor)}"><span class="step-icon" aria-hidden="true">{STEP_ICON.get(s["kind"], "•")}</span>'
            f'<div><p class="step-text">{esc(s["text"])}</p>{detail}</div><time datetime="{esc(s.get("at"))}">{esc(local_time(s.get("at")))}</time></li>'
        )
    story = f'''
      <section aria-labelledby="t{tid}-story">
        <h3 id="t{tid}-story">What happened, step by step</h3>
        <p class="muted small">Times are local, the same clock as the dashboard screenshots.</p>
        <ol class="steps">{"".join(steps)}</ol>
      </section>'''

    rows = "".join(
        f'<tr><td>{esc(local_time(a["approved_at"]))}</td><td>{esc(KIND.get(a["kind"], a["kind"]))}</td><td>{esc(a["payee"])}</td>'
        f'<td>{esc(a["what"])}</td><td>{esc(a["approved_by"])}</td><td class="num">−{money(a["amount"])}</td>'
        f'<td class="num">{money(a["balance_before"])} → {money(a["balance_after"])}</td></tr>'
        for a in t["human_approvals"]
    )
    rows += "".join(
        f'<tr class="not-paid"><td>{esc(local_time(n["at"]))}</td><td>{esc(KIND.get(n["kind"], n["kind"]))}</td><td>{esc(n["payee"])}</td>'
        f'<td>{esc(n["what"])}<br><span class="muted">{"Blocked" if n["event"] == "payment_blocked" else "Refused"}: {esc(n["reason"])}</span></td>'
        f'<td>—</td><td class="num">not paid</td><td class="num">—</td></tr>'
        for n in t["not_paid"]
    )
    rows += "".join(
        f'<tr class="not-paid"><td>—</td><td>{esc(KIND.get(p["kind"], p["kind"]))}</td><td>{esc(p["payee"])}</td>'
        f'<td>{esc(p["what"])}<br><span class="muted">Still waiting for human approval</span></td><td>—</td><td class="num">{money(p["amount"])}</td><td class="num">—</td></tr>'
        for p in t["pending_approvals"]
    )
    money_html = f'''
      <section aria-labelledby="t{tid}-money">
        <h3 id="t{tid}-money">Money the human approved</h3>
        {"<div class='table-wrap'><table><caption class='sr-only'>Payments for ticket " + str(tid) + "</caption><thead><tr><th scope='col'>Time</th><th scope='col'>Type</th><th scope='col'>Paid to</th><th scope='col'>What for</th><th scope='col'>Approved by</th><th scope='col' class='num'>Amount</th><th scope='col' class='num'>Checking</th></tr></thead><tbody>" + rows + "</tbody></table></div>" if rows else "<p class='muted'>No payments were needed for this ticket.</p>"}
      </section>'''

    d = t["customer_draft"]
    email = f'''
      <section aria-labelledby="t{tid}-email">
        <h3 id="t{tid}-email">Customer email (draft, never sent)</h3>
        {f'<article class="letter" aria-label="Email draft to {esc(d["to"])}"><p class="meta"><span>To:</span> {esc(d["to"])}</p><p class="meta"><span>Subject:</span> <strong>{esc(d["subject"])}</strong></p><p class="body">{esc(d["body"])}</p></article>' if d else "<p class='muted'>No customer email was needed for this ticket.</p>"}
      </section>'''

    def report_label(r: dict[str, Any], n: int, total: int) -> str:
        bits = [f"Run {r['run']}"]
        if total > 1:
            bits.append(f"report {n} of {total}")
        if r.get("asked_by"):
            bits.append(f"asked by {r['asked_by']}")
        label = f'<span class="run">{esc(" · ".join(bits))}</span>'
        if r.get("after_approval"):
            label += ' <span class="note">written after the payment was already approved</span>'
        return label

    cards = []
    for a in t["agents"]:
        reps = a["reports"]
        total = len(reps)
        latest = reps[-1] if reps else None
        earlier = "".join(f'<p>{report_label(r, i + 1, total)} {esc(r["summary"])}</p>' for i, r in enumerate(reps[:-1]))
        tools = ", ".join(f"{k} ×{v}" if v > 1 else k for k, v in a["tools"].items())
        cards.append(
            f'<li class="agent-card a-{esc(a["id"])}"><h4>{esc(a["agent"])}</h4>'
            + (f'<p class="muted small">Handed work to {esc(", ".join(a["handed_off_to"]))}</p>' if a["handed_off_to"] else "")
            + (f'<p class="drafted"><span class="muted">Drafted:</span> {esc("; ".join(a["drafted"]))}</p>' if a["drafted"] else "")
            + (f'<p>{report_label(latest, total, total)} {esc(latest["summary"])}</p>' if latest else "<p>No report.</p>")
            + (f'<details><summary>Earlier report{"s" if total > 2 else ""}</summary>{earlier}</details>' if earlier else "")
            + (f'<p class="small"><span class="muted">Blocked by a safety check:</span> {esc("; ".join(a["refused"]))}</p>' if a["refused"] else "")
            + (f'<p class="tools"><span class="muted">Tools:</span> {esc(tools)}</p>' if tools else "")
            + "</li>"
        )
    agents = f'''
      <section aria-labelledby="t{tid}-agents">
        <h3 id="t{tid}-agents">What each agent contributed</h3>
        <ul class="agents">{"".join(cards)}</ul>
      </section>'''

    return (
        f'<section role="tabpanel" id="panel-{tid}" aria-labelledby="tab-{tid}" tabindex="0" class="panel"{" hidden" if hidden else ""}>'
        f'<h2 class="panel-title">Ticket #{tid}: {esc(t["subject"])} <span class="muted">· {esc(TYPE.get(t["type"], t["type"]))}</span></h2>'
        f'{outcome}{shot}{story}<div class="two">{money_html}{email}</div>{agents}</section>'
    )


def board_html(data: dict[str, Any]) -> str:
    c = data["cash"]
    tabs = "".join(
        f'<button role="tab" id="tab-{t["id"]}" aria-controls="panel-{t["id"]}" aria-selected="{"true" if i == 0 else "false"}"'
        f'{"" if i == 0 else " tabindex=\"-1\""}><span class="tab-id">#{t["id"]}</span> {esc(t["subject"])}'
        f'<span class="tab-status {esc(t["final_status"])}"><span aria-hidden="true">{STATUS_ICON.get(t["final_status"], "•")}</span> {esc(t["final_status_label"])}</span></button>'
        for i, t in enumerate(data["tickets"])
    )
    panels = "".join(_panel(t, hidden=False) for t in data["tickets"])  # JS hides all but one; no-JS shows all
    match = (f'<p class="match ok"><span aria-hidden="true">✓</span> Ending balance matches the database: '
             f'{money(c["ending_balance_cash_accounts"])} = {money(c["starting_balance"])} − {money(c["total_approved_payments"])}</p>'
             if c["matches"] else
             f'<p class="match bad"><span aria-hidden="true">✗</span> Ending balance does not match the database ({money(c["ending_balance_cash_accounts"])}).</p>')
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Campus Customs · Resolved Board</title>
<style>
  :root {{
    --bg:#f4f6f9; --surface:#fff; --ink:#1b2333; --muted:#566074; --line:#dfe4ec; --navy:#13233f; --focus:#c26a00;
    --boss:#8a6400; --inventory:#1f5fa8; --accounting:#1d6b4f; --facilities:#6b3fb5; --customer_service:#b4234e; --human:#334155; --desk:#566074;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink); font:16px/1.55 "Segoe UI",system-ui,-apple-system,Roboto,Arial,sans-serif; }}
  a {{ color:#1f4f9a; }}
  :focus-visible {{ outline:3px solid var(--focus); outline-offset:2px; border-radius:6px; }}
  .sr-only {{ position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap; border:0; }}
  .skip {{ position:absolute; left:12px; top:-60px; background:#ffd27a; color:#111; padding:10px 14px; border-radius:8px; font-weight:700; z-index:5; }}
  .skip:focus {{ top:12px; }}
  .muted {{ color:var(--muted); }} .small {{ font-size:14px; }}
  header.top {{ background:var(--navy); color:#fff; padding:22px 28px 0; }}
  header.top h1 {{ margin:0; font-size:23px; }}
  header.top p {{ margin:6px 0 0; color:#c9d4e6; max-width:900px; }}
  .summary {{ display:flex; flex-wrap:wrap; gap:10px 24px; align-items:center; margin:14px 0 0; padding-bottom:16px; color:#dbe3f0; font-size:15px; }}
  .match {{ margin:0; padding:6px 12px; border-radius:8px; font-weight:600; font-size:14.5px; }}
  .match.ok {{ background:#e3f4ea; color:#145a40; }} .match.bad {{ background:#fdecec; color:#8a1d1d; }}
  [role="tablist"] {{ display:flex; gap:6px; flex-wrap:wrap; }}
  [role="tab"] {{
    appearance:none; border:0; cursor:pointer; font:inherit; font-size:15.5px; font-weight:650; color:#d7e0ee;
    background:rgba(255,255,255,.08); padding:12px 16px; border-radius:10px 10px 0 0; display:inline-flex; align-items:center; gap:10px; min-height:48px;
  }}
  [role="tab"]:hover {{ background:rgba(255,255,255,.16); color:#fff; }}
  [role="tab"][aria-selected="true"] {{ background:var(--bg); color:var(--navy); }}
  .tab-id {{ font-family:ui-monospace,Consolas,monospace; }}
  .tab-status {{ font-size:13px; font-weight:700; padding:2px 9px; border-radius:999px; background:#eef1f5; color:#3d4a5c; }}
  .tab-status.resolved {{ background:#1d6b4f; color:#fff; }} .tab-status.in_progress {{ background:#e6effb; color:#1f4f9a; }}
  .tab-status.awaiting_approval {{ background:#ffe9a8; color:#4d3700; }} .tab-status.blocked {{ background:#fdecec; color:#8a1d1d; }}
  main {{ max-width:1200px; margin:0 auto; padding:22px 28px 56px; }}
  .panel {{ display:grid; gap:22px; }}
  .panel[hidden] {{ display:none; }}
  .panel-title {{ margin:0; font-size:24px; }}
  section > h3 {{ margin:0 0 10px; font-size:14px; text-transform:uppercase; letter-spacing:.9px; color:var(--muted); }}
  .outcome {{ background:var(--surface); border:1px solid var(--line); border-left:6px solid #1f5fa8; border-radius:12px; padding:16px 20px; }}
  .outcome.resolved {{ border-left-color:#1d6b4f; }} .outcome.awaiting_approval {{ border-left-color:#b78a00; }} .outcome.blocked {{ border-left-color:#a02323; }}
  .outcome h3 {{ margin:0 0 6px; font-size:15px; text-transform:uppercase; letter-spacing:.8px; color:var(--ink); }}
  .outcome-text {{ margin:0; font-size:18px; font-weight:600; }}
  .facts {{ margin:14px 0 0; display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:10px 22px; }}
  .facts div {{ display:grid; }} .facts dt {{ font-size:13px; font-weight:700; color:var(--muted); text-transform:uppercase; letter-spacing:.5px; }}
  .facts dd {{ margin:0; }}
  .shot {{ margin:0; background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:10px; }}
  .shot img {{ display:block; width:100%; height:auto; border-radius:8px; }}
  .shot figcaption {{ margin-top:8px; font-size:14px; color:var(--muted); }}
  .steps {{ list-style:none; margin:0; padding:0; background:var(--surface); border:1px solid var(--line); border-radius:12px; }}
  .step {{ display:grid; grid-template-columns:36px minmax(0,1fr) auto; gap:12px; align-items:start; padding:12px 16px; border-bottom:1px solid var(--line); }}
  .step:last-child {{ border-bottom:0; }}
  .step-icon {{ width:30px; height:30px; border-radius:50%; display:grid; place-items:center; color:#fff; font-weight:800; background:var(--c, var(--desk)); }}
  .step-text {{ margin:0; font-weight:600; }}
  .step-detail {{ margin:4px 0 0; font-size:15px; }}
  .step details {{ margin-top:4px; }} .step summary {{ cursor:pointer; color:#1f4f9a; font-size:14.5px; min-height:24px; }}
  .step details p {{ margin:6px 0 0; font-size:15px; background:#f7f8fa; border-radius:8px; padding:8px 10px; }}
  .step time {{ font-family:ui-monospace,Consolas,monospace; font-size:13px; color:var(--muted); white-space:nowrap; }}
  .k-run {{ background:#f7f8fa; }} .k-approval {{ background:#f2f7ff; }} .k-draft {{ background:#fffaf0; }} .k-refused {{ background:#fff5f5; }}
  .a-boss {{ --c:var(--boss); }} .a-inventory {{ --c:var(--inventory); }} .a-accounting {{ --c:var(--accounting); }}
  .a-facilities {{ --c:var(--facilities); }} .a-customer_service {{ --c:var(--customer_service); }} .a-human {{ --c:var(--human); }} .a-desk {{ --c:var(--desk); }}
  .k-refused .step-icon {{ background:#a02323; }}
  .two {{ display:grid; grid-template-columns:1.2fr 1fr; gap:22px; align-items:start; }}
  @media (max-width:900px) {{ .two {{ grid-template-columns:1fr; }} }}
  .table-wrap {{ overflow-x:auto; background:var(--surface); border:1px solid var(--line); border-radius:12px; }}
  table {{ width:100%; border-collapse:collapse; font-size:15px; }}
  th, td {{ text-align:left; padding:10px 12px; border-bottom:1px solid var(--line); vertical-align:top; }}
  th {{ font-size:13px; color:var(--muted); }} tbody tr:last-child td {{ border-bottom:0; }}
  .num {{ text-align:right; font-family:ui-monospace,Consolas,monospace; white-space:nowrap; }}
  .letter {{ background:var(--surface); border:1px solid var(--line); border-left:5px solid var(--customer_service); border-radius:12px; padding:14px 18px; }}
  .letter .meta {{ margin:0; font-size:15px; }} .letter .meta span {{ color:var(--muted); }}
  .letter .body {{ margin:10px 0 0; white-space:pre-wrap; }}
  .agents {{ list-style:none; margin:0; padding:0; display:grid; gap:12px; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); }}
  .agent-card {{ background:var(--surface); border:1px solid var(--line); border-top:5px solid var(--c); border-radius:12px; padding:12px 14px; }}
  .agent-card h4 {{ margin:0; color:var(--c); font-size:17px; }}
  .agent-card p {{ margin:6px 0 0; font-size:15px; }}
  .agent-card summary {{ cursor:pointer; color:#1f4f9a; font-size:14px; margin-top:6px; }}
  .run {{ font-size:12px; font-weight:700; background:#eef1f5; border-radius:999px; padding:1px 8px; margin-right:4px; }}
  .note {{ font-size:12.5px; font-weight:600; color:#6b4a00; background:#fff4dd; border-radius:6px; padding:1px 7px; }}
  .drafted {{ font-weight:600; }}
  tr.not-paid td {{ background:#fffaf0; }}
  .tools {{ font-family:ui-monospace,Consolas,monospace; font-size:13px !important; }}
  @media (prefers-reduced-motion: reduce) {{ * {{ transition:none !important; animation:none !important; }} }}
  @media print {{ header.top [role="tablist"], .skip {{ display:none; }} .panel[hidden] {{ display:grid !important; }} .panel {{ break-after:page; }} }}
</style>
</head>
<body>
<a class="skip" href="#main">Skip to the ticket details</a>
<header class="top">
  <h1>Campus Customs · Resolved Board</h1>
  <p>What the five-agent team did on each ticket after the database reset ({esc(data["reset_at"][:16].replace("T", " "))} UTC; shop date {esc(data["desk_date"])}). Pick a ticket tab to see its outcome, the dashboard screenshot, every step in order, the money the human operator approved, and the customer email.</p>
  <div class="summary">
    <span>Checking: start <strong>{money(c["starting_balance"])}</strong> · approved payments <strong>−{money(c["total_approved_payments"])}</strong> · end <strong>{money(c["ending_balance_cash_accounts"])}</strong></span>
    {match}
  </div>
  <div role="tablist" aria-label="Tickets">{tabs}</div>
</header>
<main id="main" tabindex="-1">
{panels}
</main>
<script>
  // Accessible tabs: click, Left/Right arrows, Home/End; the URL hash (#t101) opens a ticket directly.
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  const panels = tabs.map((t) => document.getElementById(t.getAttribute('aria-controls')));
  function select(i, focus) {{
    tabs.forEach((t, j) => {{
      const on = i === j;
      t.setAttribute('aria-selected', on);
      t.tabIndex = on ? 0 : -1;
      panels[j].hidden = !on;
    }});
    if (focus) tabs[i].focus();
    history.replaceState(null, '', '#t' + tabs[i].id.replace('tab-', ''));
  }}
  tabs.forEach((t, i) => {{
    t.addEventListener('click', () => select(i, false));
    t.addEventListener('keydown', (e) => {{
      const keys = {{ ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }};
      if (!(e.key in keys)) return;
      e.preventDefault();
      select((keys[e.key] + tabs.length) % tabs.length, true);
    }});
  }});
  const fromHash = tabs.findIndex((t) => '#t' + t.id.replace('tab-', '') === location.hash);
  select(fromHash >= 0 ? fromHash : 0, false);
</script>
</body>
</html>
'''


if __name__ == "__main__":
    data = build()
    (OUT / "resolved_tickets.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "resolved_board.html").write_text(board_html(data), encoding="utf-8")
    print({t["id"]: (t["final_status"], len(t["timeline"]), len(t["human_approvals"]), t["money_spent"]) for t in data["tickets"]},
          "cash match:", data["cash"]["matches"])
