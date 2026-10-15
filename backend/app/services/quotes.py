"""Quotes: draft, send (quote_limit rule), customer approve/reject."""

from app import db, links
from app.services import core, inventory, jobs
from app.services.core import Invalid, NotFound, get_doc


def quote_ref(garage_id: str, quote_id: str):
    return core.garage(garage_id).collection("quotes").document(quote_id)


def draft_quote(who, garage_id, request_id, job_id, parts: list[str], labour: int | None = None, note: str = "",
                with_photo: bool = True):
    """parts: part ids or spoken names, one entry per unit. labour: None = highest usual labour of the parts.
    with_photo: attach the job's latest photo and its caption, if there is one."""
    def work():
        job = get_doc(jobs.job_ref(garage_id, job_id))
        lines = {}
        for spoken in parts:
            item = inventory.resolve(garage_id, spoken, job["vehicle"])
            line = lines.setdefault(item["id"], {"part_id": item["id"], "name": item["name"], "qty": 0,
                                                 "price": item["price"], "labour": item.get("labour", 0)})
            line["qty"] += 1
            # Billable consumables fitted with it (C13), so the customer approves the real total
            for c, need in inventory.fittings(garage_id, item, 1):
                if c.get("billable"):
                    extra = lines.setdefault(c["id"], {"part_id": c["id"], "name": c["name"], "qty": 0,
                                                       "price": c["price"], "labour": 0})
                    extra["qty"] += need
        if not lines:
            raise Invalid("a quote needs at least one part")
        for line in lines.values():
            line["total"] = line["qty"] * line["price"]
        labour_total = labour if labour is not None else max(l["labour"] for l in lines.values())
        parts_total = sum(l["total"] for l in lines.values())
        quote = {
            "job_id": job_id,
            "customer_id": job["customer_id"],
            "lines": [{k: l[k] for k in ("part_id", "name", "qty", "price", "total")} for l in lines.values()],
            "labour": labour_total,
            "total": parts_total + labour_total,
            "quote_limit": jobs.config(garage_id).get("quote_limit", 0),  # shown now; send_quote re-reads it
            "lang": job.get("lang", "en"),
            "note": note,
            "photo": job.get("last_photo") if with_photo else None,
            "photo_caption": job.get("last_photo_caption", "") if with_photo else "",
            "status": "draft",
            "created_at": core.now(),
            "created_by": who["name"],
        }
        quote_id = jobs.next_id(garage_id, "next_quote_no", "Q", "quotes", quote)
        needs_approval = quote["total"] > quote["quote_limit"]
        return {"quote_id": quote_id, "job_id": job_id, "lines": quote["lines"], "labour": labour_total,
                "total": quote["total"], "quote_limit": quote["quote_limit"], "needs_approval": needs_approval,
                "photo_caption": quote["photo_caption"]}, []

    return core.run(who, garage_id, request_id, "draft_quote", work)


def quote_text(job: dict, quote: dict) -> str:
    """Plain itemised quote in English; send_quote translates it into the customer's language."""
    rows = [f"{l['name']} x{l['qty']}: ₹{l['total']}" for l in quote["lines"]]
    rows.append(f"Labour: ₹{quote['labour']}")
    rows.append(f"Total: ₹{quote['total']}")
    if quote.get("photo_caption"):
        rows.append(f"Photo: {quote['photo_caption']}")
    return f"Hi {job['owner']}, quote for your {job['vehicle']}:\n" + "\n".join(rows)


def _apply_labour(garage_id: str, quote: dict) -> None:
    jobs.job_ref(garage_id, quote["job_id"]).update({
        "labour": db.Increment(quote["labour"]),
        "bill": db.Increment(quote["labour"]),
        "pending_quote": None,
    })


