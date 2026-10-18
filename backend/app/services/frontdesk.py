"""AI front desk (C15): a customer calls the garage and the agent answers.

Callers are identified by phone number, or by the job whose status link they called from: that private link already
lets them see the job, so such a call is `verified` for that job even when the job has no phone number on file.
A call from the website is not verified. The front desk never tells a caller anything about a
job unless the caller is verified and the job is theirs. Sending the status link or the pending quote again is
allowed for any caller, because it goes to the number on file, never to the caller. Everything else it can do is
read-only or a request the owner handles: a price estimate (owner confirms before the customer gets it), a
drop-off booking, a callback request. Each call is a `calls/{call_id}` doc the owner sees.
"""

import re

from app import links
from app.services import core, inventory, jobs, quotes
from app.services.core import Forbidden, Invalid, NotFound, get_doc


def digits(phone: str) -> str:
    """Last 10 digits: "+91 98000 00101" and "9800000101" are the same caller."""
    return re.sub(r"\D", "", phone or "")[-10:]


def caller(garage_id: str, phone: str, verified: bool, call_id: str, job_id: str = "") -> dict:
    who = core.actor(garage_id, f"caller:{digits(phone) or 'job-' + job_id}", "caller", "Caller")
    return who | {"phone": digits(phone), "verified": verified, "call_id": call_id, "job_id": job_id}


def _contact(who: dict) -> str:
    """How the owner reaches the caller: their number, or the job they called about (whose customer is on file)."""
    return who["phone"] or (f"the customer on {who['job_id']}" if who.get("job_id") else "unknown number")


def _check(who: dict, garage_id: str) -> None:
    core.check_tenant(who, garage_id)
    if who.get("role") != "caller":
        raise Forbidden("front desk tools are for callers")


def call_ref(garage_id: str, call_id: str):
    return core.garage(garage_id).collection("calls").document(call_id)


# ---------------------------------------------------------------- calls


def start_call(garage_id: str, phone: str, verified: bool, via: str, per_phone: int, per_garage: int,
               job_id: str = "") -> dict:
    """Open a call record and return a short-lived caller token. Rate-limited per number (or per job, for a call from a
    status link without a number on file) and per garage, over the last hour."""
    if not job_id and len(digits(phone)) < 10:
        raise Invalid("say a 10-digit phone number")
    if not (core.garage(garage_id).get().to_dict() or {}):
        raise NotFound("no such garage")
    hour_ago = core.minutes_ago(60)
    recent = [d.to_dict() for d in core.garage(garage_id).collection("calls").stream()
              if d.to_dict().get("started_at", "") >= hour_ago]
    key = digits(phone) or f"job:{job_id}"
    if len(recent) >= per_garage or sum(1 for c in recent if (c.get("phone") or f"job:{c.get('job_id', '')}") == key) >= per_phone:
        raise Invalid("too many calls in the last hour; please try again later")
    call_id = jobs.next_id(garage_id, "next_call_no", "C", "calls", {
        "phone": digits(phone), "job_id": job_id, "verified": verified, "via": via, "started_at": core.now(), "status": "live",
        "actions": [], "heard": []})
    token = links.make_caller_token(garage_id, digits(phone), verified, call_id, job_id)
    return {"call_id": call_id, "token": token, "verified": verified}


def note_action(who: dict, garage_id: str, text: str) -> None:
    """One line on the call record: what the AI did ("Status link sent", "Callback requested")."""
    from app import db

    if who.get("call_id"):
        call_ref(garage_id, who["call_id"]).set({"actions": db.ArrayUnion([text])}, merge=True)


def note_heard(garage_id: str, call_id: str, text: str) -> None:
    """The caller's words (first few turns) become the call's summary on the owner's Calls list."""
    snap = call_ref(garage_id, call_id).get()
    heard = (snap.to_dict() or {}).get("heard", [])
    if len(heard) < 6 and text.strip():
        call_ref(garage_id, call_id).set({"heard": heard + [text.strip()[:200]]}, merge=True)


def end_call(garage_id: str, call_id: str) -> None:
    call_ref(garage_id, call_id).set({"status": "ended", "ended_at": core.now()}, merge=True)


# ---------------------------------------------------------------- what the caller may ask


