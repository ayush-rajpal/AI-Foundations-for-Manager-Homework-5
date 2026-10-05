# Campus Customs Multi-Agent Operations Desk (Homework 5)

A five-agent AI team (Boss, Inventory, Accounting, Facilities, Customer Service) that works the shop's tickets. A human approves every dollar from a React dashboard. All database access goes through one MCP server.

| Folder / file | What it is |
|---|---|
| `data/campus_customs.db` | Original database (never modified; **Reset desk** restores from it) |
| `data/campus_customs_new.db` | Working copy the agents use (the state after the final run: all three tickets resolved, $20.00 in checking) |
| `mcp_server/` | FastMCP server: the only path to the database. 14 tools, see `mcp_server/README.md` |
| `backend/` | PydanticAI agent team (`team.py`, `prompts/`, `models.py`) and the FastAPI routes (`main.py`) |
| `frontend/` | React + Vite + TypeScript operations dashboard |
| `output/harness.md` | Full documentation: tables, MCP tools, the five agents, API routes, dashboard, safety rules, and the runs |
| `output/desk_tickets.html` | Expected vs. actual delegation per ticket, the Cash tab, and the Reflection tab |
| `output/resolved_board.html`, `output/resolved_tickets.json` | Final record of the three tickets, with dashboard screenshots (`output/screenshots/`) |
| `output/audit_trail.json` | Append-only log of every agent step, tool call, approval, and run summary |
| `output/payment_requests.json` | The human sign-off queue (every drafted payment and purchase, and who approved it) |
| `output/design.md` | Dashboard design choices |
| `output/github_url.txt` | Link to this repository |
| `AI_prompts.md` | Every prompt used to build the project, by problem |
| `requirements.txt` | Python packages for the backend and the MCP server |
| `.env.example` | Template for your own `.env` (the real one is not in this repo) |
| `.mcp.json` | Optional: lets an MCP client such as Claude Code use the shop's MCP server directly |

## What you need

- **Python 3.12 or newer** (built and tested on 3.14)
- **Node.js 20 or newer** (built and tested on Node 24)
- A **Portkey API key** that can reach the `gpt-6-luna` model (only needed to run the agents; the dashboard, tickets, and cash views load without it)

## Run it

Run every command from this `hw5/` folder (`cd hw5` after cloning).

### 1. Python environment

Windows:
```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

macOS / Linux:
```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

### 2. Your API key

Copy `.env.example` to `.env` in this `hw5/` folder and set `PORTKEY_API_KEY`.

### 3. Backend (FastAPI + agents + MCP server), port 8000

Windows: double-click `run-backend.cmd`, or:
```bash
.venv\Scripts\python.exe -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000
```

macOS / Linux:
```bash
.venv/bin/python -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000
```

The backend starts the MCP server (`mcp_server/server.py`) itself, using the same Python. Check it at http://127.0.0.1:8000/api/health: it lists the 14 MCP tools and whether your key is set.

### 4. Dashboard, port 5173

```bash
cd frontend
npm install
npm run dev
```

On Windows you can double-click `run-frontend.cmd` after `npm install`. Then open http://127.0.0.1:5173.

## Using the desk

1. Press **Reset desk**. It restores the clean database ($3,400.00 in checking, all tickets open) and clears the sign-off queue.
2. Run the tickets in order: **101, then 102, then 103**. Ticket 103's restock depends on 101's vendor invoice and 102's rent being paid first.
3. Approve each payment or purchase when its sign-off card pops up. Type your name to approve. After a ticket's last approval, the team re-runs on its own and finishes the ticket. Customer emails are drafts that pop up on screen; nothing is ever sent.

`output/desk_tickets.html` updates itself after every run, approval, and reset. To rebuild the resolved board, run `python backend/export_resolved.py` (with your venv's Python) while the backend is running.

## Safety in one line

Agents can only draft money moves. The single approve route is the only place cash changes, and the balance can never go below $0. No email is ever sent. Every step lands in the append-only audit trail. Details are in `output/harness.md`.
