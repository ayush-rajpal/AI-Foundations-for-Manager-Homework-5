"""The Campus Customs agent team: 5 PydanticAI agents with full connectivity.

Every agent has the same two team tools, so any agent can reach any other:

  delegate(to, task)  — hand a task to a teammate and get their structured report back now
  read_board()        — read what teammates have already reported in this run

plus its own slice of the campus-customs MCP tools (models.AGENT_TOOLS). All database
access goes through that MCP server; this module never opens the database itself.

Guardrails:
  * Money: agents can only DRAFT payments and purchases (MCP draft_payment / draft_purchase,
    which change nothing).
    Each verified draft is handed to `on_draft` (the backend's approval queue). No agent
    holds `pay`; only the backend's human approval route calls it.
  * Loops: no delegating to yourself or to anyone waiting in your chain, chains stop at
    MAX_DEPTH agents, and a run allows MAX_DELEGATIONS hand-offs.
  * Tokens: every agent run has request, tool-call, and token caps (LIMITS), and the whole
    run stops delegating once RUN_TOKEN_BUDGET is spent.
  * Customer replies: one draft per run on a single-ticket run, and none while a payment or
    purchase drafted in that run waits for human approval (the reply comes on the automatic
    re-run after approval). Extra or early drafts are refused and withheld. Only the Boss
    may hand off to Customer Service, and customer_reply_gate refuses that hand-off while the
    ticket's invoice is unpaid or an affordable restock hasn't been ordered, so the email is
    always the last step and there is only one per ticket.
  * Audit: every tool call, delegation, draft, and agent output is appended to
    output/audit_trail.json (see audit.py).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models import Model
from pydantic_ai.toolsets import FunctionToolset
from pydantic_ai.usage import UsageLimits

from audit import AuditedToolset, append, read_entries, summarize_run
from config import MODEL_NAME, build_mcp_toolset, build_model, load_prompt
from models import (
    AGENT_IDS,
    AGENT_TOOLS,
    AGENTS,
    BOSS_ID,
    REPORT_TYPES,
    AgentId,
    Delegation,
    ShopDecision,
    display_name,
)

MAX_DEPTH = 4  # longest chain, e.g. boss -> accounting -> customer_service -> inventory
MAX_DELEGATIONS = 15
BOARD_POSTS_SHOWN = 8
RUN_TOKEN_BUDGET = 1_500_000  # whole run, all agents; delegation stops once it's spent

LIMITS = {
    BOSS_ID: UsageLimits(request_limit=30, tool_calls_limit=40, total_tokens_limit=500_000),
    "specialist": UsageLimits(request_limit=15, tool_calls_limit=20, total_tokens_limit=200_000),
}

# Receives (server-verified draft, drafting agent, run_id) and returns a short note for the agent.
DraftSink = Callable[[dict[str, Any], str, str], str]
DRAFT_TOOLS = {"draft_payment", "draft_purchase"}


def highlights(output: BaseModel) -> dict[str, Any]:
    """Short, separately logged pieces of an agent's output, so the dashboard's summary cards
    survive even when the full output is too long for one audit-trail field."""
    data = output.model_dump(mode="json")
    picked: dict[str, Any] = {"summary": data.get("summary"), "ticket_ids": data.get("ticket_ids")}
    if "tickets" in data:  # Boss
        picked["tickets"] = [
            {k: t.get(k) for k in ("ticket_id", "status", "decision", "next_steps")} for t in data["tickets"]
        ]
    for key in ("rule_checks", "payment_orders", "refused_payments", "drafts", "stock_checks",
                "restock_plans", "alternatives", "lease_checks", "margin_checks", "customer_drafts"):
        if data.get(key):
            picked[key] = data[key]
    return picked


# ---------------------------------------------------------------- session state


@dataclass
class ShopSession:
    """Everything one run shares: model, MCP connection, board, delegation log, token spend."""

    model: Model
    mcp: MCPToolset
    on_draft: DraftSink | None = None
    ticket_id: int | None = None  # set for single-ticket (API) runs: one customer reply per run
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    board: list[dict[str, Any]] = field(default_factory=list)
    delegations: list[Delegation] = field(default_factory=list)
    drafts: list[dict[str, Any]] = field(default_factory=list)
    customer_drafts: list[dict[str, Any]] = field(default_factory=list)
    tokens_used: int = 0

    def customer_reply_block(self) -> str | None:
        """Why Customer Service may not draft (another) reply in this run, or None if it may."""
        if self.ticket_id is None:
            return None
        if self.customer_drafts:
            return "Customer Service already drafted this run's one customer reply. Read it on the board."
        if self.drafts:
            items = ", ".join(f"{d.get('kind')} {d.get('amount')} to {d.get('payee')}" for d in self.drafts)
            return (
                f"No customer reply yet: {items} drafted in this run still needs human sign-off. "
                "After the human approves, the team re-runs automatically and Customer Service drafts the "
                "single reply then. Record the ticket as awaiting approval."
            )
        return None

    def post(self, author: str, requested_by: str, output: BaseModel) -> None:
        self.board.append(
            {"author": author, "requested_by": requested_by, "output": output.model_dump(mode="json")}
        )

    def log(self, agent: str, event: str, **details: Any) -> None:
        append(self.run_id, agent, event, **details)

    def after_tool(self, agent: str, name: str, result: Any) -> None:
        """Called by AuditedToolset after each successful tool call."""
        if name in DRAFT_TOOLS and isinstance(result, dict):
            self.drafts.append({**result, "drafted_by": agent})
            note = self.on_draft(result, agent, self.run_id) if self.on_draft else "not queued (no approval queue)"
            self.log(agent, "payment_drafted", draft=result, queue=note)


@dataclass
class TeamDeps:
    """Who is acting, and which agents are waiting on them in the current chain."""

    session: ShopSession
    agent_id: str
    chain: tuple[str, ...]  # root first, ends with agent_id


# ---------------------------------------------------------------- team tools


async def delegate(ctx: RunContext[TeamDeps], to: AgentId, task: str) -> str:
    """Hand a task to a teammate and get their structured report back right away.

    Args:
        to: 'boss', 'inventory', 'accounting', 'facilities', or 'customer_service'.
        task: A specific job, including the ticket id(s) and any facts they need.
    """
    deps = ctx.deps
    session = deps.session
    refusal = None
    if to == deps.agent_id:
        refusal = "You can't delegate to yourself."
    elif to in deps.chain:
        refusal = (
            f"{display_name(to)} is already waiting on this chain ({' -> '.join(deps.chain)}). "
            "Finish with what you have, or delegate to someone else."
        )
    elif len(deps.chain) >= MAX_DEPTH:
        refusal = f"Delegation chain is at the limit ({MAX_DEPTH} agents). Finish with what you have."
    elif len(session.delegations) >= MAX_DELEGATIONS:
        refusal = "The team's delegation budget is used up. Finish with what you have."
    elif session.tokens_used >= RUN_TOKEN_BUDGET:
        refusal = "The run's token budget is spent. Finish now with what you have."
    elif to == "customer_service" and session.ticket_id is not None and deps.agent_id != BOSS_ID:
        refusal = (
            "Only the Boss asks Customer Service, once, at the end of the run after the money and stock "
            "work is done. Finish your report and say what the customer should hear; the Boss hands off."
        )
    elif to == "customer_service" and (block := session.customer_reply_block() or await customer_reply_gate(session)):
        refusal = block
    if refusal:
        session.log(deps.agent_id, "delegation_refused", to_agent=to, task=task, reason=refusal)
        return refusal

    record = Delegation(from_agent=deps.agent_id, to_agent=to, task=task, depth=len(deps.chain))
    session.delegations.append(record)
    session.log(deps.agent_id, "delegation_started", to_agent=to, task=task, depth=record.depth)
    try:
        output = await run_agent(session, to, task, chain=(*deps.chain, to))
    except Exception as exc:
        record.status, record.result = "error", f"{type(exc).__name__}: {exc}"
        session.log(deps.agent_id, "delegation_error", to_agent=to, error=record.result)
        return f"{display_name(to)} could not finish: {record.result}"

    session.post(to, deps.agent_id, output)
    record.status, record.result = "done", output.model_dump_json()
    session.log(deps.agent_id, "delegation_done", to_agent=to, report=output.model_dump(mode="json"))
    return record.result


async def customer_reply_gate(session: ShopSession) -> str | None:
    """Why the ticket isn't ready for its one customer email yet, checked against the database, or None.

    The email comes last. It waits while the ticket's linked invoice is unpaid, and while the
    ticket is short on stock with no restock on order for the gap even though cash covers at
    least one unit. Either means Accounting still has a draft to make (and a human an approval
    to give), so writing the email now would mean a second one after the re-run.
    """
    if session.ticket_id is None:
        return None
    try:
        call = session.mcp.direct_call_tool
        tickets = (await call("list_tickets", {"status": None}))["tickets"]
        ticket = next((t for t in tickets if t["id"] == session.ticket_id), None)
        if ticket is None:
            return None
        todo: list[str] = []
        if ticket.get("invoice_id"):
            inv = (await call("check_invoice", {"invoice_id": ticket["invoice_id"]}))["invoice"]
            if inv.get("status") == "open":
                todo.append(
                    f"invoice {ticket['invoice_id']} (${inv.get('amount', 0):,.2f} to {inv.get('vendor_name')}) is still "
                    "unpaid, so the vendor can't ship; Accounting drafts that payment first"
                )
        if ticket.get("sku") and ticket.get("qty"):
            stock = await call("check_stock", {"sku": ticket["sku"], "size": ticket.get("size")})
            on_hand = sum(s["qty"] for s in stock["sizes"])
            incoming = sum(o["qty"] for o in stock.get("incoming") or [])
            short = ticket["qty"] - on_hand - incoming
            cost = stock.get("unit_cost") or 0
            cash = await call("check_cash", {})
            balance = next((a["balance"] for a in cash["cash_accounts"] if a["name"] == "checking"), cash.get("total_cash", 0))
            if short > 0 and cost and balance >= cost:
                units = min(short, int(balance // cost))
                todo.append(
                    f"{ticket['sku']} {ticket.get('size') or ''} is {short} short ({on_hand} on hand, {incoming} on order) "
                    f"and checking has ${balance:,.2f}, enough for {units} at ${cost:,.2f}; Accounting drafts that "
                    "restock first (a partial restock if the whole gap doesn't fit)"
                )
    except Exception:  # the gate is a safety check; a lookup failure shouldn't stop the run
        return None
    if not todo:
        return None
    return (
        f"Not yet: the customer gets one email, at the very end, once everything else on ticket "
        f"{session.ticket_id} is done. Still to do: {'; '.join(todo)}. Record the ticket as awaiting approval "
        "after the drafts; Customer Service writes the single reply on the re-run after the human approves."
    )


async def read_board(ctx: RunContext[TeamDeps]) -> str:
    """Read the latest reports teammates have posted in this run, so you don't redo their work."""
    posts = ctx.deps.session.board[-BOARD_POSTS_SHOWN:]
    if not posts:
        return "The board is empty; nobody has reported yet."
    return json.dumps(posts, indent=1)


