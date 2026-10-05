"""Command-line runner for the Campus Customs agent team (the API in main.py is the main entry).

Run from Homework 5/backend with the hw5 venv:

  C:\\venvs\\hw5\\Scripts\\python.exe run.py tickets
      Full run: reset the working DB (through the MCP reset_db tool), then the Boss reads
      the open tickets with list_tickets and resolves them. Saves output/team_run.json.

  C:\\venvs\\hw5\\Scripts\\python.exe run.py ask <agent> "<task>"
      Start at any agent (boss, inventory, accounting, facilities, customer_service).
      Saves output/ask_<agent>.json.

Payments: agents only draft them. Drafts land in the same approval queue the API uses
(output/payment_requests.json); approve them with POST /api/payments/{id}/approve.
Every step lands in output/audit_trail.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import MODEL_NAME, PROJECT_ROOT
from models import AGENT_IDS
from payments import PaymentQueue
from team import ShopSession, run_team

OUTPUT_DIR = PROJECT_ROOT / "output"


def save(path: Path, task: str, entry: str, output, session: ShopSession) -> None:
    payload = {
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run_id": session.run_id,
        "model": MODEL_NAME,
        "entry_agent": entry,
        "task": task,
        "tokens_used": session.tokens_used,
        "output": output.model_dump(mode="json"),
        "payment_drafts": session.drafts,
        "delegations": [d.model_dump(mode="json") for d in session.delegations],
        "board": session.board,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Campus Customs agent team")
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("tickets", help="reset the DB and resolve all open tickets")
    ask = sub.add_parser("ask", help="give one agent a task")
    ask.add_argument("agent", choices=AGENT_IDS)
    ask.add_argument("task")
    args = parser.parse_args()

    queue = PaymentQueue()

    def on_draft(draft: dict[str, Any], agent: str, run_id: str) -> str:
        req, created = queue.add_draft(draft, agent, run_id)
        state = "queued" if created else "already queued"
        return f"{state} for human approval as payment request #{req.id}"

    if args.mode == "tickets":
        queue.clear()  # the reset restores every bill, so old requests no longer apply
        task = (
            "Read the open tickets with list_tickets, work through every one, and make the final "
            "call on each. Agents only draft payments; a human approves them afterwards."
        )
        entry, path = "boss", OUTPUT_DIR / "team_run.json"
        output, session = await run_team(task, on_draft=on_draft, reset=True)
    else:
        task, entry = args.task, args.agent
        path = OUTPUT_DIR / f"ask_{entry}.json"
        output, session = await run_team(task, entry=entry, on_draft=on_draft)

    save(path, task, entry, output, session)
    print(output.model_dump_json(indent=2))
    print(f"\nRun {session.run_id}: {len(session.delegations)} delegations, "
          f"{len(session.drafts)} payment drafts, {session.tokens_used:,} tokens")
    for d in session.delegations:
        print(f"  [{d.status}] {d.from_agent} -> {d.to_agent} (depth {d.depth}): {d.task[:100]}")
    print(f"Saved {path.relative_to(PROJECT_ROOT)}; steps appended to output/audit_trail.json")


if __name__ == "__main__":
    asyncio.run(main())
