"""Campus Customs API: FastAPI routes the dashboard uses to reach the agents and the database.

Run from Homework 5/backend:
  C:\\venvs\\hw5\\Scripts\\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000

Routes:
  GET  /api/tickets                       the three tickets and whether each is open or resolved
  POST /api/tickets/{ticket_id}/run       run the agent team on one ticket (background; 202)
  GET  /api/events?since=&limit=&run_id=  recent audit-trail events: agent messages, tool calls, drafts
  GET  /api/payments?status=              the human approval queue (payments agents drafted)
  POST /api/payments/{request_id}/approve the ONLY place money moves: runs MCP `pay` for a human
                                          (invoice, rent, or restock purchase); after a ticket's
                                          last approval the team re-runs on it automatically
  GET  /api/cash                          current checking balance from cash_accounts
  POST /api/reset                         copy data/campus_customs.db over campus_customs_new.db
  GET  /api/health                        model, key, and MCP status

Every database read and write goes through the campus-customs MCP server: these routes call
its tools (list_tickets, check_cash, pay, reset_db) and never open the database themselves.
"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastmcp.exceptions import ToolError

from audit import append, read_entries
from fill_desk_actual import fill as fill_desk_page
from config import MODEL_NAME, PROJECT_ROOT, build_mcp_client
from models import (
    AGENTS,
    ApproveRequest,
    CashBalance,
    EventsResponse,
    PaymentRequest,
    ResetResponse,
    RunStarted,
    RunState,
    TicketsResponse,
    TicketSummary,
)
from payments import PaymentQueue
from team import customer_reply_gate, run_team

OUTPUT_DIR = PROJECT_ROOT / "output"


async def backfill_restock_orders(app: FastAPI) -> None:
    """Give purchases paid before orders were recorded an order record (idempotent)."""
    for r in app.state.queue.list("paid"):
        if r.kind != "purchase" or not r.payment or (r.payment.get("updated") or {}).get("table") == "invoices":
            continue
        try:
            res = await app.state.mcp.call_tool(
                "record_restock_order",
                {"payment_id": r.payment["payment_id"], "sku": r.sku, "size": r.size, "qty": r.qty},
            )
            if res.structured_content.get("status") == "recorded":
                append("api", "runner", "restock_order_backfilled", request_id=r.id, result=res.structured_content)
        except Exception as exc:
            append("api", "runner", "restock_order_backfill_error", request_id=r.id, error=str(exc))


async def refresh_desk_page(app: FastAPI) -> None:
    """Re-fill output/desk_tickets.html: Actual sections + Cash tab (never breaks a request).
    The ending balance comes from cash_accounts through MCP check_cash."""
    try:
        cash = (await app.state.mcp.call_tool("check_cash", {})).structured_content
        fill_desk_page(cash=cash)
    except Exception as exc:  # the page is a report; a failure here must not affect the shop
        append("api", "runner", "desk_page_error", error=f"{type(exc).__name__}: {exc}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.mcp = build_mcp_client()
    app.state.queue = PaymentQueue()
    app.state.run = None  # RunState of the latest ticket run
    app.state.task = None  # its asyncio.Task while running
    app.state.reruns = []  # (ticket_id, note) automatic re-runs waiting for the current run to end
    async with app.state.mcp:
        await backfill_restock_orders(app)
        yield
        if app.state.task and not app.state.task.done():
            app.state.task.cancel()


app = FastAPI(title="Campus Customs API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)


async def mcp_call(request: Request, tool: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call one campus-customs MCP tool. A refusal from the server becomes ToolError."""
    result = await request.app.state.mcp.call_tool(tool, args or {})
    return result.structured_content or result.data


def active_run(request: Request) -> RunState | None:
    run: RunState | None = request.app.state.run
    return run if run and run.status == "running" else None


# ---------------------------------------------------------------- 1. tickets


