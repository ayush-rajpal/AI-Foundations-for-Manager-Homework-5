"""Data types for the Campus Customs multi-agent operations team.

- AGENTS / AGENT_TOOLS: roster of the 5 agents and which MCP tools each may call
- BACKEND_ONLY_TOOLS: MCP tools no agent may ever hold (pay, reset_db, record_restock_order)
- RuleCheck: one shop rule an agent checked, with the database evidence
- Specialist reports: InventoryReport, AccountingReport, FacilitiesReport, CustomerServiceReport
- PaymentOrder: a payment an agent drafted, and where it stands
- API types: TicketSummary, RunStarted, PaymentRequest, ApproveRequest, CashBalance, ...
- CustomerDraft: a reply that stays on the internal board (never sent)
- ShopDecision: the Boss's final call on every ticket
- Delegation: one agent-to-agent hand-off, kept for the trace

Validators enforce the hard rules, so PydanticAI makes the model retry instead of
returning an output that breaks them:
  * a PaymentOrder can't overdraw cash (cash_after must be >= 0)
  * pending payment orders together can't exceed the cash balance
  * a discount can't be approved below unit_cost
  * a CustomerDraft is always a draft and never sent
  * a ticket can't be "resolved" unless every constraint is satisfied and no payment
    is still waiting on a human
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, computed_field, model_validator

# ---------------------------------------------------------------- roster

AgentId = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]

BOSS_ID = "boss"
SPECIALIST_IDS: tuple[str, ...] = ("inventory", "accounting", "facilities", "customer_service")
AGENT_IDS: tuple[str, ...] = (BOSS_ID, *SPECIALIST_IDS)

AGENTS: dict[str, dict[str, str]] = {
    "boss": {
        "name": "Boss",
        "role": "Orchestrates the shop: triages tickets, delegates, reviews findings, makes the final call.",
    },
    "inventory": {
        "name": "Inventory",
        "role": "Stock by SKU and size, shortfalls, matching items to vendors, vendor lead times, "
        "and the no-shipping-while-an-invoice-is-open rule.",
    },
    "accounting": {
        "name": "Accounting",
        "role": "Cash balances, margins, discount checks, open and overdue invoices, and payment "
        "orders for human approval (never below zero cash).",
    },
    "facilities": {
        "name": "Facilities",
        "role": "Shop space and leases: rent amounts, landlords, and due dates from the lease records.",
    },
    "customer_service": {
        "name": "Customer Service",
        "role": "Drafts customer replies (delays, policies, discounts). Drafts stay on the board, never sent.",
    },
}

# Which campus-customs MCP tools each agent may call. Agents only DRAFT payments
# (draft_payment); pay and reset_db are called by the backend routes alone.
AGENT_TOOLS: dict[str, tuple[str, ...]] = {
    "boss": (
        "list_tickets", "update_ticket", "check_stock", "check_invoice",
        "check_rent", "check_vendor", "check_cash",
    ),
    "inventory": ("list_tickets", "check_stock", "check_vendor", "check_invoice", "find_alternatives"),
    "accounting": (
        "list_tickets", "check_cash", "check_invoice", "check_rent",
        "check_stock", "check_discount", "draft_payment", "draft_purchase",
    ),
    "facilities": ("list_tickets", "check_rent"),
    "customer_service": ("list_tickets", "check_stock"),
}

# Only the backend's human approval route (pay) and reset route (reset_db) call these.
BACKEND_ONLY_TOOLS: frozenset[str] = frozenset({"pay", "reset_db", "record_restock_order"})
for _agent, _tools in AGENT_TOOLS.items():
    if BACKEND_ONLY_TOOLS & set(_tools):
        raise RuntimeError(f"{_agent} must not hold backend-only tools {BACKEND_ONLY_TOOLS & set(_tools)}")


def display_name(agent_id: str) -> str:
    return AGENTS.get(agent_id, {}).get("name", agent_id)


# ---------------------------------------------------------------- shared pieces


class RuleCheck(BaseModel):
    """One shop rule or constraint an agent checked against the database."""

    rule: str = Field(description="The rule or constraint, e.g. 'Vendor has no open unpaid invoice'.")
    satisfied: bool
    evidence: str = Field(description="Tool name and the database values that prove it.")


class AgentReport(BaseModel):
    """Fields every specialist report shares."""

    agent: AgentId
    ticket_ids: list[int] = Field(default_factory=list)
    summary: str = Field(description="Two or three sentences: what you found and what you recommend.")
    facts: list[str] = Field(
        default_factory=list, description="Facts read from MCP tools only. Never invent values."
    )
    rule_checks: list[RuleCheck] = Field(default_factory=list)
    open_questions: list[str] = Field(
        default_factory=list, description="Anything you could not confirm from the database."
    )


# ---------------------------------------------------------------- inventory


class StockCheck(BaseModel):
    sku: str
    size: str
    requested: int = Field(ge=0)
    on_hand: int = Field(ge=0)
    location: str | None = None

    @computed_field
    @property
    def shortfall(self) -> int:
        return max(self.requested - self.on_hand, 0)


class RestockPlan(BaseModel):
    """How a shortfall could be refilled, and what is blocking it."""

    sku: str
    size: str
    qty_needed: int = Field(gt=0)
    vendor_id: int
    vendor_name: str
    lead_days: int = Field(ge=0, description="From the vendors table.")
    blocked_by_invoice_id: int | None = Field(
        default=None, description="Open unpaid invoice that stops this vendor from shipping."
    )
    earliest_arrival: date | None = Field(
        default=None, description="desk.date_today + lead_days, counted from when the vendor can ship."
    )


class Alternative(BaseModel):
    """An in-stock product in the same size that could replace a short item (from find_alternatives)."""

    sku: str
    name: str
    size: str
    on_hand: int = Field(ge=0)
    list_price: float | None = None
    why: str = Field(description="e.g. 'same category (apparel), same size, 4 in stock'.")


class InventoryReport(AgentReport):
    agent: Literal["inventory"] = "inventory"
    stock_checks: list[StockCheck] = Field(default_factory=list)
    restock_plans: list[RestockPlan] = Field(default_factory=list)
    alternatives: list[Alternative] = Field(
        default_factory=list, description="In-stock options in the same size for anything short."
    )


# ---------------------------------------------------------------- accounting


class PaymentOrder(BaseModel):
    """A payment an agent drafted. Only a human, through the backend approve route, can pay it."""

    kind: Literal["invoice", "rent", "purchase"]
    ref_id: int = Field(description="invoices.id, leases.id, or vendors.id for a purchase")
    payee: str = Field(description="Vendor or landlord name from the database, not from ticket text.")
    amount: float = Field(gt=0)
    account: str = Field(description="cash_accounts.name, e.g. 'checking'.")
    cash_before: float
    cash_after: float
    reason: str
    status: Literal["awaiting_human_approval", "paid", "declined_by_human", "refused"] = (
        "awaiting_human_approval"
    )
    payment_id: int | None = Field(default=None, description="payments.id once paid.")
    approved_by: str | None = Field(default=None, description="The human who approved it, from the pay result.")

    @model_validator(mode="after")
    def no_overdraft(self) -> PaymentOrder:
        if round(self.cash_before - self.amount, 2) != round(self.cash_after, 2):
            raise ValueError("cash_after must equal cash_before - amount.")
        if self.cash_after < 0 and self.status != "refused":
            raise ValueError(
                f"Refuse this payment: {self.account} has {self.cash_before:.2f}, "
                f"paying {self.amount:.2f} would leave {self.cash_after:.2f}. No negative balances."
            )
        return self


class MarginCheck(BaseModel):
    """A proposed price or discount checked against unit_cost and list_price."""

    sku: str
    qty: int = Field(gt=0)
    unit_cost: float
    list_price: float
    proposed_price: float = Field(description="Per-unit price after any discount.")
    approved: bool

    @computed_field
    @property
    def discount_pct(self) -> float:
        return round((1 - self.proposed_price / self.list_price) * 100, 1) if self.list_price else 0.0

    @computed_field
    @property
    def margin_per_unit(self) -> float:
        return round(self.proposed_price - self.unit_cost, 2)

    @model_validator(mode="after")
    def price_floor(self) -> MarginCheck:
        if self.approved and self.proposed_price < self.unit_cost:
            raise ValueError(
                f"Can't approve {self.proposed_price:.2f}/unit for {self.sku}: below unit_cost {self.unit_cost:.2f}."
            )
        return self


class AccountingReport(AgentReport):
    agent: Literal["accounting"] = "accounting"
    desk_date_today: date | None = None
    cash_balance: float | None = None
    margin_checks: list[MarginCheck] = Field(default_factory=list)
    payment_orders: list[PaymentOrder] = Field(default_factory=list)
    refused_payments: list[str] = Field(
        default_factory=list, description="Payments refused (e.g. not enough cash), with the reason."
    )

    @model_validator(mode="after")
    def orders_fit_cash_together(self) -> AccountingReport:
        """cash_balance is the balance now, so only orders still awaiting approval must fit in it."""
        pending = [p for p in self.payment_orders if p.status == "awaiting_human_approval"]
        if self.cash_balance is not None and pending:
            total = sum(p.amount for p in pending)
            if total > self.cash_balance:
                raise ValueError(
                    f"Pending payment orders total {total:.2f} but cash is {self.cash_balance:.2f}. "
                    "Refuse or drop orders until they fit; no negative balances."
                )
        return self


# ---------------------------------------------------------------- facilities


class LeaseCheck(BaseModel):
    lease_id: int
    space_name: str
    landlord: str
    monthly_rent: float = Field(description="From the leases table, the source of truth.")
    next_due: date
    days_until_due: int = Field(description="Relative to desk.date_today; negative means overdue.")
    ticket_requester: str | None = None
    ticket_amount: float | None = Field(default=None, description="Amount claimed in the ticket, if any.")
    landlord_matches: bool = Field(description="Ticket requester is the landlord on the lease.")
    amount_matches: bool | None = Field(
        default=None, description="Ticket amount equals monthly_rent; None if the ticket gave no amount."
    )


class FacilitiesReport(AgentReport):
    agent: Literal["facilities"] = "facilities"
    lease_checks: list[LeaseCheck] = Field(default_factory=list)


# ---------------------------------------------------------------- customer service


class CustomerDraft(BaseModel):
    """A customer reply that stays on the internal board. It is never emailed."""

    ticket_id: int
    to: str
    subject: str
    body: str
    status: Literal["draft"] = "draft"
    sent: Literal[False] = False


def _one_draft_per_ticket(drafts: list[CustomerDraft]) -> None:
    tickets = [d.ticket_id for d in drafts]
    if len(tickets) != len(set(tickets)):
        raise ValueError("Write exactly one customer reply per ticket; merge everything into a single draft.")


class CustomerServiceReport(AgentReport):
    agent: Literal["customer_service"] = "customer_service"
    drafts: list[CustomerDraft] = Field(
        default_factory=list, description="At most ONE reply per ticket per run."
    )

    @model_validator(mode="after")
    def one_reply_per_ticket(self) -> CustomerServiceReport:
        _one_draft_per_ticket(self.drafts)
        return self


SpecialistReport = InventoryReport | AccountingReport | FacilitiesReport | CustomerServiceReport

REPORT_TYPES: dict[str, type[AgentReport]] = {
    "inventory": InventoryReport,
    "accounting": AccountingReport,
    "facilities": FacilitiesReport,
    "customer_service": CustomerServiceReport,
}


# ---------------------------------------------------------------- boss


TicketStatus = Literal["resolved", "awaiting_human_approval", "blocked", "in_progress"]


class TicketResolution(BaseModel):
    ticket_id: int
    status: TicketStatus
    handled_by: list[AgentId] = Field(default_factory=list)
    constraints: list[RuleCheck] = Field(
        default_factory=list, description="Every constraint that must hold before this ticket is resolved."
    )
    decision: str = Field(description="The Boss's call and why, citing database values.")
    next_steps: list[str] = Field(default_factory=list)
    payment_order_refs: list[str] = Field(
        default_factory=list,
        description="Payments this ticket still waits on a human for, e.g. 'invoice 501'. Empty once paid.",
    )

    @model_validator(mode="after")
    def resolved_only_when_all_constraints_hold(self) -> TicketResolution:
        if self.status == "resolved":
            if not self.constraints:
                raise ValueError(f"Ticket {self.ticket_id}: list the constraints you checked before resolving.")
            failed = [c.rule for c in self.constraints if not c.satisfied]
            if failed:
                raise ValueError(f"Ticket {self.ticket_id} can't be resolved; unsatisfied: {failed}.")
            if self.payment_order_refs:
                raise ValueError(
                    f"Ticket {self.ticket_id} can't be resolved while a payment awaits human approval."
                )
        return self


class ShopDecision(BaseModel):
    """The Boss's final output for a run."""

    summary: str
    tickets: list[TicketResolution]
    payment_orders: list[PaymentOrder] = Field(
        default_factory=list,
        description="Every payment this run touched: paid (with the human approver), declined, refused, or pending.",
    )
    customer_drafts: list[CustomerDraft] = Field(
        default_factory=list, description="Replies that stay on the internal board. At most one per ticket."
    )

    @model_validator(mode="after")
    def one_reply_per_ticket(self) -> ShopDecision:
        _one_draft_per_ticket(self.customer_drafts)
        return self


