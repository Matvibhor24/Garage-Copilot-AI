"""Shared service-layer plumbing: actors, tenant check, idempotency, audit log, clock."""

import logging
from datetime import datetime, timezone

from app import db, notify

log = logging.getLogger(__name__)


class Forbidden(Exception):
    """Caller may not touch this garage or object."""


class NotFound(Exception):
    """Object does not exist (in this garage)."""


class Invalid(Exception):
    """Request is well-formed but not allowed right now (e.g. not enough stock)."""


def now() -> str:
    """UTC time as an ISO string. Tests monkeypatch this to replay the demo timeline."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def minutes_ago(n: int) -> str:
    """ISO time n minutes before now() (same format, so strings compare in time order)."""
    from datetime import timedelta

    return (datetime.fromisoformat(now()) - timedelta(minutes=n)).isoformat(timespec="seconds")


def minutes_between(start: str, end: str) -> int:
    return round((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() / 60)


def actor(garage_id: str, uid: str, role: str, name: str = "") -> dict:
    """Who is calling. role: owner | mechanic | customer | agent | system."""
    return {"garage_id": garage_id, "uid": uid, "role": role, "name": name or uid}


def garage(garage_id: str):
    return db.client().collection("garages").document(garage_id)


def check_tenant(who: dict, garage_id: str) -> None:
    if not garage_id or who.get("garage_id") != garage_id:
        raise Forbidden(f"{who.get('uid')} may not access garage {garage_id}")


def get_doc(ref) -> dict:
    snap = ref.get()
    if not snap.exists:
        raise NotFound(ref.path if hasattr(ref, "path") else ref.id)
    return snap.to_dict() | {"id": snap.id}


def audit(garage_id: str, who: dict, action: str, details: dict, request_id: str = "") -> None:
    at = now()
    entry = {
        "at": at,
        "action": action,
        "by_uid": who["uid"],
        "by_name": who["name"],
        "by_role": who["role"],
        "details": details,
        "request_id": request_id,
    }
    doc_id = f"{at}_{request_id or action}"
    garage(garage_id).collection("audit_log").document(doc_id).set(entry)


def run(who: dict, garage_id: str, request_id: str, action: str, work):
    """Run one service action exactly once per (garage, request_id).

    `work()` returns (result, messages). messages is a list of notify() kwargs.
    A repeated request_id returns the stored result and writes nothing.
    """
    check_tenant(who, garage_id)
    if not request_id:
        raise Invalid("request_id is required")
    claim = garage(garage_id).collection("requests").document(request_id)
    try:
        claim.create({"action": action, "status": "running", "at": now()})
    except db.AlreadyExists:
        stored = claim.get().to_dict() or {}
        log.info("duplicate request_id %s (%s)", request_id, action)
        if stored.get("status") == "done":
            return stored["result"]
        return {"status": "in_progress", "request_id": request_id}
    try:
        result, messages = work()
    except Exception:
        claim.delete()  # let a retry try again
        raise
    audit(garage_id, who, action, result, request_id)
    for message in messages:
        notify.notify(garage_id, **message)
    claim.set({"status": "done", "result": result}, merge=True)
    return result