@app.get("/api/tickets", response_model=TicketsResponse)
async def get_tickets(request: Request):
    """All tickets with their status. `resolved` is true only when the ticket's status is 'resolved'."""
    data = await mcp_call(request, "list_tickets", {"status": None})
    tickets = [TicketSummary(**t, resolved=t["status"] == "resolved") for t in data["tickets"]]
    return TicketsResponse(today=data["today"], tickets=tickets, active_run=active_run(request))


# ---------------------------------------------------------------- 2. run the team on one ticket


def emailed_since_reset(ticket_id: int) -> bool:
    """Whether Customer Service has drafted this ticket's customer email since the last reset."""
    entries = read_entries(limit=100_000)[0]
    since = max((e["seq"] for e in entries if e.get("event") == "db_reset"), default=0)
    return any(
        e["seq"] > since and e.get("event") == "agent_output" and e.get("agent") == "customer_service"
        and any(d.get("ticket_id") == ticket_id for d in e.get("drafts") or [])
        for e in entries
    )


def prior_context(ticket_id: int) -> tuple[list[dict[str, Any]], str | None]:
    """What the previous run on this ticket (since the last reset) found and decided, plus the
    human approvals since then, so a re-run continues from there instead of starting over.

    Returns (board posts to pre-load, a short "where we left off" summary)."""
    entries = read_entries(limit=100_000)[0]
    since = max((e["seq"] for e in entries if e.get("event") == "db_reset"), default=0)
    starts = [e for e in entries if e.get("event") == "run_started" and e.get("ticket_id") == ticket_id and e["seq"] > since]
    if not starts:
        return [], None
    prev = starts[-1]
    evs = [e for e in entries if e.get("run_id") == prev["run_id"]]
    skip = {"ts", "run_id", "event", "seq", "tokens_used_run", "agent", "output"}
    board = [
        {
            "author": e["agent"],
            "requested_by": "previous run",
            "output": e["output"] if isinstance(e.get("output"), dict) else {k: v for k, v in e.items() if k not in skip},
        }
        for e in evs
        if e.get("event") == "agent_output"
    ]
    lines = []
    updates = [e.get("args") or {} for e in evs if e.get("event") == "tool_call" and e.get("tool") == "update_ticket"]
    if updates:
        lines.append(f"The Boss recorded the ticket as '{updates[-1].get('status')}': {updates[-1].get('note')}")
    for e in evs:
        if e.get("event") == "payment_drafted":
            d = e.get("draft") or {}
            lines.append(f"Accounting drafted a {d.get('kind')} of {d.get('amount')} to {d.get('payee')} ({d.get('description')}).")
    for e in entries:
        if e.get("event") == "payment_approved" and e["seq"] > prev["seq"]:
            r = e.get("result") or {}
            ordered = (r.get("updated") or {}).get("ordered")
            lines.append(
                f"Since then a human ({e.get('approved_by')}) APPROVED and paid {r.get('kind')} {r.get('amount')} "
                f"to {r.get('payee')}" + (f" (restock order {ordered}, expected {(r.get('updated') or {}).get('expected_arrival')})" if ordered else "") + "."
            )
    return board[-8:], " ".join(lines) or None


EMAIL_AWAITING = "email sent to customer — awaiting response"


