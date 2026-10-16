"""Fast tools for the Live agent. Thin wrappers over the service layer.

Who is calling (garage_id, uid, name, role) comes from the ADK session state that the
voice gateway sets after checking the ID token, never from the model. The request_id
is the Gemini function call id, so a retried call is a no-op in the service layer.
Errors come back as {"error": ...} so the agent can say what went wrong.
"""

import uuid

from app import consent, gemini
from app.services import core, inventory, jobs, manuals, owner, photos, quotes, settings

CURRENT_JOB = "current_job"


def _who(tool_context, role: str = "mechanic") -> tuple[dict, str]:
    """The caller from session state. Mechanic tools refuse an owner session and owner tools a mechanic one,
    on top of each agent only having its own tools. role="any": read-only tools both may use. A front-desk caller
    (C15) is neither, so no staff tool ever runs for a phone caller."""
    s = tool_context.state
    who = core.actor(s["garage_id"], s["uid"], s.get("role", "mechanic"), s.get("name", ""))
    allowed = ("owner", "mechanic") if role == "any" else (role,)
    if who["role"] not in allowed:
        raise core.Forbidden(f"this is a {role} tool")
    return who, s["garage_id"]


def _request_id(tool_context) -> str:
    return getattr(tool_context, "function_call_id", None) or uuid.uuid4().hex


def _job_id(tool_context, job: str) -> str:
    who, g = _who(tool_context)
    if job:
        job_id = jobs.find_job(who, g, job)["id"]
    elif tool_context.state.get(CURRENT_JOB):
        job_id = tool_context.state[CURRENT_JOB]
    else:
        raise core.NotFound("which job? say the number plate")
    tool_context.state[CURRENT_JOB] = job_id
    return job_id


def _safe(fn):
    try:
        return fn()
    except (core.Invalid, core.NotFound, core.Forbidden) as e:
        return {"error": str(e)}


def create_job(plate: str, vehicle: str, owner_name: str, owner_phone: str, complaint: str, tool_context,
               customer_language: str = "") -> dict:
    """Open a new job card when a vehicle comes in.

    Args:
        plate: number plate, e.g. "MH12 AB 1234".
        vehicle: make/model, e.g. "Splendor Plus".
        owner_name: customer's name.
        owner_phone: customer's phone number, or "" if not given.
        complaint: what the customer wants done, e.g. "clutch slipping, general service".
        customer_language: only if the mechanic says which language the customer wants messages in, as a code
            (en, hi, mr, ...); "" keeps a returning customer's language, new customers get English.
    """
    def call():
        who, g = _who(tool_context)
        lang = customer_language.strip().lower()
        out = jobs.create_job(who, g, _request_id(tool_context), plate, vehicle, owner_name, owner_phone, complaint,
                              lang if lang in gemini.LANGUAGES else "")
        tool_context.state[CURRENT_JOB] = out["job_id"]
        return out

    return _safe(call)


def get_vehicle_history(plate: str, tool_context) -> dict:
    """Past visits for a number plate: dates, complaints, parts fitted. Use right after create_job
    and mention anything related to today's complaint (e.g. "Last clutch: 8 months ago").

    Args:
        plate: number plate, e.g. "MH12 AB 1234".
    """
    def call():
        who, g = _who(tool_context)
        return jobs.vehicle_history(who, g, _request_id(tool_context), plate)

    return _safe(call)


def update_stage(stage: str, job: str, tool_context) -> dict:
    """Move a job to a new stage. Stages in garage order: service, waiting_approval, washing (after the repair),
    ready. Use close_job for done.

    Args:
        stage: the new stage name.
        job: job number or number plate; "" for the job being discussed.
    """
    def call():
        who, g = _who(tool_context)
        return jobs.update_stage(who, g, _request_id(tool_context), _job_id(tool_context, job), stage)

    return _safe(call)


