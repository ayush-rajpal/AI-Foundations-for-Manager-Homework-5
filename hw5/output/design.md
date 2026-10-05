# Campus Customs Operations Desk: Design Choices

The dashboard (`frontend/`, React + Vite + TypeScript) is where a human operator supervises the five-agent team. It talks only to the FastAPI backend at `http://localhost:8000`.

## Overall desk layout

It's a sleek, dark **operations console** with a **two-column master–detail layout** that fits on one desktop screen (checked at 1440×900 with no page scrolling):

| Area | Where | What it holds |
|---|---|---|
| **Header** (dark navy) | Top, slim | Shop name, one-line purpose, **Reset desk** |
| **Sidebar (master)** | Left, 330px | The **checking-account widget** (balance plus cash meter), the **ticket list** with status tags, and a collapsible payment history |
| **Workspace (detail)** | Right | The selected ticket: outcome summary, ticket header with the **Run agent team** button, and the next step. Below that, the **sign-off banner** whenever a payment or purchase needs approval. At the bottom, **Live activity** and **Crew & hand-offs** side by side. |

**Why this layout:**
- Master–detail matches how the operator works: glance at the sidebar (how much cash is there, which ticket needs me), pick a ticket, and everything about it is on the right.
- Live activity and the crew sit **side by side** and fill the rest of the screen. You watch what's happening and who is doing it at the same time.
  - Each panel scrolls inside itself, so the page never jumps.
  - Nothing about the current ticket is below the fold.
- The **sign-off banner** appears inside the workspace, right above the activity, when Accounting drafts something. Human approval is impossible to miss, and when nothing is pending it takes no space.
- Below 1150px wide, the layout stacks into one column in working order.

## Visual style

- **Palette:** a deep slate background `#0f172a` that matches the navy header, with crisp elevated cards (`#162033`), clean 1px border lines (`#2b3a55`), and soft shadows. No browns or beige.
- **Type:** light text on slate (`#e5eaf2`, muted `#9aa8bd`), both at least 4.5:1. Money uses tabular monospace digits.

## How each agent is styled differently

Each agent has one accent color, used for its badge, its colored name and left edge in every activity message, its "View data" link, its flowchart node and arrows, and its crew card (top edge, name, tool chips). A glyph and badge shape give a second cue that doesn't rely on color, and the name is always written out.

| Agent | Accent | Glyph | Badge shape |
|---|---|---|---|
| Boss | **amber** `#fbbf24` | ♛ crown | square |
| Inventory | **blue** `#60a5fa` | ▦ crate grid | circle |
| Accounting | **green** `#34d399` | $ | hexagon |
| Facilities | **purple** `#c084fc` | ⌂ house | house outline |
| Customer Service | **coral** `#fb7185` | ✉ envelope | speech bubble |

The accents are bright on the dark background (well above 4.5:1). Each badge uses the accent as its fill with near-black text.

## How ticket status is displayed

- **Ticket list tags:** each ticket card has a status tag with an icon and a word:
  - ○ Open
  - ⟳ In progress / Agents working (spinning, blue)
  - ⛔ Blocked (red)
  - ✋ Awaiting sign-off (solid yellow)
  - ✓ Resolved (solid green)

  A matching colored left edge makes the list scannable. Tickets with money to approve also show "✋ $X to sign".
- **Outcome summary card:** after a run, a card at the top of the workspace explains the result in plain language (the note the Boss saved with `update_ticket`). It also lists the money paid for that ticket and who approved it, what still waits for sign-off, and whether a customer reply was drafted. Its color follows the status (green Resolved, yellow Awaiting sign-off, red Blocked, blue In progress).
- **Resolved, with or without an email:** when a run ends with nothing waiting on your sign-off, the desk marks the ticket Resolved. If Customer Service drafted the reply, the ticket list adds an "✉ Email sent · awaiting response" tag, and the ticket view reads "Resolved — email sent to customer — awaiting response".
- **Statuses come from the database, never the browser.** A ticket only shows Resolved when the Boss recorded it that way.
- **Auto re-run:** after you approve a ticket's last pending request, the backend re-runs the team on that ticket by itself, and the dashboard switches to it so you can watch the Boss close it.
- **One customer email per ticket, shown as a pop-up:** only the Boss asks Customer Service, and only at the end, once the invoice is paid and any affordable restock is on order. So the ticket gets a single reply, written last. For example, after you approve the $8 restock, the re-run drafts the one email with the arrival date. When a run finishes with that draft, it pops up in a dialog you close with ✕ or Esc, and **Read the latest customer draft** reopens it anytime.

## How the cash balance updates are displayed

- The balance is the largest number in the sidebar widget.
- Under it, a **cash meter** spans the session's starting cash ($3,400), split into:
  - **gray:** paid out
  - **amber:** drafted and awaiting sign-off (**red** if the drafts would overdraw)
  - **green:** what's left after approval

  A legend gives each amount, and screen readers get one full sentence.
- On approval:
  - The balance counts down to the new value.
  - A red "▼ $840.00 paid out just now" chip appears, and the meter segments slide.
  - Screen readers hear the new balance.
  - With reduced motion turned on, it changes instantly.

## Creative decisions that make it intuitive and practical

- **Readable live feed:** each line is one sentence led by the agent's colored name ("**Boss** ran list_tickets", "**Accounting** drafted a $840.00 payment…").
  - Raw JSON tool inputs and outputs are folded into a **View data** dropdown with a code panel.
  - An **Auto-scroll** toggle follows new lines, or holds your place while you read earlier ones.
- **Delegation flowchart:** at the top of the crew panel, the Boss sits above the four specialists.
  - Each hand-off draws an arrow in the delegating agent's color.
  - Live hand-offs glow with flowing dashes, and agents working right now pulse.
  - A numbered hand-off list gives the same story as text.
- **Approval action cards** in the pulsing amber sign-off banner. Each card shows:
  - the vendor and the exact amount in large type
  - the reason, and the balance before → after
  - a full-width **Approve Payment / Approve Purchase** button with a confirm step
  - a note that the ticket will re-run automatically

  The approver name sits in the banner header and is saved for next time.
- **Guard rails stay visible:** the Run button explains itself when disabled, Reset is locked during a run and asks for confirmation, and there's no desk-date badge in the header (the date appears quietly as "as of 2026-08-31" on the cash widget).

## Accessibility (WCAG 2.2 AA)

- **Structure:** landmarks (header, an `aside` sidebar, `main` workspace), a skip link to the workspace, and headings for every panel.
- **Keyboard:** everything works by keyboard, with a visible amber focus ring. The ticket list uses native radio buttons. Panels that scroll can be focused.
- **Not color alone:** status, agent identity, and money states always come with a word and an icon.
- **Text alternatives:** the flowchart SVG is decorative, and its numbered list carries the same information. The meter has a full text label.
- **Announcements:** a polite live region reads one short line per update during a run, plus balance changes. Errors use `role="alert"`.
- **Motion:** `prefers-reduced-motion` turns off all animation.

## How it stays live

- On load, the page fetches the tickets, cash, payments, and the audit trail.
- It then asks for new events every 1.2s during a run and every 4s when idle.
- It refreshes tickets, payments, and cash when a run finishes, when something is drafted, after approvals (including the automatic re-run), and after a reset.