def make_finalizer(app: FastAPI, ticket_id: int):
    """After a ticket run: mark the ticket resolved, unless a sign-off request is still waiting.

    If Customer Service drafted the customer reply in this run, the note reads
    "Resolved — email sent to customer — awaiting response" (the email stays a draft; nothing
    is actually sent). A waiting sign-off keeps the ticket open so the automatic re-run after
    the human's approval can still happen. A customer ticket also stays open while money or
    stock work remains (customer_reply_gate) or before its one customer email is written.
    """

    async def finalize(session) -> None:
        waiting = [r.id for r in app.state.queue.list("awaiting_human_approval") if r.ticket_id == ticket_id]
        if waiting:
            session.log("runner", "ticket_not_finalized", ticket_id=ticket_id, pending_request_ids=waiting,
                        reason="sign-off request(s) still waiting; the ticket resolves on the run after approval")
            return
        if session.drafts:
            # This run created money work (even if the human already approved it mid-run): the
            # follow-up run (next step, customer email) must still happen, so don't resolve yet.
            session.log("runner", "ticket_not_finalized", ticket_id=ticket_id,
                        reason=f"this run drafted {len(session.drafts)} payment(s)/purchase(s); "
                               "the ticket resolves on the follow-up run that drafts nothing new")
            return
        if any(t == ticket_id for t, _ in app.state.reruns):
            session.log("runner", "ticket_not_finalized", ticket_id=ticket_id,
                        reason="an automatic re-run is queued for this ticket")
            return
        if todo := await customer_reply_gate(session):
            # Same database check that holds back the customer email: money or stock work remains.
            session.log("runner", "ticket_not_finalized", ticket_id=ticket_id, reason=todo)
            return
        tickets = (await app.state.mcp.call_tool("list_tickets", {"status": None})).structured_content["tickets"]
        current = next((t for t in tickets if t["id"] == ticket_id), None)
        emails = session.customer_drafts
        if current is not None and current.get("sku") and not emails and not emailed_since_reset(ticket_id):
            session.log("runner", "ticket_not_finalized", ticket_id=ticket_id,
                        reason="the customer hasn't had their one email yet; the Boss asks Customer Service "
                               "for it at the end, then the ticket resolves")
            return
        if current is None or (current["status"] == "resolved" and not emails):
            return  # already resolved and nothing new to add
        run_events = read_entries(limit=100_000, run_id=session.run_id)[0]
        boss_notes = [(e.get("args") or {}).get("note") for e in run_events
                      if e.get("event") == "tool_call" and e.get("tool") == "update_ticket" and e.get("agent") == "boss"]
        boss_note = f" Boss: {boss_notes[-1]}" if boss_notes and boss_notes[-1] else ""
        if emails:
            d = emails[-1]
            note = (f"Resolved — {EMAIL_AWAITING}. Customer Service drafted the reply to {d.get('to')} "
                    f"(\"{d.get('subject')}\"); it stays a draft on the board and is never actually emailed.{boss_note}")
        else:
            note = f"Resolved — the run finished and nothing is waiting on a human.{boss_note}"
        args = {"ticket_id": ticket_id, "status": "resolved", "note": note, "updated_by": "desk"}
        try:
            result = (await app.state.mcp.call_tool("update_ticket", args)).structured_content
        except ToolError as exc:  # e.g. the linked invoice is still open
            session.log("runner", "ticket_not_finalized", ticket_id=ticket_id, reason=str(exc))
            return
        session.log("runner", "tool_call", tool="update_ticket", args=args, result=result)

    return finalize