def check_stock(part: str, vehicle: str, tool_context) -> dict:
    """Look up a part: quantity in stock, price and usual labour charge.

    Args:
        part: the part as spoken, e.g. "clutch plate".
        vehicle: model it is for, e.g. "Splendor", or "" if any.
    """
    def call():
        who, g = _who(tool_context)
        return inventory.check_stock(who, g, _request_id(tool_context), part, vehicle)

    return _safe(call)


def log_part_used(part: str, qty: int, job: str, tool_context) -> dict:
    """Record parts fitted on a job. Takes them and their usual fittings (gaskets, bolts, oil...) out of stock and
    adds them to the bill. Read back only "say" (the main part, plus "and the usual fittings"); never list bolts.

    Args:
        part: part name as spoken or a part_id from check_stock.
        qty: how many were used.
        job: job number or number plate; "" for the job being discussed.
    """
    def call():
        who, g = _who(tool_context)
        job_id = _job_id(tool_context, job)
        return inventory.log_part_used(who, g, _request_id(tool_context), job_id, part, qty)

    return _safe(call)


def close_job(job: str, tool_context) -> dict:
    """Finish a job: marks it ready for pickup and sends the customer the final bill.

    Args:
        job: job number or number plate; "" for the job being discussed.
    """
    def call():
        who, g = _who(tool_context)
        return jobs.close_job(who, g, _request_id(tool_context), _job_id(tool_context, job))

    return _safe(call)


def lookup_manual(question: str, vehicle: str, tool_context) -> dict:
    """Look up a spec or a how-to in the vehicle's manual (owner's manual or the team's procedure sheets):
    battery, spark plug gap, tyre pressure, oil grade and quantity, free play, service intervals, steps.
    Answer only from the returned passages; found=false means it is not in the manual.

    Args:
        question: the question as asked, e.g. "clutch lever free play".
        vehicle: model, e.g. "Splendor Plus"; "" for the vehicle of the job being discussed.
    """
    def call():
        who, g = _who(tool_context, "any")
        model = vehicle
        if not model.strip():
            current = tool_context.state.get(CURRENT_JOB)
            if not current:
                raise core.Invalid("which vehicle? say the model")
            model = jobs.get_job(who, g, current)["vehicle"]
        out = manuals.lookup(who, g, _request_id(tool_context), question, model)
        if not out["found"] and who["role"] == "mechanic":
            consent.offer(who["uid"], question)  # the agent now asks "Shall I search online?" (C19)
        return {"found": out["found"], "vehicle": out["vehicle"],
                "source": manuals.source_label(out["sources"][0]) if out["sources"] else "",
                "answer_sources": [{"title": h["title"], "page": h["page"], "section": h["section"], "text": h["text"]}
                                   for h in out["sources"]]}

    return _safe(call)


async def web_search_fixes(question: str, vehicle: str, confirmed: bool, tool_context) -> dict:
    """Search the web for common causes and known fixes of a problem, ONLY after lookup_manual found nothing and
    the mechanic said yes to "Shall I search online?". Returns 2-3 points with the source sites. They are from
    the web, not the manual, and never a diagnosis.

    Args:
        question: the problem as the mechanic described it, e.g. "hard to start in the morning".
        vehicle: model, e.g. "Splendor Plus"; "" for the vehicle of the job being discussed.
        confirmed: true only when the mechanic just agreed to an online search.
    """
    import asyncio

    from app.services import websearch

    if confirmed is not True:
        return {"error": 'not searched: ask the mechanic "Shall I search online for known causes and fixes?" first'}
    # The model saying "confirmed" isn't enough: the manual must have come up empty and the mechanic's own next
    # words must be a yes (C19).
    if not consent.allowed(tool_context.state.get("uid", "")):
        return {"error": 'not searched: the mechanic hasn\'t said yes yet. Look it up in the manual first; if it isn\'t '
                         'there, ask "Shall I search online for known causes and fixes?" and wait for their answer'}
    try:
        who, g = _who(tool_context)
        model = vehicle.strip()
        if not model:
            current = tool_context.state.get(CURRENT_JOB)
            if not current:
                raise core.Invalid("which vehicle? say the model")
            model = (await asyncio.to_thread(jobs.get_job, who, g, current))["vehicle"]
        found = await websearch.search(question, model)
        consent.clear(who["uid"])  # one yes, one search
        return await asyncio.to_thread(websearch.record, who, g, _request_id(tool_context), question, model, found)
    except (core.Invalid, core.NotFound, core.Forbidden) as e:
        return {"error": str(e)}
    except Exception:  # the search service failing must not end the voice session
        import logging

        logging.getLogger(__name__).exception("web search failed")
        return {"error": "the web search didn't work just now"}


