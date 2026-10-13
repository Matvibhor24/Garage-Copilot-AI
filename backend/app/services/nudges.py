"""Proactive nudges, run by a periodic sweep (Cloud Scheduler -> POST /api/tasks/sweep).
Request ids are fixed per thing being nudged, so running the sweep twice never nudges twice."""

from datetime import datetime, timedelta

from app import config, db
from app.services import core, inventory, jobs


def system(garage_id: str) -> dict:
    return core.actor(garage_id, "system:sweep", "system", "GarageCopilot")


def approval_nudges(garage_id: str) -> list[str]:
    """Quotes waiting longer than APPROVAL_NUDGE_MINUTES: ask the mechanic whether to call the customer."""
    cutoff = (datetime.fromisoformat(core.now()) - timedelta(minutes=config.APPROVAL_NUDGE_MINUTES)).isoformat()
    pending = core.garage(garage_id).collection("quotes").where(filter=db.FieldFilter("status", "==", "pending"))
    nudged = []
    for snap in pending.stream():
        quote = snap.to_dict()
        if quote.get("sent_at", core.now()) > cutoff or quote.get("nudged_at"):
            continue

        def work(quote_id=snap.id, quote=quote):
            job = core.get_doc(jobs.job_ref(garage_id, quote["job_id"]))
            core.garage(garage_id).collection("quotes").document(quote_id).update({"nudged_at": core.now()})
            phone = f" on {job['phone']}" if job.get("phone") else ""
            text = (f"No reply from {job['owner']} in {config.APPROVAL_NUDGE_MINUTES} minutes on quote {quote_id} "
                    f"(₹{quote['total']}). Call {job['owner']}{phone}?")
            return {"quote_id": quote_id, "job_id": job["id"]}, [
                {"to": job["mechanic_uid"], "kind": "approval_nudge", "job_id": job["id"], "quote_id": quote_id, "text": text}]

        core.run(system(garage_id), garage_id, f"nudge-approval-{snap.id}", "approval_nudge", work)
        nudged.append(snap.id)
    return nudged


def low_stock_asks(garage_id: str) -> list[str]:
    """Safety net for the Inventory agent: ask the owner about every low part not asked about yet.
    A part the owner answered "Later" on is asked again the next day."""
    today = core.now()[:10]
    asked = []
    for part in inventory.list_inventory(system(garage_id), garage_id, low_only=True):
        if part.get("reorder_pending"):
            continue
        ask = inventory.ask_ref(garage_id, part["id"]).get().to_dict() or {}
        if ask.get("status") == "asked" or (ask.get("status") == "later" and ask.get("answered_at", "")[:10] == today):
            continue
        if ask.get("status") == "later":
            inventory.ask_ref(garage_id, part["id"]).delete()
        out = inventory.ask_reorder(system(garage_id), garage_id, f"sweep-ask-{part['id']}-{today}", part["id"])
        if not out.get("already_asked"):
            asked.append(part["id"])
    return asked


def sweep() -> dict:
    """All nudges for all garages."""
    out = {}
    for snap in db.client().collection("garages").stream():
        out[snap.id] = {"approvals": approval_nudges(snap.id), "reorder_asks": low_stock_asks(snap.id)}
    return out
