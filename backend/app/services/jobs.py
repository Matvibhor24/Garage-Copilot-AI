"""Jobs, stages and garage config."""

import re
from datetime import datetime

from app import db, gemini, links
from app.services import core
from app.services.core import Invalid, NotFound, get_doc

# Stage names in order. Washing comes after the repair, just before delivery (C10). "done" = closed, ready for pickup.
STAGES = ["intake", "service", "waiting_approval", "washing", "ready", "done"]


def config(garage_id: str) -> dict:
    snap = core.garage(garage_id).collection("config").document("settings").get()
    return snap.to_dict() or {}


def job_ref(garage_id: str, job_id: str):
    return core.garage(garage_id).collection("jobs").document(job_id)


def get_job(who: dict, garage_id: str, job_id: str) -> dict:
    core.check_tenant(who, garage_id)
    return get_doc(job_ref(garage_id, job_id))


def find_job(who: dict, garage_id: str, ref: str) -> dict:
    """Find an open job by id ("J-1042", "1042") or plate ("MH12 AB 1234", or its last digits)."""
    core.check_tenant(who, garage_id)
    ref = (ref or "").strip()
    for candidate in (ref, f"J-{ref}"):
        snap = job_ref(garage_id, candidate.upper()).get() if candidate else None
        if snap is not None and snap.exists:
            return snap.to_dict() | {"id": snap.id}
    plate = normalise_plate(ref)
    if plate:
        for job in list_jobs(who, garage_id):
            if job["plate"] == plate or job["plate"].endswith(plate):
                return job
    raise NotFound(f"no open job matching '{ref}'")


def money(job: dict) -> dict:
    """The job's bill split (parts + billable consumables + labour = bill), what the parts and consumables cost
    the garage, and the margin (C13)."""
    lines = job.get("parts", [])
    parts = sum(line["total"] for line in lines if not line.get("consumable"))
    consumables = sum(line["total"] for line in lines if line.get("consumable"))
    labour = job.get("labour", 0)
    cost = sum(line.get("cost", 0) for line in lines) + sum(c.get("cost", 0) for c in job.get("consumables", []))
    bill = parts + consumables + labour
    return {"parts": parts, "consumables": consumables, "labour": labour, "bill": bill, "cost": cost,
            "margin": bill - cost}


COMPACT_FIELDS = ("plate", "vehicle", "owner", "stage", "status", "stage_started_at", "mechanic_name", "bill",
                  "pending_quote", "closed_at", "complaint")


def compact(job: dict) -> dict:
    """The fields a job card on a screen needs."""
    return {"id": job["id"]} | {k: job.get(k) for k in COMPACT_FIELDS} | {"money": money(job)}


def list_jobs(who: dict, garage_id: str, open_only: bool = True) -> list[dict]:
    core.check_tenant(who, garage_id)
    query = core.garage(garage_id).collection("jobs")
    if open_only:
        query = query.where(filter=db.FieldFilter("status", "==", "open"))
    return [d.to_dict() | {"id": d.id} for d in query.stream()]


def next_id(garage_id: str, counter: str, prefix: str, collection: str, data: dict) -> str:
    """Create collection/{prefix}-{n} with a readable running number. Safe under races."""
    g = core.garage(garage_id)
    n = (g.get().to_dict() or {}).get(counter, 1)
    while True:
        doc_id = f"{prefix}-{n}"
        try:
            g.collection(collection).document(doc_id).create(data)
            break
        except db.AlreadyExists:
            n += 1
    g.set({counter: n + 1}, merge=True)
    return doc_id