# ---------------------------------------------------------------- trace


class Delegation(BaseModel):
    """One agent-to-agent hand-off."""

    from_agent: AgentId
    to_agent: AgentId
    task: str
    depth: int
    status: Literal["running", "done", "error", "refused"] = "running"
    result: str = ""


# ---------------------------------------------------------------- API (backend/main.py)


class TicketSummary(BaseModel):
    id: int
    type: str
    requester: str
    subject: str
    status: str = Field(description="Raw tickets.status from the database.")
    resolved: bool = Field(description="True only when tickets.status is 'resolved'.")
    sku: str | None = None
    size: str | None = None
    qty: int | None = None
    lease_id: int | None = None
    invoice_id: int | None = None
    notes: str | None = None
    created_at: str


class RunState(BaseModel):
    """The ticket run the API started most recently."""

    run_id: str
    ticket_id: int
    status: Literal["running", "done", "error"] = "running"
    started_at: str
    finished_at: str | None = None
    tokens_used: int | None = None
    payment_requests: list[int] = Field(default_factory=list, description="PaymentRequest ids drafted in this run.")
    decision: dict | None = Field(default=None, description="The Boss's ShopDecision once done.")
    error: str | None = None


class TicketsResponse(BaseModel):
    today: str
    tickets: list[TicketSummary]
    active_run: RunState | None = Field(default=None, description="Set while a ticket run is in progress.")