def start_run(app: FastAPI, ticket_id: int, *, note: str | None = None, trigger: str = "human") -> RunState:
    """Start the agent team on one ticket in the background (callers check it's allowed).

    `note` tells the Boss why it's running again (e.g. a payment a human just approved).
    When the run ends, the next queued automatic re-run (if any) starts.
    """
    state = app.state
    run = RunState(run_id=os.urandom(6).hex(), ticket_id=ticket_id, started_at=_now())
    state.run = run
    queue: PaymentQueue = state.queue

    def on_draft(draft: dict[str, Any], agent: str, run_id: str) -> str:
        req, created = queue.add_draft(draft, agent, run_id, ticket_id=ticket_id)
        if created:
            run.payment_requests.append(req.id)
            return f"queued for human approval as payment request #{req.id}"
        return f"already awaiting human approval as payment request #{req.id}"

    task = (
        f"Handle ticket {ticket_id} only. Read it with list_tickets, delegate to the right "
        f"specialists, make the final call on ticket {ticket_id}, and record it with update_ticket. "
        "Agents only draft payments and purchases (draft_payment, draft_purchase); a human approves "
        "them in the dashboard, so anything drafted is still pending when you finish."
    )
    prior_board, where = prior_context(ticket_id)
    if where:
        task += (
            f" CONTINUE from the previous run on this ticket; don't start over. Where it left off: {where}"
            " The previous run's specialist reports are on the board (read_board): reuse them and don't ask "
            "specialists for information they already gave. Confirm only what changed with one quick check "
            "(for example check_vendor or check_stock to see that the approved payment cleared), then delegate "
            "just the NEXT step. After the invoice is paid, Accounting drafts the restock purchase. After the "
            "restock is paid, Customer Service writes the one customer reply. Resolve the ticket if every "
            "constraint is now met."
        )
    elif note:
        task += f" Why you're running again: {note}"

    async def work() -> None:
        try:
            output, session = await run_team(
                task,
                on_draft=on_draft,
                run_id=run.run_id,
                board=prior_board,
                extra={"ticket_id": ticket_id, "trigger": trigger, "continues_previous_run": bool(where)},
                finalize=make_finalizer(app, ticket_id),
            )
            run.decision = output.model_dump(mode="json")
            run.tokens_used = session.tokens_used
            run.status = "done"
            (OUTPUT_DIR / f"run_ticket_{ticket_id}.json").write_text(
                json.dumps(
                    {
                        **run.model_dump(mode="json"),
                        "model": MODEL_NAME,
                        "delegations": [d.model_dump(mode="json") for d in session.delegations],
                        "board": session.board,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as exc:
            run.status, run.error = "error", f"{type(exc).__name__}: {exc}"
        finally:
            run.finished_at = _now()
            await refresh_desk_page(app)
            await start_next_rerun(app)

    state.task = asyncio.create_task(work())
    return run


async def ticket_status(app: FastAPI, ticket_id: int) -> str | None:
    tickets = (await app.state.mcp.call_tool("list_tickets", {"status": None})).structured_content["tickets"]
    return next((t["status"] for t in tickets if t["id"] == ticket_id), None)


async def start_next_rerun(app: FastAPI) -> None:
    """Start the oldest queued automatic re-run whose ticket still isn't resolved."""
    while app.state.reruns:
        ticket_id, note = app.state.reruns.pop(0)
        if await ticket_status(app, ticket_id) not in (None, "resolved"):
            run = start_run(app, ticket_id, note=note, trigger="auto_after_approval")
            append("api", "runner", "auto_rerun_started", ticket_id=ticket_id, new_run_id=run.run_id, note=note)
            return


@app.post("/api/tickets/{ticket_id}/run", response_model=RunStarted, status_code=202)
async def run_ticket(ticket_id: int, request: Request):
    """Start the agent team on one ticket. Runs in the background; follow it with /api/events."""
    state = request.app.state
    if active_run(request):
        raise HTTPException(409, f"Run {state.run.run_id} on ticket {state.run.ticket_id} is still going.")
    status = await ticket_status(request.app, ticket_id)
    if status is None:
        raise HTTPException(404, f"No ticket {ticket_id}.")
    if status == "resolved":
        raise HTTPException(409, f"Ticket {ticket_id} is already resolved.")
    run = start_run(request.app, ticket_id)
    return RunStarted(
        run_id=run.run_id,
        ticket_id=ticket_id,
        message=f"Agent team started on ticket {ticket_id}. Poll /api/events?run_id={run.run_id}.",
    )


# ---------------------------------------------------------------- 3. events


@app.get("/api/events", response_model=EventsResponse)
async def get_events(
    request: Request,
    since: int = Query(0, ge=0, description="Only events with seq greater than this."),
    limit: int = Query(100, ge=1, le=1000),
    run_id: str | None = Query(None, description="Only events from one run."),
):
    """Recent steps from output/audit_trail.json: what agents were asked and said, tools they used."""
    events, last_seq = read_entries(since=since, limit=limit, run_id=run_id)
    return EventsResponse(
        events=events, last_seq=last_seq, active_run=active_run(request), last_run=request.app.state.run
    )


# ---------------------------------------------------------------- 4. payment approvals


@app.get("/api/payments", response_model=list[PaymentRequest])
async def list_payments(request: Request, status: str | None = Query(None)):
    """The approval queue. Agents put drafts here; only a human approval pays them.

    Pending purchases get a live `blocked_reason` when their vendor still has an open
    unpaid invoice (checked now through MCP check_vendor), so the human knows what to
    approve first.
    """
    items = request.app.state.queue.list(status)
    vendors_needed = {r.ref_id for r in items if r.kind == "purchase" and r.status == "awaiting_human_approval"}
    open_by_vendor: dict[int, tuple[str, list[int]]] = {}
    for vendor_id in vendors_needed:
        v = (await mcp_call(request, "check_vendor", {"vendor_id": vendor_id}))["vendors"][0]
        open_by_vendor[vendor_id] = (v["name"], [i["id"] for i in v["open_invoices"]])
    shown = []
    for r in items:
        name, open_ids = open_by_vendor.get(r.ref_id, ("", [])) if r.kind == "purchase" else ("", [])
        reason = None
        if r.status == "awaiting_human_approval" and open_ids:
            reason = f"{name} won't ship until invoice {', '.join(map(str, open_ids))} is paid. Approve that first."
        shown.append(r.model_copy(update={"blocked_reason": reason}))
    return shown


@app.post("/api/payments/{request_id}/approve", response_model=PaymentRequest)
async def approve_payment(request_id: int, body: ApproveRequest, request: Request):
    """A human approves one drafted payment or purchase. This is the only route that moves money.

    Calls the MCP `pay` tool, which in one transaction adds a `payments` row, lowers the
    `cash_accounts` balance, and marks the invoice paid or moves the lease's next_due (a
    purchase records the order; stock arrives after the vendor's lead time). The server
    re-checks the amount, the bill, and the balance, refuses an overdraft, and refuses a
    purchase from a vendor that still has an open unpaid invoice.
    """
    queue: PaymentQueue = request.app.state.queue
    req = queue.get(request_id)
    if req is None:
        raise HTTPException(404, f"No payment request {request_id}.")
    if req.status != "awaiting_human_approval":
        raise HTTPException(409, f"Payment request {request_id} is already {req.status}.")

    approver = body.approved_by.strip()
    agent_names = {a.lower() for a in AGENTS} | {v["name"].lower() for v in AGENTS.values()}
    if not approver or approver.lower() in agent_names or "agent" in approver.lower():
        raise HTTPException(400, "approved_by must be the name of the human approving, not an agent.")
    args = {"kind": req.kind, "ref_id": req.ref_id, "amount": req.amount, "account": req.account, "approved_by": approver}
    if req.kind == "purchase":
        args.update(sku=req.sku, size=req.size, qty=req.qty)
    try:
        result = await mcp_call(request, "pay", args)
    except ToolError as exc:
        if str(exc).startswith("Blocked:"):  # temporary (vendor invoice still open): stays pending
            append("api", "human", "payment_blocked", request_id=request_id, args=args, approved_by=approver, error=str(exc))
            raise HTTPException(409, str(exc)) from exc
        queue.mark_refused(request_id, str(exc))
        append("api", "human", "payment_refused", request_id=request_id, args=args, approved_by=approver, error=str(exc))
        raise HTTPException(409, str(exc)) from exc

    paid = queue.mark_paid(request_id, approver, result)
    append("api", "human", "payment_approved", request_id=request_id, approved_by=approver, result=result)
    await refresh_desk_page(request.app)
    return paid.model_copy(update={"auto_rerun": await schedule_rerun(request, paid)})


async def schedule_rerun(request: Request, paid: PaymentRequest) -> dict[str, Any] | None:
    """After the last pending approval for a ticket, re-run the team on it automatically.

    Starts right away if the team is free, otherwise queues it behind the current run.
    Waits while other sign-off requests for the same ticket are still pending.
    """
    run_tickets = {
        e["run_id"]: e["ticket_id"] for e in read_entries(limit=100_000)[0] if e.get("event") == "run_started" and "ticket_id" in e
    }

    def ticket_of(r: PaymentRequest) -> int | None:  # older requests have no ticket_id: use their run
        return r.ticket_id if r.ticket_id is not None else run_tickets.get(r.run_id)

    ticket_id = ticket_of(paid)
    if ticket_id is None:
        return None
    waiting = [r.id for r in request.app.state.queue.list("awaiting_human_approval") if ticket_of(r) == ticket_id]
    if waiting:
        return {"status": "waiting_for_other_approvals", "ticket_id": ticket_id, "pending_request_ids": waiting}
    if await ticket_status(request.app, ticket_id) in (None, "resolved"):
        return None
    note = (
        f"A human ({paid.approved_by}) just approved and paid {paid.kind} request #{paid.id}: "
        f"{paid.amount:.2f} to {paid.payee} ({paid.description})."
    )
    if active_run(request):
        if all(t != ticket_id for t, _ in request.app.state.reruns):
            request.app.state.reruns.append((ticket_id, note))
        append("api", "runner", "auto_rerun_queued", ticket_id=ticket_id, note=note)
        return {"status": "queued", "ticket_id": ticket_id}
    run = start_run(request.app, ticket_id, note=note, trigger="auto_after_approval")
    append("api", "runner", "auto_rerun_started", ticket_id=ticket_id, new_run_id=run.run_id, note=note)
    return {"status": "started", "ticket_id": ticket_id, "run_id": run.run_id}


# ---------------------------------------------------------------- 5. cash


@app.get("/api/cash", response_model=CashBalance)
async def get_cash(request: Request):
    """The checking account balance from cash_accounts, plus what's waiting for approval."""
    data = await mcp_call(request, "check_cash")
    checking = next((a for a in data["cash_accounts"] if a["name"] == "checking"), None)
    if checking is None:
        raise HTTPException(404, "No 'checking' account in cash_accounts.")
    return CashBalance(
        today=data["today"],
        account="checking",
        balance=checking["balance"],
        as_of=checking["date"],
        pending_approvals=request.app.state.queue.pending_total(),
    )


# ---------------------------------------------------------------- 6. reset


@app.post("/api/reset", response_model=ResetResponse)
async def reset(request: Request):
    """Copy the clean data/campus_customs.db over data/campus_customs_new.db for a fresh run.

    Also clears the payment approval queue, since the bills it points at are restored.
    The audit trail is never cleared.
    """
    if active_run(request):
        raise HTTPException(409, "A ticket run is in progress; reset after it finishes.")
    data = await mcp_call(request, "reset_db")
    cleared = request.app.state.queue.clear()
    request.app.state.run = None
    request.app.state.reruns = []
    append("api", "human", "db_reset", result=data, cleared_payment_requests=cleared)
    await refresh_desk_page(request.app)
    checking = next(a for a in data["cash_accounts"] if a["name"] == "checking")
    return ResetResponse(
        reset_from=data["reset_from"],
        working_db=data["working_db"],
        today=data["today"],
        open_tickets=data["open_tickets"],
        balance=checking["balance"],
        cleared_payment_requests=cleared,
    )


# ---------------------------------------------------------------- health


@app.get("/api/health")
async def health(request: Request):
    tools = sorted(t.name for t in await request.app.state.mcp.list_tools())
    return {
        "ok": True,
        "model": MODEL_NAME,
        "portkey_key_set": bool(os.getenv("PORTKEY_API_KEY", "").strip()),
        "mcp_tools": tools,
        "active_run": active_run(request),
    }
