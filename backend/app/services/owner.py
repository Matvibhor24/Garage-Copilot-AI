"""Owner dashboard numbers and audit log reads."""

from datetime import datetime
from zoneinfo import ZoneInfo

from app import db
from app.services import core, inventory, jobs


def dashboard(who: dict, garage_id: str) -> dict:
    """The four tiles: open jobs, pending approvals, low stock, revenue today (garage local day)."""
    core.check_tenant(who, garage_id)
    tz = ZoneInfo(jobs.config(garage_id).get("timezone", "Asia/Kolkata"))
    today = datetime.fromisoformat(core.now()).astimezone(tz).date()
    all_jobs = [d.to_dict() | {"id": d.id} for d in core.garage(garage_id).collection("jobs").stream()]
    open_jobs = [j for j in all_jobs if j.get("status") == "open"]
    closed_today = [j for j in all_jobs if j.get("closed_at")
                    and datetime.fromisoformat(j["closed_at"]).astimezone(tz).date() == today]
    pending = core.garage(garage_id).collection("quotes").where(filter=db.FieldFilter("status", "==", "pending"))
    low = inventory.list_inventory(who, garage_id, low_only=True)
    garage_doc = core.garage(garage_id).get().to_dict() or {}
    asks = core.garage(garage_id).collection("reorder_asks").where(filter=db.FieldFilter("status", "==", "asked"))
    messages = core.garage(garage_id).collection("messages").order_by("at", direction="DESCENDING").limit(12)
    return {
        "garage": {"id": garage_id, "name": garage_doc.get("name", ""), "city": garage_doc.get("city", "")},
        "open_jobs": len(open_jobs),
        "jobs_by_stage": {s: sum(1 for j in open_jobs if j["stage"] == s) for s in jobs.STAGES if s != "done"},
        "pending_approvals": [d.to_dict() | {"id": d.id} for d in pending.stream()],
        "low_stock": [{"part_id": p["id"], "name": p["name"], "qty": p["qty"]} for p in low],
        "revenue_today": sum(j.get("bill", 0) for j in closed_today),
        "cost_today": sum(jobs.money(j)["cost"] for j in closed_today),  # parts + consumables used (C13)
        "margin_today": sum(jobs.money(j)["margin"] for j in closed_today),
        "minutes_per_job": {j["id"]: sum(j.get("stage_minutes", {}).values()) for j in closed_today},
        "reorder_asks": [d.to_dict() for d in asks.stream()],
        "jobs": [jobs.compact(j) for j in open_jobs + closed_today],
        "messages": [d.to_dict() | {"id": d.id} for d in messages.stream()],
    }


def audit_log(who: dict, garage_id: str, limit: int = 50) -> list[dict]:
    core.check_tenant(who, garage_id)
    query = core.garage(garage_id).collection("audit_log").order_by("at", direction="DESCENDING").limit(limit)
    return [d.to_dict() for d in query.stream()]