def send_quote(who, garage_id, request_id, quote_id):
    """Over the garage's quote_limit (read now, so an owner's change applies to the next quote): send to the
    customer and wait. Otherwise approve straight away ("Approved automatically: within the ₹X limit")."""
    def work():
        quote = get_doc(quote_ref(garage_id, quote_id))
        if quote["status"] != "draft":
            raise Invalid(f"{quote_id} is already {quote['status']}")
        job = get_doc(jobs.job_ref(garage_id, quote["job_id"]))
        at = core.now()
        limit = jobs.config(garage_id).get("quote_limit", 0)  # the owner's current setting, not the draft's copy
        if quote["total"] <= limit:
            quote_ref(garage_id, quote_id).update({"status": "approved", "by": "auto (within quote limit)",
                                                   "auto": True, "quote_limit": limit, "at": at})
            _apply_labour(garage_id, quote)
            return {"quote_id": quote_id, "status": "approved", "auto": True, "total": quote["total"],
                    "quote_limit": limit, "reason": f"within the ₹{limit} limit",
                    "say": f"Approved automatically: within the ₹{limit} limit"}, []
        texts = jobs.customer_texts(quote_text(job, quote), quote["lang"])
        text = texts["text"]
        quote_ref(garage_id, quote_id).update({"status": "pending", "sent_at": at, "quote_limit": limit, **texts})
        jobs.job_ref(garage_id, quote["job_id"]).update({"pending_quote": quote_id})
        message = {
            "to": quote["customer_id"],
            "kind": "quote",
            "job_id": quote["job_id"],
            "quote_id": quote_id,
            "lang": quote["lang"],
            "text": text + f"\n{links.job_url(garage_id, quote['job_id'])}",
            "text_en": texts["text_en"],
            "text_hi": texts["text_hi"],
        }
        reason = f"₹{quote['total']} > ₹{limit} limit"
        return {"quote_id": quote_id, "status": "pending", "total": quote["total"], "reason": reason}, [message]

    return core.run(who, garage_id, request_id, "send_quote", work)


def resend_quote(who, garage_id, request_id, quote_id):
    """Send a pending quote to the customer again (same text, same link), e.g. when they call and ask (C15)."""
    def work():
        quote = get_doc(quote_ref(garage_id, quote_id))
        if quote["status"] != "pending":
            raise Invalid(f"{quote_id} is {quote['status']}")
        message = {"to": quote["customer_id"], "kind": "quote", "job_id": quote["job_id"], "quote_id": quote_id,
                   "lang": quote.get("lang", "en"),
                   "text": quote.get("text", "") + f"\n{links.job_url(garage_id, quote['job_id'])}",
                   "text_en": quote.get("text_en", ""), "text_hi": quote.get("text_hi", "")}
        return {"quote_id": quote_id, "sent": True}, [message]

    return core.run(who, garage_id, request_id, "resend_quote", work)


def decide_quote(who, garage_id, job_id, quote_id, decision: str):
    """Customer taps Approve or Reject. One decision per quote (double taps are no-ops)."""
    if decision not in ("approved", "rejected"):
        raise Invalid("decision must be approved or rejected")

    def work():
        quote = get_doc(quote_ref(garage_id, quote_id))
        if quote["job_id"] != job_id:
            raise NotFound(quote_id)
        if quote["status"] != "pending":
            raise Invalid(f"{quote_id} is {quote['status']}")
        job = get_doc(jobs.job_ref(garage_id, job_id))
        quote_ref(garage_id, quote_id).update({"status": decision, "by": "customer", "at": core.now()})
        if decision == "approved":
            _apply_labour(garage_id, quote)
            text = f"{job['owner']} approved. Go ahead."
        else:
            jobs.job_ref(garage_id, job_id).update({"pending_quote": None})
            text = f"{job['owner']} rejected the quote for {job['vehicle']}. Do not fit the parts."
        message = {"to": job["mechanic_uid"], "kind": f"quote_{decision}", "job_id": job_id,
                   "quote_id": quote_id, "text": text}
        return {"quote_id": quote_id, "status": decision, "total": quote["total"]}, [message]

    # One decision per sent quote: the request id names this quote *and* when it was sent. A bare quote id is not
    # enough: after a re-seed (or any reuse of the id) the old stored decision would be returned without writing,
    # so the customer saw "Approved" while the quote stayed pending.
    sent = get_doc(quote_ref(garage_id, quote_id)).get("sent_at", "")
    return core.run(who, garage_id, f"{quote_id}-{sent}-decision", f"quote_{decision}", work)