# ---------------------------------------------------------------- Quote agent tools


def describe_photo(job: str, tool_context) -> dict:
    """Caption the latest photo of the job (e.g. "friction surface glazed") for the customer's quote.

    Args:
        job: job number or number plate; "" for the job being discussed.
    """
    def call():
        who, g = _who(tool_context)
        return photos.describe_photo(who, g, _request_id(tool_context), _job_id(tool_context, job))

    return _safe(call)


def draft_quote(parts: list[str], note: str, job: str, tool_context) -> dict:
    """Draft an itemised quote: parts at stock price plus usual labour, with the latest photo attached.
    Returns quote_id, total and needs_approval (total above the garage's quote limit).

    Args:
        parts: part names as spoken or part_ids, one entry per unit.
        note: short reason for the customer, e.g. "clutch plate worn".
        job: job number or number plate; "" for the job being discussed.
    """
    def call():
        who, g = _who(tool_context)
        return quotes.draft_quote(who, g, _request_id(tool_context), _job_id(tool_context, job), parts, note=note)

    return _safe(call)


QUOTE_TOOLS = [describe_photo, draft_quote]


# ---------------------------------------------------------------- Comms agent tools


def send_status_link(job: str, tool_context) -> dict:
    """Send the customer the link to their live job status page (WhatsApp).

    Args:
        job: job number or number plate; "" for the job being discussed.
    """
    def call():
        who, g = _who(tool_context)
        return jobs.send_status_link(who, g, _request_id(tool_context), _job_id(tool_context, job))

    return _safe(call)


def send_quote(quote_id: str, tool_context) -> dict:
    """Send a drafted quote to the customer in their language. Above the garage's auto-approve limit it waits
    for their Approve/Reject (status "pending"); otherwise it is approved straight away (auto=true, and "say"
    holds the line for the mechanic, e.g. "Approved automatically: within the ₹500 limit").

    Args:
        quote_id: e.g. "Q-77", from draft_quote.
    """
    def call():
        who, g = _who(tool_context)
        return quotes.send_quote(who, g, _request_id(tool_context), quote_id.upper().replace(" ", "-"))

    return _safe(call)


COMMS_TOOLS = [send_status_link, send_quote]


# ---------------------------------------------------------------- Inventory agent tools


def low_stock_report(tool_context) -> dict:
    """Parts at or below their low-stock level, with quantity left."""
    def call():
        who, g = _who(tool_context)
        low = inventory.list_inventory(who, g, low_only=True)
        return {"low_stock": [{"part_id": p["id"], "name": p["name"], "qty": p["qty"],
                               "reorder_pending": p.get("reorder_pending", False)} for p in low]}

    return _safe(call)


def ask_owner_to_reorder(part_id: str, tool_context) -> dict:
    """Ask the owner on their dashboard whether to reorder a low part from the usual supplier.
    Asks only once while the part stays low.

    Args:
        part_id: from low_stock_report or log_part_used, e.g. "clutch-splendor".
    """
    def call():
        who, g = _who(tool_context)
        return inventory.ask_reorder(who, g, _request_id(tool_context), part_id)

    return _safe(call)


INVENTORY_TOOLS = [low_stock_report, ask_owner_to_reorder]


# ---------------------------------------------------------------- Owner agent tools (read-only + reorder answers)


