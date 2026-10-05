"""The human approval queue for payments, saved to output/payment_requests.json.

Agents can only DRAFT a payment or purchase: when one calls the MCP `draft_payment` or
`draft_purchase` tool and the server verifies it, the team records the server's figures
here as a PaymentRequest (status awaiting_human_approval). Nothing is paid until a human calls the backend's
approve route, which runs the MCP `pay` tool and marks the request paid (or refused).

Only one pending request is kept per bill (kind + ref_id, plus sku/size for purchases),
so a second draft of the same bill doesn't create a second approval.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import PROJECT_ROOT
from models import PaymentRequest
from safe_write import atomic_write_text

# CAMPUS_CUSTOMS_PAYMENTS (tests only) points the queue at a scratch file.
QUEUE_PATH = Path(os.getenv("CAMPUS_CUSTOMS_PAYMENTS", PROJECT_ROOT / "output" / "payment_requests.json"))

# Draft fields kept as PaymentRequest.details (shown to the human next to the approve button).
DETAIL_KEYS = (
    "unit_cost", "on_hand", "vendor_specialty", "lead_days", "arrival_if_paid_today",
    "vendor_can_ship", "blocked_by_invoices",
)


class PaymentQueue:
    def __init__(self, path: Path = QUEUE_PATH) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._items: list[PaymentRequest] = []
        if path.exists() and path.stat().st_size:
            self._items = [PaymentRequest(**r) for r in json.loads(path.read_text(encoding="utf-8"))]

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(self.path, json.dumps([r.model_dump(mode="json") for r in self._items], indent=2))

    def list(self, status: str | None = None) -> list[PaymentRequest]:
        return [r for r in self._items if status is None or r.status == status]

    def get(self, request_id: int) -> PaymentRequest | None:
        return next((r for r in self._items if r.id == request_id), None)

    def pending_total(self) -> float:
        return round(sum(r.amount for r in self.list("awaiting_human_approval")), 2)

    def add_draft(
        self, draft: dict[str, Any], drafted_by: str, run_id: str, ticket_id: int | None = None
    ) -> tuple[PaymentRequest, bool]:
        """Record a server-verified draft. Returns (request, created); an existing pending one is reused."""
        with self._lock:
            key = (draft["kind"], draft["ref_id"], draft.get("sku"), draft.get("size"))
            for r in self.list("awaiting_human_approval"):
                if (r.kind, r.ref_id, r.sku, r.size) == key:
                    return r, False
            request = PaymentRequest(
                id=max((r.id for r in self._items), default=0) + 1,
                kind=draft["kind"],
                ref_id=draft["ref_id"],
                payee=draft["payee"],
                amount=draft["amount"],
                account=draft["account"],
                description=draft.get("description"),
                due_date=draft.get("due_date"),
                balance_before=draft["balance_before"],
                balance_after=draft["balance_after"],
                sku=draft.get("sku"),
                size=draft.get("size"),
                qty=draft.get("qty"),
                details={k: draft[k] for k in DETAIL_KEYS if k in draft},
                drafted_by=drafted_by,
                run_id=run_id,
                ticket_id=ticket_id,
                drafted_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
            self._items.append(request)
            self._save()
            return request, True

    def mark_paid(self, request_id: int, approved_by: str, payment: dict[str, Any]) -> PaymentRequest:
        with self._lock:
            r = self.get(request_id)
            r.status, r.approved_by, r.payment = "paid", approved_by, payment
            self._save()
            return r

    def mark_refused(self, request_id: int, reason: str) -> PaymentRequest:
        with self._lock:
            r = self.get(request_id)
            r.status, r.refusal = "refused", reason
            self._save()
            return r

    def clear(self) -> int:
        """Drop every request (used by the reset route, since the bills they point at are restored)."""
        with self._lock:
            count = len(self._items)
            self._items = []
            self._save()
            return count
