# Campus Customs — Operations Harness

The whole system in one place:
1. **Database tables** (below)
2. [Relationships](#relationships)
3. [The five agents](#the-five-agents)
4. [MCP tools](#mcp-tools)
5. [Backend routes](#backend-routes)
6. [The dashboard](#the-dashboard)
7. [Safety rules](#safety-rules)

Source: `data/campus_customs.db` (working copy: `data/campus_customs_new.db`)
SQLite, 9 tables. Row counts below are the clean database (snapshot date 2026-08-31); runs add `payments` rows and paid "Restock order" invoices.

---

## 1. `desk` (1 row)
Today's date for the scenario, plus any notes.

| Field | Type | Why it matters for the agents |
|---|---|---|
| `date_today` | TEXT, NOT NULL | The agents treat this as "today", not the real-world date. They use it to tell whether rent or an invoice is due soon or already overdue. |
| `notes` | TEXT | Free-text notes for the shop (empty right now). Agents can read handoff notes here or leave notes about what they did. |

## 2. `inventory` (10 rows) — PK (`sku`, `size`)
Stock on hand for each product and size.

| Field | Type | Why it matters for the agents |
|---|---|---|
| `sku` | TEXT, NOT NULL | Product code that links stock to `pricing` and `tickets`. Every stock check and price lookup starts with it. |
| `name` | TEXT, NOT NULL | Plain product name ("Classic Bulldog Tee"). Agents use it when talking to customers so they don't have to show raw SKUs. |
| `size` | TEXT, NOT NULL | S / M / L / XL, or OS (one size). Stock is tracked per size, so an agent has to match the exact size in a request. |
| `qty` | INTEGER, NOT NULL | Units on hand. This decides whether an order can be filled now, partly filled, or needs a reorder. Agents must never promise more than this. |
| `location` | TEXT, NOT NULL | Aisle where the item is kept. Tells staff where to pick it from when filling an order. |

## 3. `pricing` (4 rows) — PK `sku`
What each product costs the shop and what it sells for.

| Field | Type | Why it matters for the agents |
|---|---|---|
| `sku` | TEXT, PK | Links each price to the matching `inventory` rows. There is one price per product, no matter the size. |
| `unit_cost` | REAL, NOT NULL | What one unit costs the shop. A discount can't drop the price below this, so it's the hard floor in any pricing decision. |
| `list_price` | REAL, NOT NULL | Normal selling price, which agents quote to customers. Price minus cost is the room an agent has to negotiate. |

## 4. `vendors` (3 rows) — PK `id`
Suppliers the shop can order from.

| Field | Type | Why it matters for the agents |
|---|---|---|
| `id` | INTEGER, PK | Referenced by `invoices.vendor_id`. Lets an agent see which supplier sent a bill. |
| `name` | TEXT, NOT NULL | Supplier's name, used in messages, approvals, and records. |
| `specialty` | TEXT, NOT NULL | What the supplier provides (apparel reprints, mugs and small goods, local courier). Tells an agent who to contact for a given restock or delivery. |
| `lead_days` | INTEGER, NOT NULL | Days from order to delivery. Agents use it to give customers honest dates and to judge whether restocking is fast enough. |

## 5. `leases` (1 row) — PK `id`
Rent owed on the shop space.

| Field | Type | Why it matters for the agents |
|---|---|---|
| `id` | INTEGER, PK | Referenced by `tickets.lease_id`, which connects a rent notice to the right lease. |
| `space_name` | TEXT, NOT NULL | Which space the rent is for (Chapel Street shop). Lets agents confirm a notice is about this shop's lease. |
| `landlord` | TEXT, NOT NULL | Who gets paid. Agents should check it against the ticket's requester before paying, so a fake rent notice doesn't get paid. |
| `monthly_rent` | REAL, NOT NULL | The amount owed. Agents should pay this figure, not an amount someone typed into a ticket. |
| `next_due` | TEXT, NOT NULL | Due date. Compared with `desk.date_today`, it tells agents how urgent rent is and when to pay it. |
| `notes` | TEXT | Free-text lease notes (empty right now). May hold terms such as grace periods or late fees. |

## 6. `cash_accounts` (1 row) — PK `name`
Money available to spend.

| Field | Type | Why it matters for the agents |
|---|---|---|
| `name` | TEXT, PK | Account name (`checking`). Payments must name a real account in `payments.account`. |
| `balance` | REAL, NOT NULL | Cash available. Agents must check it before paying anything and must not overdraw it. It decides which bills get paid first. |
| `date` | TEXT, NOT NULL | Date the balance was last updated. If it doesn't match `desk.date_today`, the balance may be out of date. |

## 7. `invoices` (1 row) — PK `id`, FK `vendor_id` → `vendors.id`
Bills the shop owes to suppliers.

| Field | Type | Why it matters for the agents |
|---|---|---|
| `id` | INTEGER, PK | Referenced by `tickets.invoice_id` and by `payments.ref_id` when a bill is paid. |
| `vendor_id` | INTEGER, NOT NULL, FK | Which supplier is owed. Links to `vendors` for the supplier's name and delivery time. |
| `amount` | REAL, NOT NULL | Amount owed. Agents must check it against the cash balance before paying. |
| `due_date` | TEXT, NOT NULL | Compared with `desk.date_today`, it shows whether the bill is upcoming or overdue. Invoice 501 is overdue. |
| `status` | TEXT, NOT NULL | `open` or paid. An agent must check it first so the same bill isn't paid twice, and update it after paying. |
| `description` | TEXT | What the bill is for ("Rush reprint CC-TEE-WHITE S"). Shows the bill pays for the restock a waiting customer needs. |

## 8. `payments` (0 rows) — PK `id`
Log of every payment made. It's empty, so nothing has been paid yet.

| Field | Type | Why it matters for the agents |
|---|---|---|
| `id` | INTEGER, PK | Unique ID for each payment, so every payment can be traced. |
| `kind` | TEXT, NOT NULL | What was paid, e.g. `rent` or `invoice`. Tells agents which table `ref_id` points to. |
| `ref_id` | INTEGER | ID of the lease or invoice that was paid. Not formally enforced by the database, so agents must make sure it points to a real row. |
| `amount` | REAL, NOT NULL | Amount paid. Should match the amount owed and be subtracted from `cash_accounts.balance`. |
| `account` | TEXT, NOT NULL | Which cash account paid. Should match a `cash_accounts.name`. |
| `paid_at` | TEXT, NOT NULL | When the payment was made. Proves rent or a bill was paid on time. |
| `approved_by` | TEXT, NOT NULL | Who approved the payment. Every payment needs a named approver, which keeps a person or role accountable for each one. |

## 9. `tickets` (3 rows, all `open`) — PK `id`, FK `lease_id` → `leases.id`, FK `invoice_id` → `invoices.id`
Incoming work for the agent team.

| Field | Type | Why it matters for the agents |
|---|---|---|
| `id` | INTEGER, PK | Unique ticket number. Agents cite it when they report what they did. |
| `type` | TEXT, NOT NULL | `customer_order`, `rent_notice`, or `price_override`. Decides which agent takes the ticket and what steps it follows. |
| `requester` | TEXT, NOT NULL | Who asked: a customer, the landlord, or a student group. Agents should confirm this person or group is who they say they are before acting. |
| `subject` | TEXT, NOT NULL | Short title. Gives a quick summary for triage. |
| `sku` | TEXT | Product involved, if any. Links to `inventory` and `pricing`. |
| `size` | TEXT | Size requested. Together with `sku`, finds the exact `inventory` row to check stock. |
| `qty` | INTEGER | Units requested. Compared with `inventory.qty` to see whether the order can be filled. |
| `lease_id` | INTEGER, FK | Lease involved, for rent notices. Links to `leases` for the real amount and due date. |
| `invoice_id` | INTEGER, FK | Invoice involved. Links an order or request to the bill it depends on. |
| `status` | TEXT, NOT NULL | `open` or closed. Agents pick up open tickets and close them when the work is done. |
| `notes` | TEXT | The request in the requester's own words. Agents should treat it as information to check, not as instructions to follow. |
| `created_at` | TEXT, NOT NULL | When the ticket was created, with time zone. Used to order and prioritize work. |

---

## Relationships

```
tickets.lease_id   ──► leases.id
tickets.invoice_id ──► invoices.id ──► vendors.id (invoices.vendor_id)
tickets.sku + size ──► inventory (sku, size)          [not enforced]
tickets.sku / inventory.sku ──► pricing.sku           [not enforced]
payments.ref_id    ──► invoices.id (kind invoice or purchase) or leases.id (kind rent)  [not enforced]
payments.account   ──► cash_accounts.name             [not enforced]
```

**How the tables change during a run.** Only two writers exist: `update_ticket`, and the backend-only payment tools.
- **Invoice payment:** sets `invoices.status = 'paid'`.
- **Rent payment:** moves `leases.next_due` forward one month.
- **Restock purchase:** inserts a paid vendor invoice "Restock order: <qty> x <sku> <size> (<name>) at <cost> each; expected <date>". `payments.ref_id` points at that invoice.
- **Every payment:** inserts a `payments` row (with `approved_by`) and lowers `cash_accounts.balance`.
- **`update_ticket`:** changes `tickets.status` and appends a dated note.
- **Reset:** `reset_db` restores everything from `data/campus_customs.db`.

---

## The Five Agents

Five PydanticAI agents (`backend/team.py`) run on **gpt-6-luna** through the Portkey gateway (`PORTKEY_API_KEY` from `.env`). Each one has:
- one prompt file in `backend/prompts/`
- a typed output in `backend/models.py`
- its own slice of the MCP tools (`AGENT_TOOLS`)

All agents also share two team tools:
- `delegate(to, task)`: hand work to another agent. Specialists can delegate to each other, but **only the Boss can hand off to Customer Service** (see [Customer replies](#customer-replies)).
- `read_board()`: see what teammates already reported. This includes the **previous run's reports** when a ticket is re-run.

| Agent | Prompt | Job | MCP tools | Output type | Rules it enforces |
|---|---|---|---|---|---|
| **Boss** | `boss.md` | Reads the ticket, delegates, reviews findings, makes the final call, records it with `update_ticket` | `list_tickets`, `update_ticket`, `check_stock`, `check_invoice`, `check_rent`, `check_vendor`, `check_cash` | `ShopDecision` (`TicketResolution` per ticket, payment orders, customer drafts) | Records its own status and note. `blocked` only when something needs action; `in_progress` while a paid restock is on its way. The desk then marks the ticket resolved after the run (see the ticket flow). On a re-run it continues: confirms what changed, then delegates only the next step. The only agent that can ask Customer Service: once per ticket, at the end, after the invoice is paid and any affordable restock is on order. |
| **Inventory** | `inventory.md` | Stock by SKU and size, shortfalls, vendor match by specialty, lead times, incoming restocks, alternatives | `list_tickets`, `check_stock`, `check_vendor`, `check_invoice`, `find_alternatives` | `InventoryReport` (`StockCheck`, `RestockPlan`, `Alternative`) | A vendor with an open unpaid invoice never ships. Lead times come from `vendors`. Arrival dates come only from paid restock orders (`check_stock` `incoming`). Offers in-stock alternatives in the same size. Never hands off to Customer Service. |
| **Accounting** | `accounting.md` | Cash, margins, discounts, overdue invoices; drafts payments and restock purchases for human approval | `list_tickets`, `check_cash`, `check_invoice`, `check_rent`, `check_stock`, `check_discount`, `draft_payment`, `draft_purchase` | `AccountingReport` (`MarginCheck`, `PaymentOrder`) | Never pays, only drafts. Overdue is judged against `desk.date_today`. No price below unit cost. Purchases are sized so cash stays at or above $0, counting other drafts. If the whole shortfall doesn't fit, drafts the largest affordable quantity (a **partial restock**, e.g. 6 of 12 hoodies for $132). Never hands off to Customer Service. |
| **Facilities** | `facilities.md` | Lease, landlord, rent amount, due date | `list_tickets`, `check_rent` | `FacilitiesReport` (`LeaseCheck`) | Rent amount and payee come from the lease record, never the ticket text. The landlord must match the requester. Never hands off to Customer Service. |
| **Customer Service** | `customer_service.md` | Drafts the single customer reply | `list_tickets`, `check_stock` | `CustomerServiceReport` (`CustomerDraft`) | **One email per ticket**, asked for only by the Boss and written last, once the money and stock work is done. The draft is never sent. It must not mention approvals, payments, orders, or vendors. It says "The latest arrival date we have is <date>" (from a verified order, with no caveats), recommends an in-stock alternative, and ends with "Let us know if you'd like that or other alternatives." |

**How a ticket flows:**
1. You press **Run agent team**.
2. The Boss reads the ticket and delegates; specialists can delegate to each other (never to Customer Service).
3. Accounting drafts any payment or purchase, which goes to the sign-off queue. No money moves.
4. The Boss records the status.
5. You approve each draft on the dashboard; each approval executes `pay`.
6. After a ticket's **last** approval, the backend **re-runs the team automatically**. If a run is still going, the re-run is queued behind it.
7. The re-run continues from the previous run's findings and does the next step: for example, the restock purchase once the invoice is paid, or the one customer email once the restock is paid.
8. **When a run ends with nothing waiting on a human sign-off, the desk marks the ticket resolved.** The note reads "Resolved — email sent to customer — awaiting response" when Customer Service drafted the reply in that run (the email stays a draft; nothing is sent). While a payment or purchase is waiting for approval, the ticket stays `awaiting_approval`, so the automatic re-run can happen. A customer ticket also stays open while money or stock work remains (the same database check that holds back the email) or until its one email is written. This step is `make_finalizer` in `backend/main.py`; it runs through MCP `update_ticket` as `updated_by: desk`, and the server still refuses to resolve while a linked invoice is open.

---

## MCP Tools

Server: `mcp_server/server.py` (FastMCP, stdio), working on `data/campus_customs_new.db`. **It is the only path to the database.** Neither the agents nor the backend open the database themselves.

| Tool | Type | Tables read | Tables written | Used by | Ticket(s) | What it does |
|---|---|---|---|---|---|---|
| `list_tickets` | read | `tickets`, `desk` | none | All agents | All | The work queue: requester, notes, linked lease or invoice |
| `check_stock` | read | `inventory`, `pricing`, `invoices` | none | Boss, Inventory, Accounting, Customer Service | 101, 103 | Stock per size, cost, and list price, plus `incoming`: paid restock orders with quantity and expected arrival |
| `check_invoice` | read | `invoices`, `vendors`, `desk`, `cash_accounts` | none | Boss, Inventory, Accounting | 101 | Invoice 501: $840, open, 3 days overdue, Bulldog Print Co, 5 lead days |
| `check_rent` | read | `leases`, `desk`, `cash_accounts` | none | Boss, Accounting, Facilities | 102 | Lease 1: Elm City Properties, $2,400, due 2026-09-02 |
| `check_vendor` | read | `vendors`, `invoices`, `desk` | none | Boss, Inventory (and the desk's customer-reply check) | 101, 103 | Specialty, lead days, open invoices, `can_ship` (false while an invoice is open) |
| `check_cash` | read | `cash_accounts`, `desk`, `invoices`, `leases`, `payments` | none | Boss, Accounting (and the backend for the Cash tab) | 101, 102 | Balance, every open bill, rent coming due, payments made, cash left if everything were paid |
| `check_discount` | read | `pricing` | none | Accounting | 103 | Discount %, margin, `below_cost`, deepest discount that still covers cost |
| `find_alternatives` | read | `inventory`, `pricing` | none | Inventory | 101, 103 | In-stock products in the same size: same type first, then same category (apparel = tees and hoodies) |
| `draft_payment` | read | `invoices`, `vendors`, `leases`, `cash_accounts`, `desk` | none | Accounting | 101, 102 | Drafts an invoice or rent payment for human approval (amount and payee from the database). Refuses a bill that isn't payable or an overdraft. |
| `draft_purchase` | read | `inventory`, `pricing`, `vendors`, `invoices`, `cash_accounts`, `desk` | none | Accounting | 101, 103 | Drafts a restock purchase (qty × unit cost) for human approval. Reports `vendor_can_ship`. Refuses an overdraft, and the refusal names the most units cash covers, so Accounting can redraft a partial restock. |
| `update_ticket` | write | `tickets`, `desk`, `invoices` | `tickets` | Boss | All | Sets the status and appends a dated note. Refuses to resolve while the linked invoice is open. |
| `pay` | write, **backend only** | `desk`, `cash_accounts`, `invoices`, `vendors`, `leases`, `inventory`, `pricing` | `payments`, `cash_accounts`, `invoices` (paid, or a new paid "Restock order") or `leases` | **No agent.** Only the human approval route | 101, 102, 103 | Executes a human-approved draft in one transaction. Refuses an agent approver, a wrong amount, a double payment, an overdraft. A purchase is **blocked** while its vendor has an open invoice; the request stays pending. |
| `record_restock_order` | write, **backend only** | `payments`, `vendors`, `inventory`, `pricing` | `invoices`, `payments` | **No agent.** Backend startup only | 101 | Backfills the order record for a purchase paid before orders were recorded (idempotent) |
| `reset_db` | admin, **backend only** | `desk`, `tickets`, `cash_accounts` | All tables (file restored from `campus_customs.db`) | **No agent.** Only the reset route (and `run.py tickets`) | n/a | Restores the original values before a full run |

`BACKEND_ONLY_TOOLS` = `pay`, `reset_db`, `record_restock_order`. `models.py` refuses to load if any agent is given one.

---

## Backend Routes

FastAPI app in `backend/main.py`, served at `http://127.0.0.1:8000`. Every route reaches the database only through the MCP tools above.

| Method | URL | What it does |
|---|---|---|
| GET | `/api/tickets` | All three tickets with their status, and `resolved: true` only when the status is `resolved` (MCP `list_tickets`) |
| POST | `/api/tickets/{ticket_id}/run` | Starts the team on one ticket in the background (202). If the ticket was run before, the run continues from the previous run's findings. 409 if a run is going or the ticket is resolved; 404 if the ticket doesn't exist. |
| GET | `/api/events?since=&limit=&run_id=` | Recent audit-trail events (agent messages, tools, drafts, approvals) plus `last_seq` for the next refresh |
| GET | `/api/payments?status=` | The sign-off queue: drafted payments and purchases with status `awaiting_human_approval`, `paid`, or `refused`, plus a live `blocked_reason` |
| POST | `/api/payments/{request_id}/approve` | A human approves one draft with `{"approved_by": "<name>"}`. The **only** route that moves money (MCP `pay`). After a ticket's last approval it **re-runs the team automatically** (or queues the re-run). 400 for a blank or agent name; 409 if refused, or blocked (stays pending). |
| GET | `/api/cash` | Checking balance from `cash_accounts`, plus the total awaiting approval (MCP `check_cash`) |
| POST | `/api/reset` | Restores the clean database (MCP `reset_db`) and clears the queue. 409 during a run. |
| GET | `/api/health` | Model, whether the Portkey key is set, MCP tools, active run |

After every run, approval, and reset, the backend also refreshes `output/desk_tickets.html` (Actual sections and Cash tab). At startup it backfills any old purchase's order record.

---

## The Dashboard

React + Vite + TypeScript in `frontend/` (`run-frontend.cmd`, http://127.0.0.1:5173). It talks only to the FastAPI backend at `http://localhost:8000`. Full design notes are in `output/design.md`.

| Area | What it shows / does |
|---|---|
| **Sidebar** | The **checking widget**: balance, a cash meter (paid / awaiting sign-off / left after approval), and a count-down when money leaves. The **ticket list** with status tags (○ Open, ⟳ In progress, ⛔ Blocked, ✋ Awaiting sign-off, ✓ Resolved). A resolved customer ticket gets a second, separate tag: ✉ Email sent · awaiting response. Payment history. |
| **Ticket workspace** | An outcome card (plain-language result, money paid, email drafted), the ticket and its **Run agent team** button (explains itself when disabled), the next step, and "Read the latest customer draft". The status chip (✓ Resolved) and the note "✉ Email sent to customer · awaiting response" are shown as two separate parts. |
| **Sign-off banner** | Pops up when Accounting drafts something. Shows an action card per draft (vendor, amount, reason, balance before → after, blocked warning) with **Approve Payment / Approve Purchase** and a confirm step. The approver name is saved. |
| **Live activity** | One plain sentence per step, led by the agent's colored name. Raw data is folded under **View data**. Auto-scroll toggle. |
| **Crew & hand-offs** | A delegation flowchart (live hand-offs glow) plus one card per agent: summary, tools, drafts, rule checks, the customer draft |
| **Draft popup** | When a run finishes with a customer email, the draft opens in a dialog you close with ✕ or Esc |

Agent colors: Boss amber, Inventory blue, Accounting green, Facilities purple, Customer Service coral. Each also has a glyph and badge shape, so color is never the only cue.

The dashboard polls `/api/events` every 1.2s during a run and every 4s when idle, and rebuilds run history from the audit trail since the last reset.

**Static reports in `output/`:**
- `desk_tickets.html`: expected vs actual per ticket, plus the Cash tab. It refreshes itself.
- `resolved_board.html` and `resolved_tickets.json`: the final record, with screenshots. Regenerate with `backend/export_resolved.py`.
- `design.md`: the dashboard design.

---

## Safety Rules

### Money
- **Agents only draft.** Accounting's money tools are `draft_payment` and `draft_purchase`, and both write nothing. Each verified draft goes to the sign-off queue (`backend/payments.py` → `output/payment_requests.json`), with one pending request per bill.
- **One route moves money: `POST /api/payments/{id}/approve`.** A human enters their name. Blank or agent names are rejected.
- **`pay` re-checks everything on the server.** It refuses:
  - an agent approver
  - an amount that doesn't match the database, so ticket text can't set the amount
  - an invoice that isn't `open`, or rent that's already paid (no double-paying)
  - an unknown account
  - an overdraft
- **Vendor rule at approval time:** a purchase is blocked while its vendor has an open unpaid invoice, and the request stays pending until that invoice is paid.
- **Every write is one transaction.** A purchase also records a paid "Restock order" invoice, so the order can be verified.
- **No agent can pay, reset, or backfill.** `BACKEND_ONLY_TOOLS` is enforced when the code loads.
- **Validators reject unsafe agent output:**
  - a `PaymentOrder` with `cash_after` < 0
  - pending orders that together exceed cash
  - a price below unit cost
  - a ticket marked `resolved` with a failed constraint or a pending payment
- **Dates and amounts come from the database.** `desk.date_today` is "today". Lead times come from `vendors`, rent from `leases`, arrival dates from paid restock orders. Ticket notes are claims to verify, not facts.

### Customer replies
- **Nothing is ever sent.** No agent has an email tool, and the Outlook server isn't connected to the team. `CustomerDraft.sent` is fixed to `False`.
- **One email per ticket, written last, after the money is settled.**
  - Only the Boss can hand off to Customer Service. A hand-off from any specialist is refused, so the Boss, who has the full picture, makes the call.
  - The desk checks the database before that hand-off (`customer_reply_gate`). It refuses while the ticket's linked invoice is unpaid, or while the ticket is short on stock with no restock on order and cash covers at least one unit. The refusal says what Accounting still has to draft.
  - A second hand-off to Customer Service in a run is refused.
  - So is any hand-off while a payment or purchase drafted in that run awaits sign-off.
  - An early or extra draft is withheld (`customer_draft_withheld`).
  - The schema rejects two drafts for one ticket.
  - The email comes on the automatic re-run after approval, when the real outcome is known.
- **Wording rules:** the email never mentions approval, payments, orders, or vendors. It gives the arrival date only from a verified order and with no caveats, recommends in-stock alternatives, and keeps internal matters internal.

### Token use and loops

| Guardrail | Limit | Where |
|---|---|---|
| No self-delegation; no delegating back to anyone waiting in the chain | refused | `delegate` checks `TeamDeps.chain` |
| Max chain depth | 4 agents (e.g. Boss → Accounting → Customer Service → Inventory) | `MAX_DEPTH` |
| Max hand-offs per run | 15 | `MAX_DELEGATIONS` |
| Whole-run token budget | 1,500,000 tokens; delegation stops once spent | `RUN_TOKEN_BUDGET` |
| Boss per run | 30 model requests, 40 tool calls, 500k tokens | `LIMITS` (PydanticAI `UsageLimits`) |
| Each specialist per run | 15 model requests, 20 tool calls, 200k tokens | `LIMITS` |
| Output validation retries | 3 per agent | `Agent(retries=3)` |
| Tool errors | returned as a final failure (no retry prompt), bounded by `tool_calls_limit` | `MCPToolset(tool_error_behavior="failed")` |
| Re-runs continue, not restart | previous run's reports pre-loaded on the board, plus a "where we left off" summary | `prior_context` in `main.py` |
| One run at a time | a second run, or a reset during a run, gets HTTP 409; automatic re-runs queue | `backend/main.py` |
| Duplicate drafts | one pending request per bill | `PaymentQueue.add_draft` |
| Customer replies | one per ticket, written last: only the Boss may ask; refused while this run's drafts await sign-off, or while the database shows an unpaid invoice or an affordable restock not yet ordered | `delegate`, `ShopSession.customer_reply_block`, `customer_reply_gate` |

### Audit trail
- Every step is appended to `output/audit_trail.json` (`backend/audit.py`):
  - run start and finish
  - each agent's start and output (with a short `summary`)
  - every tool call with its arguments and result or error
  - every delegation (started, done, refused, error)
  - every payment draft
  - every human approval, block, or refusal
  - every automatic re-run (queued, started)
  - every withheld customer draft, and every refused hand-off to Customer Service with the reason
  - every time the desk declines to resolve a ticket (`ticket_not_finalized`, with the reason)
  - every database reset
- **Each run also ends with a `run_summary` entry:** ticket, trigger (you or automatic after approval), agents that ran, hand-offs, tool counts, payment drafts, the customer email, the final status and note, and tokens. Runs from before this feature were backfilled with `backfilled: true`.
- The file is a JSON array that only grows. Each write appends one entry with the next `seq` and atomically replaces the file. Nothing is removed between runs, and every entry carries a `run_id`.
- **Windows and OneDrive file locks.** The `output/` folder sits in OneDrive, which briefly locks files while it syncs them. Writes to the audit trail, the payment queue, and `desk_tickets.html` go through `backend/safe_write.py`: it retries the atomic replace for about 5 seconds and, if the lock still holds, overwrites the file in place instead of failing the run. Readers retry too. (One early run on ticket 103 crashed this way before the fix; it is in the log as `run_error`, before the final reset.)
- **Fields are capped at 4,000 characters** so entries stay readable; longer values are cut and marked `…[truncated]`.

### Runs in the audit trail (final pass)

After the last reset (entry 1444) the three tickets took **6 runs**. Each has its own `run_started` … `run_finished` and a `run_summary`. A `run_record` entry per run (entries 1615–1620) and a `runs_rollup_index` (entry 1621) list them together.

| Run | Ticket | Started by | Agents that ran | Money drafted | Customer email | Status after the run |
|---|---|---|---|---|---|---|
| 1 | 101 | You | Boss, Inventory, Accounting | $840 invoice 501 | — | Awaiting approval |
| 2 | 101 | Automatic, after you approved $840 | Boss, Accounting | $8 restock (1 tee) | — | Awaiting approval |
| 3 | 101 | Automatic, after you approved $8 | Boss, Customer Service, Inventory | — | "Re: Bulldog tee" | **Resolved**, email sent · awaiting response |
| 4 | 102 | You | Boss, Facilities, Accounting | $2,400 rent | — | **Resolved** |
| 5 | 103 | You | Boss, Accounting, Inventory | $132 partial restock (6 hoodies) | — | Awaiting approval |
| 6 | 103 | Automatic, after you approved $132 | Boss, Customer Service | — | "Your bulk hoodie request" | **Resolved**, email sent · awaiting response |

Four human approvals (all by Ayush Rajpal) took checking from **$3,400.00 to $20.00**, which matches `cash_accounts` exactly. Each customer got one email, in the ticket's last run.