def _job_line(j: dict) -> dict:
    return {"job_id": j["id"], "vehicle": j.get("vehicle"), "plate": j.get("plate"), "customer": j.get("owner"),
            "stage": j.get("stage"), "status": j.get("status"), "mechanic": j.get("mechanic_name"),
            "bill": j.get("bill", 0), "waiting_on_quote": j.get("pending_quote") or None}


def today_summary(tool_context) -> dict:
    """Today's numbers: open jobs (and how many per stage), jobs closed today, revenue today in rupees,
    quotes waiting for customer approval, low-stock parts, open reorder questions."""
    def call():
        who, g = _who(tool_context, "owner")
        d = owner.dashboard(who, g)
        return {"open_jobs": d["open_jobs"], "open_by_stage": d["jobs_by_stage"],
                "closed_today": len(d["minutes_per_job"]), "revenue_today": d["revenue_today"],
                "pending_approvals": len(d["pending_approvals"]), "low_stock_parts": len(d["low_stock"]),
                "reorder_questions": [a.get("text") for a in d["reorder_asks"]]}

    return _safe(call)


def list_open_jobs(stage: str, mechanic: str, tool_context) -> dict:
    """Jobs on the floor now, optionally only one stage or one mechanic.

    Args:
        stage: intake, service, waiting_approval, washing or ready; "" for all.
        mechanic: mechanic's name; "" for all.
    """
    def call():
        who, g = _who(tool_context, "owner")
        out = [_job_line(j) for j in jobs.list_jobs(who, g)]
        if stage:
            out = [j for j in out if j["stage"] == stage.strip().lower()]
        if mechanic:
            out = [j for j in out if (j["mechanic"] or "").lower() == mechanic.strip().lower()]
        return {"count": len(out), "jobs": out}

    return _safe(call)


def job_details(job: str, tool_context) -> dict:
    """One job: vehicle, customer, mechanic, stage, minutes spent in each stage and in total, parts, bill, and
    money: the bill split (parts + consumables + labour), what the parts and consumables cost the garage, and the
    margin. Use it for "what did J-1042 cost us?". Finds closed jobs by number; open jobs also by plate.

    Args:
        job: job number (e.g. "J-1042" or "1042") or number plate.
    """
    def call():
        who, g = _who(tool_context, "owner")
        j = jobs.find_job(who, g, job)
        minutes = j.get("stage_minutes", {})
        return _job_line(j) | {"complaint": j.get("complaint"), "minutes_per_stage": minutes,
                               "total_minutes": sum(minutes.values()),
                               "parts": [{"name": p["name"], "qty": p["qty"], "total": p["total"]} for p in j.get("parts", [])],
                               "garage_consumables": [{"name": c["name"], "qty": c["qty"], "cost": c["cost"]}
                                                      for c in j.get("consumables", [])],
                               "money": jobs.money(j)}

    return _safe(call)


def pending_approvals(tool_context) -> dict:
    """Quotes sent to customers and still waiting for their Approve or Reject."""
    def call():
        who, g = _who(tool_context, "owner")
        d = owner.dashboard(who, g)
        return {"count": len(d["pending_approvals"]),
                "quotes": [{"quote_id": q["id"], "job_id": q.get("job_id"), "total": q.get("total"),
                            "note": q.get("note"), "sent_at": q.get("sent_at")} for q in d["pending_approvals"]]}

    return _safe(call)


def low_stock(tool_context) -> dict:
    """Parts at or below their low-stock level, with quantity left and whether a reorder is already placed."""
    def call():
        who, g = _who(tool_context, "owner")
        low = inventory.list_inventory(who, g, low_only=True)
        return {"low_stock": [{"part_id": p["id"], "name": p["name"], "qty": p["qty"],
                               "reorder_pending": p.get("reorder_pending", False)} for p in low]}

    return _safe(call)


def recent_activity(limit: int, tool_context) -> dict:
    """The latest things that happened in the garage (who did what, when), newest first.

    Args:
        limit: how many entries, e.g. 10.
    """
    def call():
        who, g = _who(tool_context, "owner")
        entries = owner.audit_log(who, g, limit=max(1, min(int(limit or 10), 30)))
        return {"activity": [{"at": a["at"], "who": a.get("by_name"), "action": a["action"],
                              "details": a.get("details")} for a in entries]}

    return _safe(call)


