# Campus Customs Operations Desk: dashboard

React 19 + Vite + TypeScript. The dashboard shows the five-agent team working each ticket live, and it's where a human approves every payment. It talks only to the FastAPI backend; it never touches the database or the MCP server.

## Run it

Start the backend first (see `../README.md`), then from this folder:

```bash
npm install
npm run dev
```

Open http://127.0.0.1:5173. On Windows you can also double-click `../run-frontend.cmd` after `npm install`.

| Command | What it does |
|---|---|
| `npm run dev` | Dev server on http://127.0.0.1:5173 (`vite.config.ts`) |
| `npm run build` | Type-check and build to `dist/` |
| `npm run lint` | Lint with oxlint |
| `npm run preview` | Serve the built `dist/` |

The backend address defaults to `http://localhost:8000`. To point somewhere else, set `VITE_API_URL` (for example in a `.env.local` file here) before `npm run dev`.

## Code map

| File | What it does |
|---|---|
| `src/App.tsx` | Page layout: sidebar, ticket workspace, sign-off banner, live activity, crew panel, draft popup |
| `src/useDesk.ts` | Polls the backend (`/api/events` every 1.2 s during a run, 4 s when idle) and holds the desk state |
| `src/api.ts` | Typed calls to the backend routes: tickets, run, events, payments, approve, cash, reset |
| `src/derive.ts` | Turns audit-trail events into runs, agent summaries, hand-offs, and the activity feed |
| `src/agents.ts` | The five agents' names, colors, glyphs, and roles |
| `src/types.ts`, `src/format.ts` | Shared types and money/time formatting |
| `src/index.css` | The dark slate theme |
| `src/components/TicketList.tsx` | Ticket list with status tags and the separate "Email sent · awaiting response" tag |
| `src/components/TicketDetail.tsx` | Ticket workspace: outcome card, **Run agent team**, next step, latest customer draft |
| `src/components/ApprovalQueue.tsx` | Sign-off banner (approve a payment or purchase with your name) and payment history |
| `src/components/CashLedger.tsx` | Checking balance widget and cash meter |
| `src/components/ActivityFeed.tsx` | Live activity: one plain sentence per step, raw data under **View data** |
| `src/components/DelegationFlow.tsx`, `AgentCrew.tsx` | Hand-off flowchart and one card per agent |
| `src/components/DraftDialog.tsx`, `ResetDialog.tsx` | Customer-draft popup and the Reset desk confirmation |

Design choices are documented in `../output/design.md`.
