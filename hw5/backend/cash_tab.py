"""Build the Cash tab of output/desk_tickets.html from the audit trail + the live cash balance.

- Starting balance: the checking balance the last database reset restored (db_reset event).
- Every payment a human approved since then, which ticket it was for, and why it was spent.
- Ending balance: read from cash_accounts through the MCP server (check_cash), never by
  opening the database directly, and compared with starting balance minus the payments.
"""

from __future__ import annotations

import asyncio
import html
from datetime import datetime
from typing import Any

WHY = {
    "invoice": "Overdue vendor invoice. The vendor won't ship new stock until it's paid.",
    "rent": "Monthly rent for the shop, at the amount on the lease (not the ticket text).",
    "purchase": "Restock order for stock the ticket needed, sized so cash stays at or above $0.",
}
KIND = {"invoice": "Invoice payment", "rent": "Rent payment", "purchase": "Restock purchase"}


def esc(v: Any) -> str:
    return html.escape(str(v), quote=True)


def money(n: Any) -> str:
    return f"${float(n):,.2f}"


async def _check_cash_async() -> dict[str, Any]:
    from config import build_mcp_client

    async with build_mcp_client() as client:
        return (await client.call_tool("check_cash", {})).structured_content


def fetch_cash() -> dict[str, Any] | None:
    """check_cash through MCP from a plain (non-async) caller, e.g. the CLI."""
    try:
        return asyncio.run(_check_cash_async())
    except Exception:
        return None


def payments_since_reset(events: list[dict], ticket_of_draft) -> tuple[dict | None, list[dict]]:
    resets = [e for e in events if e.get("event") == "db_reset"]
    reset = resets[-1] if resets else None
    since = reset["seq"] if reset else 0
    rows = []
    for e in events:
        if e.get("event") != "payment_approved" or e["seq"] <= since:
            continue
        r = e.get("result") or {}
        tid, desc = ticket_of_draft(r)
        rows.append({
            "seq": e["seq"], "ts": e.get("ts", ""), "ticket": tid, "kind": r.get("kind"), "payee": r.get("payee"),
            "amount": float(r.get("amount", 0)), "before": r.get("balance_before"), "after": r.get("balance_after"),
            "approved_by": e.get("approved_by"), "desc": desc, "updated": r.get("updated") or {},
        })
    return reset, rows