def _jobs_for(who: dict, garage_id: str, plate: str = "") -> list[dict]:
    """The caller's open jobs: by their verified number, else (for sending a link to the number on file) by plate."""
    all_open = jobs.list_jobs(core.actor(garage_id, "system:frontdesk", "system"), garage_id)
    if who["verified"]:
        mine = [j for j in all_open if (who.get("job_id") and j["id"] == who["job_id"])
                or (who["phone"] and digits(j.get("phone", "")) == who["phone"])]
        if plate:
            mine = [j for j in mine if j["plate"].endswith(jobs.normalise_plate(plate))]
        return mine
    if not plate:
        return []
    return [j for j in all_open if jobs.normalise_plate(plate) and j["plate"].endswith(jobs.normalise_plate(plate))]


def vehicle_status(who, garage_id, request_id, plate=""):
    """Status of the caller's own vehicle(s). Unverified callers get no job details, only the offer of a link."""
    def work():
        _check(who, garage_id)
        if not who["verified"]:
            return {"verified": False, "jobs": [],
                    "say": "I can't share job details on this line. I can send the status link to the number we "
                           "have on file for the vehicle; tell me the number plate."}, []
        mine = _jobs_for(who, garage_id, plate)
        out = [{"job_id": j["id"], "vehicle": j["vehicle"], "plate": j["plate"],
                "stage": jobs.STAGE_LABELS.get(j["stage"], j["stage"]), "waiting_for_your_ok": bool(j.get("pending_quote")),
                "bill_so_far": j.get("bill", 0)} for j in mine]
        return {"verified": True, "jobs": out}, []

    out = core.run(who, garage_id, request_id, "caller_status", work)
    note_action(who, garage_id, "Told the caller their vehicle status" if out["jobs"] else "Status asked: nothing to share")
    return out


def send_status_link(who, garage_id, request_id, plate=""):
    """Send the job's status link again, to the customer's number on file (never to the caller)."""
    _check(who, garage_id)
    mine = _jobs_for(who, garage_id, plate)
    if not mine:
        raise NotFound("no open job for that number plate" if plate else "which vehicle? say the number plate")
    jobs.send_status_link(who, garage_id, request_id, mine[0]["id"])
    note_action(who, garage_id, f"Status link sent again ({mine[0]['id']})")
    return {"sent": True, "sent_to": "the number we have on file"}


def send_quote_again(who, garage_id, request_id, plate=""):
    """Resend the pending quote to the customer's number on file."""
    _check(who, garage_id)
    mine = [j for j in _jobs_for(who, garage_id, plate) if j.get("pending_quote")]
    if not mine:
        raise NotFound("no quote waiting for that vehicle")
    out = quotes.resend_quote(who, garage_id, request_id, mine[0]["pending_quote"])
    note_action(who, garage_id, f"Quote {out['quote_id']} sent again")
    return {"sent": True, "sent_to": "the number we have on file", "quote_id": out["quote_id"]}


def _round15(minutes: float) -> int:
    return max(15, int(round(minutes / 15.0)) * 15)