def normalise_plate(plate: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", plate.upper())


def upsert_customer(garage_id: str, name: str, phone: str, lang: str, default_lang: str = "en") -> tuple[str, str]:
    """(customer_id, their language). A language the mechanic gave wins; otherwise a returning customer keeps theirs
    and a new one gets the garage default (English unless the owner changed it in Settings)."""
    key = re.sub(r"\D", "", phone) or re.sub(r"\W", "", name.lower())
    customer_id = f"c-{key}"
    ref = core.garage(garage_id).collection("customers").document(customer_id)
    customer_lang = lang or (ref.get().to_dict() or {}).get("lang") or default_lang or "en"
    ref.set({"name": name, "phone": phone, "lang": customer_lang}, merge=True)
    return customer_id, customer_lang


def customer_texts(text_en: str, lang: str) -> dict:
    """A customer message in their language for WhatsApp, plus English and Hindi for the status page's switch (C12).
    Translated once, when the message is sent."""
    text_hi = gemini.translate(text_en, "hi")
    text = text_en if lang in ("", "en") else text_hi if lang == "hi" else gemini.translate(text_en, lang)
    return {"text": text, "text_en": text_en, "text_hi": text_hi}


def bill_of(job: dict) -> int:
    return sum(line["total"] for line in job.get("parts", [])) + job.get("labour", 0)


def status_link_message(garage_id: str, job_id: str, job: dict) -> dict:
    garage_name = (core.garage(garage_id).get().to_dict() or {}).get("name", "the garage")
    text_en = (f"Hi {job['owner']}, your {job['vehicle']} is checked in at {garage_name}. "
               f"Track it: {links.job_url(garage_id, job_id)}")
    return {"to": job["customer_id"], "kind": "status_link", "job_id": job_id, "lang": job.get("lang", "en"),
            **customer_texts(text_en, job.get("lang", "en"))}


def send_status_link(who, garage_id, request_id, job_id):
    """(Re)send the customer their live status link."""
    def work():
        job = get_doc(job_ref(garage_id, job_id))
        return {"job_id": job_id, "sent_to": job["owner"]}, [status_link_message(garage_id, job_id, job)]

    return core.run(who, garage_id, request_id, "send_status_link", work)


def create_job(who, garage_id, request_id, plate, vehicle, owner_name, phone="", complaint="", lang=""):
    def work():
        settings = config(garage_id)
        at = core.now()
        customer_id, customer_lang = upsert_customer(garage_id, owner_name, phone, lang, settings.get("lang", "en"))
        job = {
            "plate": normalise_plate(plate),
            "vehicle": vehicle,
            "owner": owner_name,
            "phone": phone,
            "customer_id": customer_id,
            "lang": customer_lang,
            "complaint": complaint,
            "stage": "intake",
            "stage_started_at": at,
            "stage_no": 1,
            "stage_minutes": {},
            "status": "open",
            "mechanic_uid": who["uid"],
            "mechanic_name": who["name"],
            "created_at": at,
            "quote_limit": settings.get("quote_limit", 0),
            "parts": [],
            "labour": 0,
            "bill": 0,
        }
        job_id = next_id(garage_id, "next_job_no", "J", "jobs", job)
        job_ref(garage_id, job_id).collection("stages").document("s1").set({"name": "intake", "started_at": at})
        message = status_link_message(garage_id, job_id, job)
        return {"job_id": job_id, "plate": job["plate"], "owner": owner_name, "stage": "intake"}, [message]

    return core.run(who, garage_id, request_id, "create_job", work)


def _move_stage(garage_id: str, job: dict, stage: str, at: str) -> int:
    """Close the current stage, open the next. Returns minutes spent in the previous stage."""
    ref = job_ref(garage_id, job["id"])
    minutes = core.minutes_between(job["stage_started_at"], at)
    stages = ref.collection("stages")
    stages.document(f"s{job['stage_no']}").set({"ended_at": at, "minutes": minutes}, merge=True)
    stages.document(f"s{job['stage_no'] + 1}").set({"name": stage, "started_at": at})
    ref.update({
        "stage": stage,
        "stage_started_at": at,
        "stage_no": db.Increment(1),
        f"stage_minutes.{job['stage']}": minutes,
    })
    return minutes


def update_stage(who, garage_id, request_id, job_id, stage):
    def work():
        if stage not in STAGES or stage == "done":
            raise Invalid(f"stage must be one of {STAGES[:-1]}; use close_job to finish")
        job = get_doc(job_ref(garage_id, job_id))
        if job["status"] != "open":
            raise Invalid(f"{job_id} is already closed")
        previous = job["stage"]
        minutes = _move_stage(garage_id, job, stage, core.now())
        return {"job_id": job_id, "stage": stage, "previous_stage": previous, "previous_minutes": minutes}, []

    return core.run(who, garage_id, request_id, "update_stage", work)


def close_job(who, garage_id, request_id, job_id):
    def work():
        job = get_doc(job_ref(garage_id, job_id))
        if job["status"] != "open":
            raise Invalid(f"{job_id} is already closed")
        at = core.now()
        _move_stage(garage_id, job, "done", at)
        bill = bill_of(job)
        job_ref(garage_id, job_id).update({"status": "done", "closed_at": at, "bill": bill})
        message = {
            "to": job["customer_id"],
            "kind": "final_bill",
            "job_id": job_id,
            "lang": job.get("lang", "en"),
            **customer_texts(f"Hi {job['owner']}, your {job['vehicle']} is ready for pickup. Final bill: ₹{bill}.",
                             job.get("lang", "en")),
        }
        return {"job_id": job_id, "stage": "done", "bill": bill, "parts": job["parts"], "labour": job["labour"]}, [message]

    return core.run(who, garage_id, request_id, "close_job", work)


STAGE_LABELS = {"intake": "Checked in", "service": "In service", "waiting_approval": "Waiting for your approval",
                "washing": "Washing", "ready": "Ready for pickup", "done": "Ready for pickup"}


def _with_photo_url(garage_id: str, quote: dict) -> dict:
    from app.services import photos

    if quote.get("photo"):
        quote["photo_url"] = photos.photo_url(garage_id, quote["photo"])  # never fails the customer page (C21)
    return quote


def customer_view(garage_id: str, job_id: str) -> dict:
    """What the customer status page shows. Caller has already verified the signed link."""
    job = get_doc(job_ref(garage_id, job_id))
    stages = sorted((d.to_dict() for d in job_ref(garage_id, job_id).collection("stages").stream()),
                    key=lambda s: s["started_at"])
    garage_doc = core.garage(garage_id).get().to_dict() or {}
    quotes = core.garage(garage_id).collection("quotes").where(filter=db.FieldFilter("job_id", "==", job_id))
    sent = core.garage(garage_id).collection("messages").where(filter=db.FieldFilter("job_id", "==", job_id))
    messages = sorted(({"kind": m["kind"], "at": m["at"], "text_en": m.get("text_en") or m["text"],
                        "text_hi": m.get("text_hi") or m["text"]}
                       for m in (d.to_dict() for d in sent.stream()) if m.get("to") == job["customer_id"]),
                      key=lambda m: m["at"])
    return {
        "garage": garage_doc.get("name", ""),
        "job_id": job_id,
        "vehicle": job["vehicle"],
        "plate": job["plate"],
        "owner": job["owner"],
        "stage": job["stage"],
        "stage_label": STAGE_LABELS.get(job["stage"], job["stage"]),
        "status": job["status"],
        "timeline": [{"name": s["name"], "label": STAGE_LABELS.get(s["name"], s["name"]),
                      "started_at": s["started_at"], "minutes": s.get("minutes")} for s in stages],
        "quotes": [_with_photo_url(garage_id, d.to_dict() | {"id": d.id}) for d in quotes.stream()],
        "parts": [{k: p[k] for k in ("name", "qty", "price", "total")} for p in job.get("parts", [])],
        "labour": job.get("labour", 0),
        "bill": job.get("bill", 0),
        "messages": messages,  # what the garage sent this customer, in English and Hindi (C12)
    }


def _months_between(start: str, end: str) -> int:
    a, b = datetime.fromisoformat(start), datetime.fromisoformat(end)
    return max(0, round((b - a).days / 30.44))


def vehicle_history(who, garage_id, request_id, plate):
    """Past closed jobs for a plate, newest first, with a one-line summary for the agent to say."""
    def work():
        at = core.now()
        query = core.garage(garage_id).collection("jobs").where(
            filter=db.FieldFilter("plate", "==", normalise_plate(plate)))
        past = sorted((d.to_dict() | {"id": d.id} for d in query.stream() if d.to_dict().get("status") == "done"),
                      key=lambda j: j.get("closed_at", ""), reverse=True)
        visits = [{
            "job_id": j["id"],
            "date": j.get("closed_at", "")[:10],
            "months_ago": _months_between(j["closed_at"], at) if j.get("closed_at") else None,
            "complaint": j.get("complaint", ""),
            "parts": [p["name"] for p in j.get("parts", [])],
            "bill": j.get("bill", 0),
        } for j in past]
        if visits:
            last = visits[0]
            parts = f" ({', '.join(last['parts'])})" if last["parts"] else ""
            summary = f"Last visit {last['months_ago']} months ago: {last['complaint']}{parts}."
        else:
            summary = "First visit to this garage."
        return {"plate": normalise_plate(plate), "visits": visits, "summary": summary}, []

    return core.run(who, garage_id, request_id, "get_vehicle_history", work)