TEAM_TOOLS = FunctionToolset([delegate, read_board])


# ---------------------------------------------------------------- agents


def team_context(agent_id: str) -> str:
    """Roster + delegation rules appended to every agent's prompt file."""
    lines = [
        "\n\n# Your team",
        "Any agent can delegate to any other with `delegate(to, task)`. Use `read_board()` first "
        "to see what teammates already reported.",
        "",
    ]
    for other in AGENT_IDS:
        if other == agent_id:
            continue
        tools = ", ".join(AGENT_TOOLS[other]) or "none"
        lines.append(f"- `{other}` ({display_name(other)}): {AGENTS[other]['role']} MCP tools: {tools}.")
    lines += [
        "",
        f"Your MCP tools: {', '.join(AGENT_TOOLS[agent_id])}.",
        "Delegate only when a teammate owns the answer. Don't delegate back to whoever is waiting on you, "
        "and don't repeat a tool call you've already made. If read_board shows reports from the previous "
        "run, reuse them: only re-check what your task says has changed. Never invent data: every number must come "
        "from an MCP tool or a teammate's report.",
    ]
    return "\n".join(lines)


def build_agent(session: ShopSession, agent_id: str) -> Agent[TeamDeps, Any]:
    allowed = set(AGENT_TOOLS[agent_id])
    return Agent(
        session.model,
        name=display_name(agent_id),
        deps_type=TeamDeps,
        output_type=ShopDecision if agent_id == BOSS_ID else REPORT_TYPES[agent_id],
        instructions=load_prompt(agent_id) + team_context(agent_id),
        toolsets=[
            AuditedToolset(TEAM_TOOLS),
            AuditedToolset(session.mcp.filtered(lambda ctx, tool_def: tool_def.name in allowed)),
        ],
        retries=3,
    )


