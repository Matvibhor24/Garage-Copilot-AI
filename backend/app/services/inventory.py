"""Inventory: stock lookup by spoken name, parts used on a job, low-stock flags."""

import re

from app import db
from app.services import core, jobs
from app.services.core import Invalid, NotFound, get_doc


def part_ref(garage_id: str, part_id: str):
    return core.garage(garage_id).collection("inventory").document(part_id)


def low_at(garage_id: str, part: dict) -> int:
    """A part's low-stock level: its own low_at, else the garage's (owner Settings, default 1)."""
    return part["low_at"] if "low_at" in part else jobs.config(garage_id).get("low_at", 1)


def _words(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words}


def search(garage_id: str, query: str, vehicle: str = "", limit: int = 3) -> list[dict]:
    """Best matching parts for a spoken query like "clutch plate" + "Splendor"."""
    wanted, model = _words(query), _words(vehicle)
    scored = []
    for snap in core.garage(garage_id).collection("inventory").stream():
        part = snap.to_dict() | {"id": snap.id}
        name_words = _words(part["name"]) | _words(" ".join(part.get("keywords", [])))
        hits = len(wanted & name_words)
        if not hits:
            continue
        fits = _words(" ".join(part.get("fits", [])))
        fit_score = 2 if model and model & fits else (1 if not fits or "universal" in fits else 0)
        if model and fit_score == 0:
            continue
        consumable = 2 if part.get("kind") == "consumable" else 0  # "engine oil" means the oil, not the top-up
        scored.append((hits * 3 + fit_score - consumable, part))
    scored.sort(key=lambda s: -s[0])
    return [p for _, p in scored[:limit]]


def _summary(part: dict) -> dict:
    return {
        "part_id": part["id"],
        "name": part["name"],
        "qty": part["qty"],
        "price": part["price"],
        "labour": part.get("labour", 0),
        "low_stock": part.get("low_stock", False),
    }


def check_stock(who, garage_id, request_id, part, vehicle=""):
    def work():
        matches = [_summary(p) for p in search(garage_id, part, vehicle)]
        return {"query": part, "vehicle": vehicle, "matches": matches}, []

    return core.run(who, garage_id, request_id, "check_stock", work)


def resolve(garage_id: str, part: str, vehicle: str = "") -> dict:
    snap = part_ref(garage_id, part).get()
    if snap.exists:
        return snap.to_dict() | {"id": snap.id}
    matches = search(garage_id, part, vehicle, limit=1)
    if not matches:
        raise NotFound(f"no part matching '{part}'")
    return matches[0]


def fittings(garage_id: str, item: dict, units: int) -> list[tuple[dict, int]]:
    """The consumables used with `units` of a part (its `with` list): [(consumable, qty needed)]."""
    out = []
    for w in item.get("with", []):
        snap = part_ref(garage_id, w["part_id"]).get()
        if snap.exists:
            out.append((snap.to_dict() | {"id": snap.id}, w.get("qty", 1) * units))
    return out


def log_part_used(who, garage_id, request_id, job_id, part, qty=1):
    """Take the part and its consumables (C13) out of stock in one call. Billable consumables become their own
    bill lines; the others are recorded on the job as `consumables` with their cost. A consumable short in stock
    never blocks the main part: what is there is used, the shortfall is recorded and the item flagged low."""
    def work():
        job = get_doc(jobs.job_ref(garage_id, job_id))
        if job["status"] != "open":
            raise Invalid(f"{job_id} is closed")
        item = resolve(garage_id, part, job["vehicle"])
        if qty < 1 or item["qty"] < qty:
            raise Invalid(f"only {item['qty']} {item['name']} in stock")
        left = item["qty"] - qty
        low = left <= low_at(garage_id, item)
        part_ref(garage_id, item["id"]).update({"qty": db.Increment(-qty), "low_stock": low})
        lines = [{
            "part_id": item["id"],
            "name": item["name"],
            "qty": qty,
            "price": item["price"],
            "total": item["price"] * qty,
            "cost": item.get("cost", 0) * qty,
            "request_id": request_id,  # keeps lines unique for ArrayUnion
        }]
        used, shortfall, low_items = [], [], []
        for c, need in fittings(garage_id, item, qty):
            take = min(need, c["qty"])
            c_low = c["qty"] - take <= low_at(garage_id, c) or take < need
            part_ref(garage_id, c["id"]).update({"qty": db.Increment(-take), "low_stock": c_low})
            if take < need:
                shortfall.append({"part_id": c["id"], "name": c["name"], "needed": need, "missing": need - take})
            if c_low:
                low_items.append(c["id"])
            entry = {"part_id": c["id"], "name": c["name"], "qty": need, "cost": c.get("cost", 0) * need,
                     "with": item["id"], "request_id": f"{request_id}:{c['id']}"}
            if c.get("billable"):
                lines.append(entry | {"price": c["price"], "total": c["price"] * need, "consumable": True})
            else:
                used.append(entry)
        added = sum(line["total"] for line in lines)
        update = {"parts": db.ArrayUnion(lines), "bill": db.Increment(added)}
        if used:
            update["consumables"] = db.ArrayUnion(used)
        jobs.job_ref(garage_id, job_id).update(update)
        has_fittings = len(lines) > 1 or bool(used)
        say = f"Logged {qty} {item['name']}" + (" and the usual fittings" if has_fittings else "") + "."
        if shortfall:
            say += " Short on " + ", ".join(f"{s['name']} ({s['missing']} missing)" for s in shortfall) + "."
        result = {"job_id": job_id, "part_id": item["id"], "name": item["name"], "qty_used": qty,
                  "qty_left": left, "low_stock": low, "bill": job["bill"] + added,
                  "fittings": [line["name"] for line in lines[1:]] + [u["name"] for u in used],
                  "fittings_billed": added - lines[0]["total"], "shortfall": shortfall,
                  "low_consumables": low_items, "say": say}
        return result, []

    return core.run(who, garage_id, request_id, "log_part_used", work)


