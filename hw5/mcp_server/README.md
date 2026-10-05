# Campus Customs MCP Server

## What it is for
This MCP server is the shared tool layer for the **Campus Customs Multi-Agent Operations team**, the AI agents that run the shop. It is the **only** path to the database. No agent and no part of the backend opens the database directly. Every read and write goes through these tools, so all agents see the same data and the same rules are enforced in one place.

The server is built with **FastMCP** and runs over stdio.

## Database
- **File:** `data/campus_customs_new.db`, a working copy of the original `data/campus_customs.db`.
- The original database is never written to. It's the clean copy that `reset_db` restores from before a full run.
- Read tools open the database read-only. Write tools run inside a single transaction, so a refused or failed write changes nothing.
- Tools return only values stored in the database. They add only simple math: days overdue, days until due, margins.
- "Today" for the shop is `desk.date_today` (2026-08-31), not the real-world date. `pay` stamps payments with this date.
- **Agents can't move money.** They hold `draft_payment` and `draft_purchase`, which write nothing. `pay` and `reset_db` are backend-only: the FastAPI routes in `backend/main.py` are the only callers.

## Tools

### Read tools

| Tool | Inputs | Tables read | What it returns | Tickets |
|---|---|---|---|---|
| `list_tickets` | optional `status` (default `open`) | `tickets`, `desk` | Every ticket with that status, oldest first, plus today's date | All (the Boss's work queue) |
| `check_stock` | `sku`, optional `size` | `inventory`, `pricing`, `invoices` | Product name; units in stock and aisle for each size; unit cost; list price; `incoming` restock orders (paid, with quantity and expected arrival) | 101, 103 |
| `check_invoice` | `invoice_id` | `invoices`, `vendors`, `desk`, `cash_accounts` | Invoice amount, due date, status, and description; the vendor's name, specialty, and lead days; days overdue; cash balance | 101 |
| `check_rent` | `lease_id` | `leases`, `desk`, `cash_accounts` | Shop space, landlord, monthly rent, and next due date; days until due; cash balance | 102 |
| `check_vendor` | optional `vendor_id` | `vendors`, `invoices`, `desk` | Each vendor's specialty and lead days, its open invoices, `can_ship` (false while an invoice is open), and the arrival date if ordered today | 101, 103 |
| `check_cash` | none | `cash_accounts`, `desk`, `invoices`, `leases`, `payments` | Balances; every open bill with days overdue; rent with days until due; total owed in the next 31 days; cash left if everything were paid; payments already made | 101, 102 |
| `find_alternatives` | `sku`, `size` | `inventory`, `pricing` | In-stock products in the same size: same product type first, then same category (from SKU naming: apparel = TEE/HOOD, accessories = HAT, drinkware = MUG), with stock and list price | 101, 103 |
| `check_discount` | `sku`, `qty`, `unit_price` | `pricing` | Discount %, margin per unit and in total, `below_cost`, and the deepest discount that still covers unit cost | 103 |
| `draft_payment` | `kind` (`invoice`/`rent`), `ref_id`, optional `account` (default `checking`) | `invoices`, `vendors`, `leases`, `cash_accounts`, `desk` | A verified draft: payee and amount from the database, balance before and after, status `awaiting_human_approval`. Refuses if the invoice isn't open, rent isn't due within 31 days, or the balance would go negative. **Changes nothing.** | 101, 102 |
| `draft_purchase` | `sku`, `size`, `qty`, `vendor_id`, optional `account` | `inventory`, `pricing`, `vendors`, `invoices`, `cash_accounts`, `desk` | A verified restock draft: qty × `unit_cost`, vendor, lead days, arrival date if paid today, `vendor_can_ship` and any blocking open invoices, balance before and after. Refuses if the SKU/size or vendor doesn't exist or the balance would go negative. **Changes nothing.** | 103 |

### Write tools