async def run_agent(session: ShopSession, agent_id: str, task: str, *, chain: tuple[str, ...]) -> BaseModel:
    """Run one agent on a task inside an existing session and return its structured output."""
    session.log(agent_id, "agent_started", task=task, chain=list(chain))
    result = await build_agent(session, agent_id).run(
        task,
        deps=TeamDeps(session=session, agent_id=agent_id, chain=chain),
        usage_limits=LIMITS.get(agent_id, LIMITS["specialist"]),
    )
    session.tokens_used += result.usage.total_tokens
    output = result.output
    drafts = getattr(output, "drafts", None) if agent_id == "customer_service" else None
    if drafts:
        block = session.customer_reply_block()
        if block:  # e.g. Accounting drafted a payment in parallel: hold the reply for the re-run
            session.log(agent_id, "customer_draft_withheld", reason=block, drafts=[d.model_dump() for d in drafts])
            output = output.model_copy(update={"drafts": [], "open_questions": [*output.open_questions, block]})
        else:
            session.customer_drafts.extend(d.model_dump() for d in drafts)
    session.log(
        agent_id,
        "agent_output",
        **highlights(output),
        output=output.model_dump(mode="json"),
        tokens_used_run=session.tokens_used,
    )
    return output


async def run_team(
    task: str,
    *,
    entry: str = BOSS_ID,
    on_draft: DraftSink | None = None,
    reset: bool = False,
    run_id: str | None = None,
    board: list[dict[str, Any]] | None = None,
    extra: dict[str, Any] | None = None,
    finalize: Callable[[ShopSession], Awaitable[None]] | None = None,
) -> tuple[BaseModel, ShopSession]:
    """Start a run at any agent (the Boss by default). Opens one MCP connection for the whole run.

    reset=True restores the working database through the MCP `reset_db` tool first (CLI only;
    the API resets through its own route). `finalize` runs after the agents finish, before the
    run summary is written (the API uses it to mark the ticket resolved).
    """
    session = ShopSession(
        model=build_model(), mcp=build_mcp_toolset(), on_draft=on_draft, ticket_id=(extra or {}).get("ticket_id")
    )
    if run_id:
        session.run_id = run_id
    if board:  # findings from the previous run on this ticket, so agents don't redo them
        session.board.extend(board)
    session.log("runner", "run_started", entry_agent=entry, task=task, model=MODEL_NAME, reset=reset, **(extra or {}))
    try:
        async with session.mcp:
            if reset:
                result = await session.mcp.direct_call_tool("reset_db", {})
                session.log("runner", "tool_call", tool="reset_db", args={}, result=result)
            output = await run_agent(session, entry, task, chain=(entry,))
            if finalize:
                await finalize(session)
    except Exception as exc:
        session.log("runner", "run_error", error=f"{type(exc).__name__}: {exc}", tokens_used=session.tokens_used)
        raise
    session.post(entry, "user", output)
    session.log(
        "runner",
        "run_finished",
        delegations=len(session.delegations),
        payment_drafts=len(session.drafts),
        tokens_used=session.tokens_used,
        **(extra or {}),
    )
    # one roll-up record per run (ticket, agents, hand-offs, tools, drafts, email, outcome)
    session.log("runner", "run_summary", **summarize_run(read_entries(limit=100_000, run_id=session.run_id)[0], session.run_id))
    return output, session