def wait_time(who, garage_id, request_id, work_wanted: str = ""):
    """Rough "if I bring it in now" answer from the live floor: how long until a mechanic is free and how long a job
    usually takes. Only counts and ranges, never another customer's vehicle, name or job."""
    def work():
        _check(who, garage_id)
        system = core.actor(garage_id, "system:frontdesk", "system")
        open_jobs = jobs.list_jobs(system, garage_id)
        mechanics = [d.to_dict() for d in core.garage(garage_id).collection("mechanics").stream()]
        on_shift = [m for m in mechanics if m.get("role") == "mechanic" and m.get("active") is not False]
        crew = max(1, len({j.get("mechanic_name") for j in open_jobs if j.get("mechanic_name")}) or len(on_shift))
        # How long a job usually takes: median of jobs closed in the last 30 days, else an hour
        since = core.minutes_ago(30 * 24 * 60)
        closed = [d.to_dict() for d in core.garage(garage_id).collection("jobs").stream()
                  if d.to_dict().get("status") == "done" and d.to_dict().get("closed_at", "") >= since]
        totals = sorted(sum((j.get("stage_minutes") or {}).values()) for j in closed if j.get("stage_minutes"))
        typical = totals[len(totals) // 2] if totals else 60
        typical = min(max(typical, 30), 240)
        waiting = sum(1 for j in open_jobs if j.get("stage") == "intake")
        working = sum(1 for j in open_jobs if j.get("stage") in ("service", "waiting_approval"))
        # Work ahead of a new vehicle, shared by the crew: waiting jobs in full, jobs on the lifts half done
        ahead = (waiting + 0.5 * working) * typical / crew
        start = 0 if waiting + working < crew else ahead
        out = {
            "vehicles_ahead": waiting + working,
            "mechanics_working": crew,
            "start_in_minutes": [_round15(start * 0.8), _round15(start * 1.3 + 15)] if start else [0, 15],
            "job_takes_minutes": [_round15(typical * 0.8), _round15(typical * 1.3)],
            "note": "a rough estimate from how busy the garage is right now; the mechanic confirms after a look",
        }
        return out, []

    out = core.run(who, garage_id, request_id, "caller_wait_time", work)
    note_action(who, garage_id, f"Told the caller the rough wait ({out['vehicles_ahead']} vehicle(s) ahead)")
    return out


def estimate_ref(garage_id: str, estimate_id: str):
    return core.garage(garage_id).collection("estimates").document(estimate_id)


def request_estimate(who, garage_id, request_id, work_wanted: str, vehicle: str, name: str = ""):
    """Draft a rough estimate from stock prices for the parts the caller named; it goes to the OWNER to confirm.
    The caller hears that the garage will confirm the price on WhatsApp, never a price."""
    def work():
        _check(who, garage_id)
        lines = []
        main = [i for i in inventory.search(garage_id, work_wanted, vehicle, limit=3) if i.get("kind") != "consumable"][:1]
        for item in main:  # the best-matching part for the work, plus its billable fittings
            lines.append({"part_id": item["id"], "name": item["name"], "qty": 1, "price": item["price"],
                          "total": item["price"]})
            for c, need in inventory.fittings(garage_id, item, 1):
                if c.get("billable"):
                    lines.append({"part_id": c["id"], "name": c["name"], "qty": need, "price": c["price"],
                                  "total": c["price"] * need})
        labour = max([i.get("labour", 0) for i in main] or [0])
        service = jobs.config(garage_id).get("service_fee", jobs.SERVICE_FEE)  # every job has the service charge
        total = sum(line["total"] for line in lines) + labour + service
        estimate = {"phone": who["phone"], "job_id": who.get("job_id", ""), "verified": who["verified"], "name": name,
                    "vehicle": vehicle,
                    "work": work_wanted, "lines": lines, "labour": labour, "service_fee": service, "total": total,
                    "status": "asked",
                    "at": core.now(), "call_id": who.get("call_id", "")}
        estimate_id = jobs.next_id(garage_id, "next_estimate_no", "E", "estimates", estimate)
        text = (f"Caller {_contact(who)}{f' ({name})' if name else ''} asks the price for {work_wanted} on a "
                f"{vehicle or 'vehicle'}. Estimate from stock prices: ₹{total}. Send it?")
        return ({"estimate_id": estimate_id, "status": "sent to the owner to confirm", "lines": len(lines)},
                [{"to": "owner", "kind": "estimate_ask", "estimate_id": estimate_id, "text": text}])

    out = core.run(who, garage_id, request_id, "request_estimate", work)
    note_action(who, garage_id, f"Price estimate {out['estimate_id']} sent to you to confirm")
    return out


def answer_estimate(who, garage_id, request_id, estimate_id, send: bool, total: int | None = None):
    """Owner confirms (optionally with a corrected total) or drops an estimate. Confirmed = WhatsApp to the caller."""
    def work():
        if who["role"] != "owner":
            raise Forbidden("only the owner can confirm an estimate")
        est = get_doc(estimate_ref(garage_id, estimate_id))
        if est["status"] != "asked":
            raise Invalid(f"{estimate_id} is already {est['status']}")
        if not send:
            estimate_ref(garage_id, estimate_id).update({"status": "dropped", "answered_at": core.now()})
            return {"estimate_id": estimate_id, "status": "dropped"}, []
        amount = int(total) if total is not None else est["total"]
        if amount < 0 or amount > 1_000_000:
            raise Invalid("estimate total out of range")
        estimate_ref(garage_id, estimate_id).update({"status": "sent", "total": amount, "answered_at": core.now()})
        garage_name = (core.garage(garage_id).get().to_dict() or {}).get("name", "the garage")
        text_en = (f"Hi{(' ' + est['name']) if est.get('name') else ''}, {garage_name} here. Estimate for {est['work']}"
                   f"{(' on your ' + est['vehicle']) if est.get('vehicle') else ''}: about ₹{amount} (service charge, parts and labour). "
                   "The final price is confirmed after we inspect the vehicle.")
        to = f"c-{est['phone']}" if est.get("phone") else jobs.job_ref(garage_id, est["job_id"]).get().to_dict()["customer_id"]
        message = {"to": to, "kind": "estimate", "estimate_id": estimate_id, "lang": "en",
                   **jobs.customer_texts(text_en, "en")}
        return {"estimate_id": estimate_id, "status": "sent", "total": amount}, [message]

    return core.run(who, garage_id, request_id, "answer_estimate", work)


def book_dropoff(who, garage_id, request_id, name: str, vehicle: str, when: str, note: str = ""):
    """A drop-off time the caller asked for; the owner sees it in Calls (and can call back to change it)."""
    def work():
        _check(who, garage_id)
        if not when.strip():
            raise Invalid("when would they like to come? a day and time")
        booking = {"phone": who["phone"], "job_id": who.get("job_id", ""), "name": name, "vehicle": vehicle, "when": when.strip(), "note": note,
                   "status": "booked", "at": core.now(), "call_id": who.get("call_id", "")}
        booking_id = jobs.next_id(garage_id, "next_booking_no", "B", "bookings", booking)
        text = f"New drop-off: {name or _contact(who)}, {vehicle or 'vehicle'}, {when.strip()}."
        return {"booking_id": booking_id, "when": when.strip()}, [{"to": "owner", "kind": "booking", "text": text}]

    out = core.run(who, garage_id, request_id, "book_dropoff", work)
    note_action(who, garage_id, f"Drop-off booked: {out['when']}")
    return out


def request_callback(who, garage_id, request_id, name: str, reason: str):
    """When the front desk can't help: "Call back Ramesh about …". No real call transfer."""
    def work():
        _check(who, garage_id)
        cb = {"phone": who["phone"], "job_id": who.get("job_id", ""), "name": name, "reason": reason, "status": "open", "at": core.now(),
              "call_id": who.get("call_id", "")}
        callback_id = jobs.next_id(garage_id, "next_callback_no", "CB", "callbacks", cb)
        text = f"Call back {name or _contact(who)} ({_contact(who)}) about {reason}."
        return {"callback_id": callback_id, "status": "someone will call back"}, [
            {"to": "owner", "kind": "callback", "text": text}]

    out = core.run(who, garage_id, request_id, "request_callback", work)
    note_action(who, garage_id, f"Callback requested: {reason}")
    return out


def close_callback(who, garage_id, request_id, callback_id):
    def work():
        if who["role"] != "owner":
            raise Forbidden("only the owner can close a callback")
        get_doc(core.garage(garage_id).collection("callbacks").document(callback_id))
        core.garage(garage_id).collection("callbacks").document(callback_id).update(
            {"status": "done", "done_at": core.now()})
        return {"callback_id": callback_id, "status": "done"}, []

    return core.run(who, garage_id, request_id, "close_callback", work)


def calls_overview(who: dict, garage_id: str, limit: int = 30) -> dict:
    """The owner's Calls card: recent calls, open callbacks, estimates to confirm, upcoming drop-offs."""
    core.check_tenant(who, garage_id)
    if who["role"] != "owner":
        raise Forbidden("owner only")
    g = core.garage(garage_id)

    def recent(name, key="at"):
        return sorted((d.to_dict() | {"id": d.id} for d in g.collection(name).stream()),
                      key=lambda x: x.get(key, ""), reverse=True)

    calls = recent("calls", "started_at")[:limit]
    for c in calls:
        c["summary"] = " · ".join(c.get("heard", [])[:2]) or "(no words heard)"
    return {
        "calls": calls,
        "callbacks": [c for c in recent("callbacks") if c.get("status") == "open"],
        "estimates": [e for e in recent("estimates") if e.get("status") == "asked"],
        "bookings": [b for b in recent("bookings") if b.get("status") == "booked"][:limit],
    }
