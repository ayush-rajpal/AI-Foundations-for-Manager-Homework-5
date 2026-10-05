"""Append-only audit trail at output/audit_trail.json.

Every agent action (tool call and its result), every delegation, every payment
draft, every human approval from the API, and every run start/finish is appended
as one entry. The file
is a JSON array that only ever grows: each write reads the existing entries, adds
the new one, and atomically replaces the file (retrying while OneDrive holds a lock). Nothing is removed between runs.
If the file can't be parsed, it is set aside (never deleted) and a new one starts.

AuditedToolset wraps an agent's toolsets so every tool call is logged without
each tool having to remember to do it. read_entries() serves the API's events route.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.toolsets import WrapperToolset
from pydantic_ai.toolsets.abstract import ToolsetTool

from config import PROJECT_ROOT
from safe_write import atomic_write_text

# CAMPUS_CUSTOMS_AUDIT (tests only) sends entries to a scratch file instead.
AUDIT_PATH = Path(os.getenv("CAMPUS_CUSTOMS_AUDIT", PROJECT_ROOT / "output" / "audit_trail.json"))
MAX_TEXT = 4_000
UNLOGGED_TOOLS = {"delegate"}  # delegate writes its own, richer delegation entries

_lock = threading.Lock()


def _clip(value: Any) -> Any:
    """Keep entries readable: long strings are cut, structures are kept as JSON."""
    if isinstance(value, str):
        return value if len(value) <= MAX_TEXT else value[:MAX_TEXT] + " …[truncated]"
    try:
        text = json.dumps(value, default=str)
    except TypeError:
        return _clip(str(value))
    return value if len(text) <= MAX_TEXT else text[:MAX_TEXT] + " …[truncated]"


def _read(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    data = None
    for attempt in range(20):  # OneDrive can briefly lock the file or catch it mid-write
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            break
        except (PermissionError, json.JSONDecodeError):
            time.sleep(0.05 * (attempt + 1))
    if isinstance(data, list):
        return data
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path.rename(path.with_name(f"{path.stem}.unreadable-{stamp}.json"))  # keep it, start fresh
    return []


def read_entries(since: int = 0, limit: int = 200, run_id: str | None = None) -> tuple[list[dict[str, Any]], int]:
    """Entries with seq > since (optionally one run), newest `limit` of them, plus the latest seq."""
    with _lock:
        entries = _read(AUDIT_PATH)
    last_seq = entries[-1]["seq"] if entries else 0
    picked = [e for e in entries if e.get("seq", 0) > since and (run_id is None or e.get("run_id") == run_id)]
    return picked[-limit:], last_seq


def summarize_run(entries: list[dict[str, Any]], run_id: str) -> dict[str, Any]:
    """One record for a whole run: ticket, trigger, agents, hand-offs, tools, drafts, email, outcome."""
    evs = [e for e in entries if e.get("run_id") == run_id]
    start = next((e for e in evs if e.get("event") == "run_started"), {})
    finish = next((e for e in evs if e.get("event") in ("run_finished", "run_error")), {})
    agents: list[str] = []
    tools: dict[str, int] = {}
    handoffs = []
    for e in evs:
        if e.get("event") == "agent_started" and e["agent"] not in agents:
            agents.append(e["agent"])
        elif e.get("event") == "tool_call" and e.get("tool") != "read_board":
            tools[e["tool"]] = tools.get(e["tool"], 0) + 1
        elif e.get("event") == "delegation_started":
            handoffs.append({"from": e["agent"], "to": e.get("to_agent"), "status": "started"})
        elif e.get("event") in ("delegation_done", "delegation_error", "delegation_refused"):
            status = {"delegation_done": "done", "delegation_error": "error", "delegation_refused": "refused"}[e["event"]]
            open_ = next((h for h in handoffs if h["from"] == e["agent"] and h["to"] == e.get("to_agent") and h["status"] == "started"), None)
            if open_ and status != "refused":
                open_["status"] = status
            else:
                handoffs.append({"from": e["agent"], "to": e.get("to_agent"), "status": status})
    drafts = [
        {k: (e.get("draft") or {}).get(k) for k in ("kind", "amount", "payee", "description")}
        for e in evs if e.get("event") == "payment_drafted"
    ]
    emails = [d for e in evs if e.get("event") == "agent_output" and e.get("agent") == "customer_service" for d in (e.get("drafts") or [])]
    updates = [e.get("args") or {} for e in evs if e.get("event") == "tool_call" and e.get("tool") == "update_ticket"]
    return {
        "summarized_run_id": run_id,
        "ticket_id": start.get("ticket_id"),
        "trigger": start.get("trigger"),
        "started_at": start.get("ts"),
        "finished_at": finish.get("ts"),
        "outcome": "error" if finish.get("event") == "run_error" else ("finished" if finish else "unfinished"),
        "agents_ran": agents,
        "handoffs": handoffs,
        "tools": tools,
        "payment_drafts": drafts,
        "customer_email": {k: emails[-1].get(k) for k in ("to", "subject")} if emails else None,
        "final_status": updates[-1].get("status") if updates else None,
        "final_note": updates[-1].get("note") if updates else None,
        "tokens_used": finish.get("tokens_used"),
    }


def append(run_id: str, agent: str, event: str, **details: Any) -> None:
    """Append one entry to the audit trail (thread-safe, atomic replace, never truncates)."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "run_id": run_id,
        "agent": agent,
        "event": event,
        **{k: _clip(v) for k, v in details.items()},
    }
    with _lock:
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        entries = _read(AUDIT_PATH)
        entry["seq"] = len(entries) + 1
        entries.append(entry)
        atomic_write_text(AUDIT_PATH, json.dumps(entries, indent=2, default=str))


@dataclass
class AuditedToolset(WrapperToolset):
    """Logs every tool call an agent makes, with its arguments and result or error."""

    async def call_tool(
        self, name: str, tool_args: dict[str, Any], ctx: RunContext[Any], tool: ToolsetTool[Any]
    ) -> Any:
        if name in UNLOGGED_TOOLS:
            return await super().call_tool(name, tool_args, ctx, tool)
        deps = ctx.deps
        run_id, agent = deps.session.run_id, deps.agent_id
        try:
            result = await super().call_tool(name, tool_args, ctx, tool)
        except Exception as exc:
            append(run_id, agent, "tool_error", tool=name, args=tool_args, error=f"{type(exc).__name__}: {exc}")
            raise
        append(run_id, agent, "tool_call", tool=name, args=tool_args, result=result)
        deps.session.after_tool(agent, name, result)
        return result