| Tool | Inputs | Tables read | Tables written | What it does | Refuses when |
|---|---|---|---|---|---|
| `pay` **(backend only)** | `kind` (`invoice`/`rent`/`purchase`), `ref_id` (invoice, lease, or vendor id), `amount`, `account`, `approved_by`, plus `sku`/`size`/`qty` for purchases | `desk`, `cash_accounts`, `invoices`, `vendors`, `leases`, `inventory`, `pricing` | `payments` (new row), `cash_accounts` (balance down), `invoices` (status → `paid`) or `leases` (`next_due` + 1 month); a purchase also inserts a **paid vendor invoice** "Restock order: <qty> x <sku> <size> (<name>) at <cost> each; expected <date>" so the order is verifiable (stock itself arrives after `lead_days`) | Pays one invoice, one month's rent, or one restock purchase | `approved_by` is empty or names an agent; invoice not `open`; rent not due within 31 days (already paid); `amount` ≠ the amount on record; unknown account; balance would go below zero; **Blocked:** a purchase whose vendor still has an open unpaid invoice |
| `update_ticket` | `ticket_id`, `status`, `note`, `updated_by` | `tickets`, `desk`, `invoices` | `tickets` (status, notes) | Sets the status (`open`, `in_progress`, `blocked`, `awaiting_approval`, `resolved`) and appends a dated note. The requester's original note is kept. | Unknown status or empty note; resolving a ticket whose linked invoice is still open |

### Backend-only admin tools

| Tool | Inputs | Tables read | Tables written | What it does |
|---|---|---|---|---|
| `reset_db` | none | `desk`, `tickets`, `cash_accounts` (to report the fresh state) | **All tables**: the whole file is replaced with `data/campus_customs.db` | Restores the working copy before a full run. **Not given to any agent.** Called by `POST /api/reset` (and `backend/run.py tickets`). |
| `record_restock_order` | `payment_id`, `sku`, `size`, `qty` | `payments`, `vendors`, `inventory`, `pricing` | `invoices` (paid "Restock order" row), `payments` (ref_id points at it) | Backfills the order record for a purchase paid before orders were recorded; does nothing if already recorded. **Not given to any agent.** Called once at backend startup. |

If an ID or SKU doesn't exist, the tool returns an error instead of guessing.

## Human approval for payments
1. Accounting calls `draft_payment` or `draft_purchase`. The backend puts the verified draft in its approval queue (`output/payment_requests.json`). Nothing in the database changes.
2. A human approves it with `POST /api/payments/{id}/approve` and their name. This is the only route that calls `pay`.
3. `pay` re-checks the amount, the bill, the balance, and that the approver isn't an agent. A purchase is blocked while its vendor has an open invoice; the request stays pending until that invoice is paid. Then, in one transaction, `pay` adds a `payments` row, lowers `cash_accounts`, and marks the invoice `paid` or moves the lease's `next_due`.
4. Every draft, approval, and refusal is appended to `output/audit_trail.json`.

## Which agent can call which tool

| Agent | Tools |
|---|---|
| Boss | `list_tickets`, `update_ticket`, `check_stock`, `check_invoice`, `check_rent`, `check_vendor`, `check_cash` |
| Inventory | `list_tickets`, `check_stock`, `check_vendor`, `check_invoice`, `find_alternatives` |
| Accounting | `list_tickets`, `check_cash`, `check_invoice`, `check_rent`, `check_stock`, `check_discount`, `draft_payment`, `draft_purchase` |
| Facilities | `list_tickets`, `check_rent` |
| Customer Service | `list_tickets`, `check_stock` |

`pay`, `reset_db` and `record_restock_order` are assigned to no agent (`BACKEND_ONLY_TOOLS`); `models.py` refuses to load if one is. The map lives in `backend/models.py` (`AGENT_TOOLS`).

## Setup and run
The venv lives outside OneDrive, because Windows path limits break pip inside the course folder:

```bash
python -m venv C:\venvs\hw5
C:\venvs\hw5\Scripts\python.exe -m pip install -r requirements.txt
```

Start the server from the `Homework 5` folder (`hw5/` in the GitHub repo):

```bash
C:\venvs\hw5\Scripts\python.exe mcp_server\server.py
```

To test against a scratch copy, set `CAMPUS_CUSTOMS_DB` to another database file. The server then reads and writes that file instead.

Tested with FastMCP 4.0.10 on Python 3.14.