def list_inventory(who, garage_id, low_only=False) -> list[dict]:
    core.check_tenant(who, garage_id)
    query = core.garage(garage_id).collection("inventory")
    if low_only:
        query = query.where(filter=db.FieldFilter("low_stock", "==", True))
    return [d.to_dict() | {"id": d.id} for d in query.stream()]


def restock(who, garage_id, request_id, part_id, qty):
    def work():
        item = get_doc(part_ref(garage_id, part_id))
        left = item["qty"] + qty
        low = left <= low_at(garage_id, item)
        part_ref(garage_id, part_id).update({"qty": db.Increment(qty), "low_stock": low, "reorder_pending": False})
        if not low:
            ask_ref(garage_id, part_id).delete()
        return {"part_id": part_id, "qty": left}, []

    return core.run(who, garage_id, request_id, "restock", work)


def reorder(who, garage_id, request_id, part_id, qty=0):
    """Owner said yes to a reorder: record it and message the supplier (simulated WhatsApp)."""
    def work():
        if who["role"] != "owner":
            raise core.Forbidden("only the owner can reorder")
        item = get_doc(part_ref(garage_id, part_id))
        settings = jobs.config(garage_id)
        n = qty or item.get("reorder_qty") or settings.get("reorder_qty", 5)
        supplier = item.get("supplier") or settings.get("supplier", "supplier")
        order = {"part_id": part_id, "name": item["name"], "qty": n, "supplier": supplier,
                 "status": "ordered", "at": core.now(), "by": who["name"]}
        core.garage(garage_id).collection("reorders").document(request_id).set(order)
        part_ref(garage_id, part_id).update({"reorder_pending": True})
        if ask_ref(garage_id, part_id).get().exists:
            ask_ref(garage_id, part_id).set({"status": "ordered", "answered_at": order["at"]}, merge=True)
        garage_name = (core.garage(garage_id).get().to_dict() or {}).get("name", "")
        message = {"to": f"supplier:{supplier}", "kind": "reorder", "part_id": part_id,
                   "text": f"{garage_name} order: {n} x {item['name']} ({', '.join(item.get('fits', []))})."}
        return order, [message]

    return core.run(who, garage_id, request_id, "reorder", work)


def ask_ref(garage_id: str, part_id: str):
    return core.garage(garage_id).collection("reorder_asks").document(part_id)


def ask_reorder(who, garage_id, request_id, part_id):
    """Ask the owner "Clutch plate set down to 1. Reorder 5 from Sai Spares?" once per low-stock spell."""
    def work():
        item = get_doc(part_ref(garage_id, part_id))
        open_ask = ask_ref(garage_id, part_id).get().to_dict()
        if open_ask and open_ask.get("status") == "asked":
            return open_ask | {"already_asked": True}, []
        settings = jobs.config(garage_id)
        n = item.get("reorder_qty") or settings.get("reorder_qty", 5)
        supplier = item.get("supplier") or settings.get("supplier", "the supplier")
        text = f"{item['name']} down to {item['qty']}. Reorder {n} from {supplier}?"
        ask = {"part_id": part_id, "name": item["name"], "qty_left": item["qty"], "reorder_qty": n,
               "supplier": supplier, "text": text, "status": "asked", "at": core.now()}
        ask_ref(garage_id, part_id).set(ask)
        return ask | {"already_asked": False}, [{"to": "owner", "kind": "reorder_ask", "part_id": part_id, "text": text}]

    return core.run(who, garage_id, request_id, "ask_reorder", work)


def reorder_later(who, garage_id, request_id, part_id):
    def work():
        if who["role"] != "owner":
            raise core.Forbidden("only the owner can answer a reorder ask")
        ask_ref(garage_id, part_id).set({"status": "later", "answered_at": core.now()}, merge=True)
        return {"part_id": part_id, "status": "later"}, []

    return core.run(who, garage_id, request_id, "reorder_later", work)
