"""Fast tools for the Live agent. Thin wrappers over the service layer.

Who is calling (garage_id, uid, name, role) comes from the ADK session state that the
voice gateway sets after checking the ID token, never from the model. The request_id
is the Gemini function call id, so a retried call is a no-op in the service layer.
Errors come back as {"error": ...} so the agent can say what went wrong.
"""

import uuid

from app.services import core, inventory, jobs, manuals, owner, photos, quotes

CURRENT_JOB = "current_job"


def _who(tool_context, role: str = "mechanic") -> tuple[dict, str]:
    """The caller from session state. Mechanic tools refuse an owner session and owner tools a mechanic one,
    on top of each agent only having its own tools. role="any": read-only tools both may use."""
    s = tool_context.state
    who = core.actor(s["garage_id"], s["uid"], s.get("role", "mechanic"), s.get("name", ""))
    if role != "any" and (role == "owner") != (who["role"] == "owner"):
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


def create_job(plate: str, vehicle: str, owner_name: str, owner_phone: str, complaint: str, tool_context) -> dict:
    """Open a new job card when a vehicle comes in.

    Args:
        plate: number plate, e.g. "MH12 AB 1234".
        vehicle: make/model, e.g. "Splendor Plus".
        owner_name: customer's name.
        owner_phone: customer's phone number, or "" if not given.
        complaint: what the customer wants done, e.g. "clutch slipping, general service".
    """
    def call():
        who, g = _who(tool_context)
        out = jobs.create_job(who, g, _request_id(tool_context), plate, vehicle, owner_name, owner_phone, complaint)
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
    """Move a job to a new stage. Stages: washing, service, waiting_approval, ready.

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
    """Record parts fitted on a job. Takes them out of stock and adds them to the bill.

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
        return {"found": out["found"], "vehicle": out["vehicle"],
                "source": manuals.source_label(out["sources"][0]) if out["sources"] else "",
                "answer_sources": [{"title": h["title"], "page": h["page"], "section": h["section"], "text": h["text"]}
                                   for h in out["sources"]]}

    return _safe(call)


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
    """Send a drafted quote to the customer in their language. Above the garage's quote limit it waits
    for their Approve/Reject (status "pending"); otherwise it is approved straight away.

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
        stage: intake, washing, service, waiting_approval or ready; "" for all.
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
    """One job: vehicle, customer, mechanic, stage, minutes spent in each stage and in total, parts, bill.
    Finds closed jobs by number; open jobs also by plate.

    Args:
        job: job number (e.g. "J-1042" or "1042") or number plate.
    """
    def call():
        who, g = _who(tool_context, "owner")
        j = jobs.find_job(who, g, job)
        minutes = j.get("stage_minutes", {})
        return _job_line(j) | {"complaint": j.get("complaint"), "minutes_per_stage": minutes,
                               "total_minutes": sum(minutes.values()),
                               "parts": [{"name": p["name"], "qty": p["qty"], "total": p["total"]} for p in j.get("parts", [])]}

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
               answer_reorder, lookup_manual]


FAST_TOOLS = [create_job, get_vehicle_history, update_stage, check_stock, log_part_used, close_job, lookup_manual]