def garage_settings(tool_context) -> dict:
    """The garage's settings: auto-approve limit in rupees (quotes up to it are approved without asking the
    customer; 0 = always ask), garage name and city, default customer language, supplier, reorder quantity and
    low-stock level. Read-only: settings are changed in the app's Settings tab."""
    def call():
        who, g = _who(tool_context, "owner")
        out = settings.get_settings(who, g)
        out.pop("languages", None)
        return out | {"auto_approve_limit": out["quote_limit"]}

    return _safe(call)


def mechanic_jobs(mechanic: str, period: str, tool_context) -> dict:
    """How many jobs a mechanic (or every mechanic) finished in a period, their open jobs now, average time per job,
    revenue on their jobs and parts logged. "How many jobs did Raju finish this week?"

    Args:
        mechanic: the mechanic's name, or "" for everyone.
        period: "today", "week" (Monday to today) or "month" (1st to today).
    """
    from app.services import reports

    def call():
        who, g = _who(tool_context, "owner")
        out = reports.staff(who, g, period.strip().lower() or "week")
        rows = [m for m in out["mechanics"] if not mechanic.strip() or m["name"].lower() == mechanic.strip().lower()]
        if mechanic.strip() and not rows:
            raise core.NotFound(f"no mechanic called {mechanic}")
        return {"period": out["period"], "from": out["from"], "to": out["to"],
                "mechanics": [{k: m[k] for k in ("name", "finished", "open_now", "average_minutes", "revenue",
                                                 "parts_logged", "active")} for m in rows]}

    return _safe(call)


def revenue_for(period: str, tool_context) -> dict:
    """Money from jobs closed in a period: revenue, number of jobs, average bill, cost of parts used and margin.
    "How much did we make this month?"

    Args:
        period: "today", "week" (Monday to today) or "month" (1st to today).
    """
    from app.services import reports

    def call():
        who, g = _who(tool_context, "owner")
        return reports.revenue(who, g, period.strip().lower() or "today")

    return _safe(call)


def vehicle_last_visit(plate: str, tool_context) -> dict:
    """When a vehicle last came in, what was done and the bill. "When did MH12AB1234 last come in?"

    Args:
        plate: number plate, e.g. "MH12 AB 1234".
    """
    from app.services import reports

    def call():
        who, g = _who(tool_context, "owner")
        return reports.last_visit(who, g, plate)

    return _safe(call)


def answer_reorder(part_id: str, answer: str, tool_context) -> dict:
    """The owner answers an open reorder question. Only when the owner clearly said yes or later.

    Args:
        part_id: the part, e.g. "clutch-splendor" (from today_summary or low_stock).
        answer: "yes" to order from the usual supplier, "later" to be asked again tomorrow.
    """
    def call():
        who, g = _who(tool_context, "owner")
        if answer.strip().lower() == "yes":
            return inventory.reorder(who, g, _request_id(tool_context), part_id)
        if answer.strip().lower() == "later":
            return inventory.reorder_later(who, g, _request_id(tool_context), part_id)
        raise core.Invalid('answer must be "yes" or "later"')

    return _safe(call)


OWNER_TOOLS = [today_summary, list_open_jobs, job_details, pending_approvals, low_stock, recent_activity,
               garage_settings, mechanic_jobs, revenue_for, vehicle_last_visit, answer_reorder, lookup_manual]


FAST_TOOLS = [create_job, get_vehicle_history, update_stage, check_stock, log_part_used, close_job, lookup_manual,
              web_search_fixes]


# ---------------------------------------------------------------- Front desk tools (C15: a customer calls the garage)


def _caller(tool_context) -> tuple[dict, str]:
    """The caller from session state (set by the gateway from the signed call token, never from the model)."""
    from app.services import frontdesk

    s = tool_context.state
    if s.get("role") != "caller":
        raise core.Forbidden("this is a front desk tool")
    return (frontdesk.caller(s["garage_id"], s.get("phone", ""), bool(s.get("verified")), s.get("call_id", ""),
                             s.get("call_job", "")), s["garage_id"])