class RunStarted(BaseModel):
    run_id: str
    ticket_id: int
    status: Literal["running"] = "running"
    message: str


class EventsResponse(BaseModel):
    events: list[dict]
    last_seq: int = Field(description="Pass this back as ?since= to get only newer events.")
    active_run: RunState | None = None
    last_run: RunState | None = None


class PaymentRequest(BaseModel):
    """A payment or purchase an agent drafted (draft_payment / draft_purchase), waiting for a human."""

    id: int
    kind: Literal["invoice", "rent", "purchase"]
    ref_id: int = Field(description="invoices.id, leases.id, or vendors.id for a purchase")
    payee: str
    amount: float
    account: str
    description: str | None = None
    due_date: str | None = None
    balance_before: float
    balance_after: float
    sku: str | None = Field(default=None, description="Purchases only.")
    size: str | None = Field(default=None, description="Purchases only.")
    qty: int | None = Field(default=None, description="Purchases only.")
    details: dict = Field(
        default_factory=dict,
        description="Extra draft facts, e.g. unit_cost, lead_days, vendor_can_ship, blocked_by_invoices.",
    )
    drafted_by: str
    run_id: str
    ticket_id: int | None = Field(default=None, description="Ticket whose run drafted it (API runs).")
    drafted_at: str
    status: Literal["awaiting_human_approval", "paid", "refused"] = "awaiting_human_approval"
    approved_by: str | None = None
    payment: dict | None = Field(default=None, description="The pay tool's result once paid.")
    refusal: str | None = None
    blocked_reason: str | None = Field(
        default=None, description="Live, not saved: why approval would be blocked right now (purchases)."
    )
    auto_rerun: dict | None = Field(
        default=None,
        description="Approve response only: whether the team re-runs the ticket now ('started'), "
        "after the current run ('queued'), or after other approvals ('waiting_for_other_approvals').",
    )


class ApproveRequest(BaseModel):
    approved_by: str = Field(min_length=1, description="Name of the human approving this payment.")


class CashBalance(BaseModel):
    today: str
    account: str
    balance: float
    as_of: str
    pending_approvals: float = Field(description="Total of payment requests still awaiting approval.")


class ResetResponse(BaseModel):
    reset_from: str
    working_db: str
    today: str
    open_tickets: int
    balance: float
    cleared_payment_requests: int