def cash_section(events: list[dict], cash: dict | None, subjects: dict[int, str]) -> str:
    # map an approved payment back to the ticket whose run drafted it (and its description)
    run_ticket = {e["run_id"]: e.get("ticket_id") for e in events if e.get("event") == "run_started"}
    drafts = [(run_ticket.get(e["run_id"]), e.get("draft") or {}) for e in events if e.get("event") == "payment_drafted"]

    def ticket_of_draft(r: dict) -> tuple[int | None, str]:
        sku = None
        if r.get("kind") == "purchase":
            sku = ((r.get("updated") or {}).get("ordered") or "").split(" x ")[-1].split(" ")[0] or None
        for tid, d in reversed(drafts):
            if d.get("kind") == r.get("kind") and (
                (r.get("kind") == "purchase" and d.get("sku") == sku and float(d.get("amount", 0)) == float(r.get("amount", 0)))
                or (r.get("kind") != "purchase" and d.get("ref_id") == r.get("ref_id"))
            ):
                return tid, d.get("description") or ""
        return None, ""

    reset, rows = payments_since_reset(events, ticket_of_draft)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    if reset is None:
        return '<div class="placeholder"><h2>Cash</h2><p>No database reset recorded yet.</p></div>'
    start = next((a["balance"] for a in reset["result"]["cash_accounts"] if a["name"] == "checking"), None)
    spent = round(sum(r["amount"] for r in rows), 2)
    expected_end = round(start - spent, 2)
    db_end = None
    if cash:
        db_end = next((a["balance"] for a in cash.get("cash_accounts", []) if a["name"] == "checking"), None)

    if db_end is None:
        match = '<p class="cash-note warn">⚠ Couldn\'t read cash_accounts through the MCP server, so the match wasn\'t checked.</p>'
    elif round(db_end, 2) == expected_end:
        match = (
            f'<p class="cash-note ok">✓ <strong>Ending balance matches.</strong> cash_accounts (checking) in '
            f'data/campus_customs_new.db shows {money(db_end)}, exactly the starting {money(start)} minus '
            f'{money(spent)} in approved payments.</p>'
        )
    else:
        match = (
            f'<p class="cash-note bad">✗ <strong>Mismatch.</strong> cash_accounts shows {money(db_end)} but '
            f'{money(start)} − {money(spent)} = {money(expected_end)} (off by {money(db_end - expected_end)}).</p>'
        )

    # per-payment rows
    body = []
    for i, r in enumerate(rows, 1):
        t = f'#{r["ticket"]} · {esc(subjects.get(r["ticket"], ""))}' if r["ticket"] else "—"
        what = esc(r["desc"] or KIND.get(r["kind"], r["kind"]))
        extra = ""
        if r["kind"] == "purchase" and r["updated"].get("expected_arrival"):
            extra = f' Arrives about {esc(r["updated"]["expected_arrival"])}.'
        body.append(
            f'<tr><td>{i}</td><td>{t}</td><td>{esc(KIND.get(r["kind"], r["kind"]))}</td><td>{esc(r["payee"])}</td>'
            f'<td><strong>{what}</strong><br><span class="why">{esc(WHY.get(r["kind"], ""))}{extra}</span></td>'
            f'<td>{esc(r["approved_by"])}</td><td class="num neg">−{money(r["amount"])}</td><td class="num">{money(r["after"])}</td></tr>'
        )
    table = (
        '<table class="cash-table"><thead><tr><th>#</th><th>Ticket</th><th>Type</th><th>Paid to</th>'
        '<th>What it was for, and why</th><th>Approved by</th><th class="num">Amount</th><th class="num">Balance after</th></tr></thead>'
        f'<tbody><tr class="start-row"><td></td><td colspan="5">Starting balance after the reset ({esc(reset["ts"][:16].replace("T", " "))} UTC)</td>'
        f'<td></td><td class="num">{money(start)}</td></tr>{"".join(body)}'
        f'<tr class="end-row"><td></td><td colspan="5">Ending balance (start − approved payments)</td><td class="num neg">−{money(spent)}</td>'
        f'<td class="num">{money(expected_end)}</td></tr></tbody></table>'
        if rows else '<p class="step-note">No payments approved since the reset.</p>'
    )

    # per-ticket subtotals
    per = []
    for tid in (101, 102, 103):
        mine = [r for r in rows if r["ticket"] == tid]
        total = sum(r["amount"] for r in mine)
        items = "; ".join(f'{KIND.get(r["kind"], r["kind"]).lower()} {money(r["amount"])} to {esc(r["payee"])}' for r in mine) or "no money spent"
        per.append(f'<tr><td>#{tid} · {esc(subjects.get(tid, ""))}</td><td>{items}</td><td class="num neg">{"−" + money(total) if total else money(0)}</td></tr>')
    per_table = (
        '<table class="cash-table per-ticket"><thead><tr><th>Ticket</th><th>Deductions</th><th class="num">Total</th></tr></thead>'
        f'<tbody>{"".join(per)}</tbody></table>'
    )

    end_card = money(db_end) if db_end is not None else "—"
    return f'''<div class="cash-wrap">
      <div class="cash-head"><h2>Cash</h2><span class="hint">From the audit trail and cash_accounts (via MCP check_cash) · updated {stamp}</span></div>
      <div class="cash-cards">
        <div class="cash-card"><p class="label">Starting balance after reset</p><p class="big">{money(start)}</p></div>
        <div class="cash-card"><p class="label">Spent (human-approved)</p><p class="big neg">−{money(spent)}</p><p class="label">{len(rows)} payment{"s" if len(rows) != 1 else ""}</p></div>
        <div class="cash-card"><p class="label">Ending balance in cash_accounts</p><p class="big">{end_card}</p></div>
      </div>
      {match}
      <h3 class="cash-h3">Every payment, in order</h3>
      {table}
      <h3 class="cash-h3">Per ticket</h3>
      {per_table}
    </div>'''


CASH_CSS = """
<style id="cash-styles">
  .cash-wrap { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 20px 22px; display: grid; gap: 14px; }
  .cash-head { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
  .cash-head h2 { margin: 0; font-size: 19px; }
  .cash-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
  .cash-card { border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; }
  .cash-card .label { margin: 0; font-size: 12px; text-transform: uppercase; letter-spacing: .4px; color: var(--muted); }
  .cash-card .big { margin: 4px 0 0; font: 700 26px/1.2 ui-monospace, Consolas, monospace; }
  .neg { color: #a02323; }
  .cash-note { margin: 0; padding: 10px 14px; border-radius: 8px; font-size: 14px; }
  .cash-note.ok { background: #e3f4ea; color: #145a40; border: 1px solid #b7e0c7; }
  .cash-note.bad { background: #fdecec; color: #8a1d1d; border: 1px solid #f2c2c2; }
  .cash-note.warn { background: #fff4dd; color: #6b4a00; border: 1px solid #f0dca6; }
  .cash-h3 { margin: 6px 0 0; font-size: 12px; text-transform: uppercase; letter-spacing: .5px; color: var(--muted); }
  .cash-table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
  .cash-table th, .cash-table td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
  .cash-table th { font-size: 12px; color: var(--muted); font-weight: 650; }
  .cash-table .num { text-align: right; font-family: ui-monospace, Consolas, monospace; white-space: nowrap; }
  .cash-table .why { color: var(--muted); font-size: 12.5px; }
  .cash-table .start-row td, .cash-table .end-row td { font-weight: 700; background: #f7f8fa; }
</style>
"""