def my_vehicle_status(plate: str, tool_context) -> dict:
    """The caller's own vehicle status: stage, whether a quote waits for their OK, bill so far. Only for a caller
    whose number is verified; otherwise it says it can't share details and offers to send the link instead.

    Args:
        plate: number plate if the caller has more than one vehicle in, else "".
    """
    from app.services import frontdesk

    def call():
        who, g = _caller(tool_context)
        return frontdesk.vehicle_status(who, g, _request_id(tool_context), plate)

    return _safe(call)


def send_status_link_again(plate: str, tool_context) -> dict:
    """Send the vehicle's live status link again, by WhatsApp, to the customer's number on file (not to the caller).

    Args:
        plate: the vehicle's number plate; "" if the caller is verified and has one vehicle in.
    """
    from app.services import frontdesk

    def call():
        who, g = _caller(tool_context)
        return frontdesk.send_status_link(who, g, _request_id(tool_context), plate)

    return _safe(call)


def send_quote_again(plate: str, tool_context) -> dict:
    """Send the quote that is waiting for the customer's OK again, to the customer's number on file.

    Args:
        plate: the vehicle's number plate; "" if the caller is verified and has one vehicle in.
    """
    from app.services import frontdesk

    def call():
        who, g = _caller(tool_context)
        return frontdesk.send_quote_again(who, g, _request_id(tool_context), plate)

    return _safe(call)


def request_estimate(work_wanted: str, vehicle: str, name: str, tool_context) -> dict:
    """A caller asks what a job would cost. Drafts an estimate from stock prices and sends it to the OWNER to
    confirm; the caller gets it on WhatsApp once the owner confirms. Never tell the caller a price yourself.

    Args:
        work_wanted: what they want done, e.g. "clutch plate change".
        vehicle: their vehicle model, e.g. "Splendor Plus".
        name: the caller's name if they gave it, else "".
    """
    from app.services import frontdesk

    def call():
        who, g = _caller(tool_context)
        return frontdesk.request_estimate(who, g, _request_id(tool_context), work_wanted, vehicle, name)

    return _safe(call)


def book_dropoff(name: str, vehicle: str, when: str, note: str, tool_context) -> dict:
    """Book a time for the caller to drop off their vehicle.

    Args:
        name: the caller's name.
        vehicle: model and, if given, number plate.
        when: day and time as the caller said it, e.g. "tomorrow 10 am".
        note: what they want done, or "".
    """
    from app.services import frontdesk

    def call():
        who, g = _caller(tool_context)
        return frontdesk.book_dropoff(who, g, _request_id(tool_context), name, vehicle, when, note)

    return _safe(call)


def request_callback(name: str, reason: str, tool_context) -> dict:
    """When you can't help: ask the owner to call the caller back. There is no live transfer.

    Args:
        name: the caller's name, or "".
        reason: what it's about, in a few words, e.g. "the bill for the Splendor".
    """
    from app.services import frontdesk

    def call():
        who, g = _caller(tool_context)
        return frontdesk.request_callback(who, g, _request_id(tool_context), name, reason)

    return _safe(call)


def service_wait_time(work_wanted: str, tool_context) -> dict:
    """"How long if I bring my bike now?", "how soon can you service it?". A rough range from how busy the garage is
    right now (vehicles ahead, mechanics working, how long jobs usually take). Shares only counts, never anyone's job.

    Args:
        work_wanted: what they want done, e.g. "general service", or "" if they didn't say.
    """
    from app.services import frontdesk

    def call():
        who, g = _caller(tool_context)
        return frontdesk.wait_time(who, g, _request_id(tool_context), work_wanted)

    return _safe(call)


FRONT_DESK_TOOLS = [my_vehicle_status, service_wait_time, send_status_link_again, send_quote_again, request_estimate,
                    book_dropoff, request_callback]
