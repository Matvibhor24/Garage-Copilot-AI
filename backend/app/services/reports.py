"""Owner records (C17): jobs (transactions), customers, vehicles and staff, read from the data the garage already has.

Aggregates are computed on read: small garages have a few thousand jobs at most. Everything is in this one module,
so moving to stored daily totals later only changes this file. All dates are the garage's local day
(config timezone, default Asia/Kolkata). Every function checks that the caller is this garage's owner.
"""

import csv
import io
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app import db
from app.services import core, jobs
from app.services.core import Forbidden, NotFound, get_doc

PAGE = 50


def _photo_url(garage_id: str, path: str) -> str:
    from app.services import photos

    return photos.photo_url(garage_id, path)


def _owner(who: dict, garage_id: str) -> None:
    core.check_tenant(who, garage_id)
    if who["role"] != "owner":
        raise Forbidden("owner only")


def _tz(garage_id: str) -> ZoneInfo:
    return ZoneInfo(jobs.config(garage_id).get("timezone", "Asia/Kolkata"))


def _day(iso: str, tz: ZoneInfo) -> date | None:
    return datetime.fromisoformat(iso).astimezone(tz).date() if iso else None


def _all_jobs(garage_id: str) -> list[dict]:
    return [d.to_dict() | {"id": d.id} for d in core.garage(garage_id).collection("jobs").stream()]


def minutes_taken(job: dict, now: str) -> int:
    """Check-in to ready (closed jobs), or so far (open jobs)."""
    done = sum(job.get("stage_minutes", {}).values())
    if job.get("status") == "open" and job.get("stage_started_at"):
        done += max(0, core.minutes_between(job["stage_started_at"], now))
    return done


def period_range(period: str, today: date) -> tuple[date, date]:
    """today | week (Monday to today) | month (1st to today)."""
    if period == "week":
        return today - timedelta(days=today.weekday()), today
    if period == "month":
        return today.replace(day=1), today
    return today, today


def _row(job: dict, tz: ZoneInfo, now: str) -> dict:
    m = jobs.money(job)
    return {
        "job_id": job["id"],
        "date": str(_day(job.get("created_at", ""), tz) or ""),
        "created_at": job.get("created_at", ""),
        "closed_at": job.get("closed_at") or "",
        "vehicle": job.get("vehicle", ""),
        "plate": job.get("plate", ""),
        "customer": job.get("owner", ""),
        "customer_id": job.get("customer_id", ""),
        "mechanic": job.get("mechanic_name", ""),
        "status": "closed" if job.get("status") == "done" else "open",
        "stage": job.get("stage", ""),
        "parts": m["parts"],
        "consumables": m["consumables"],
        "labour": m["labour"],
        "bill": m["bill"],
        "cost": m["cost"],
        "margin": m["margin"],
        "minutes": minutes_taken(job, now),
    }


def _matches(job: dict, tz: ZoneInfo, from_: str, to: str, status: str, mechanic: str, q: str) -> bool:
    day = _day(job.get("created_at", ""), tz)
    if from_ and (not day or str(day) < from_):
        return False
    if to and (not day or str(day) > to):
        return False
    closed = job.get("status") == "done"
    if status == "open" and closed or status == "closed" and not closed:
        return False
    if mechanic and mechanic.lower() not in (job.get("mechanic_name", "").lower(), job.get("mechanic_uid", "").lower()):
        return False
    if q:
        needle = q.strip().lower()
        plate = jobs.normalise_plate(q)
        hay = f"{job['id']} {job.get('owner', '')} {job.get('vehicle', '')}".lower()
        if needle not in hay and not (plate and plate in job.get("plate", "")):
            return False
    return True


def job_rows(who, garage_id, from_="", to="", status="", mechanic="", q="") -> list[dict]:
    """Every job matching the filter, newest first."""
    _owner(who, garage_id)
    tz, now = _tz(garage_id), core.now()
    found = [j for j in _all_jobs(garage_id) if _matches(j, tz, from_, to, status, mechanic, q)]
    found.sort(key=lambda j: (j.get("created_at", ""), j["id"]), reverse=True)
    return [_row(j, tz, now) for j in found]


def totals(rows: list[dict]) -> dict:
    closed = [r for r in rows if r["status"] == "closed"]
    revenue = sum(r["bill"] for r in closed)
    return {
        "jobs": len(rows),
        "closed": len(closed),
        "revenue": revenue,
        "cost": sum(r["cost"] for r in closed),
        "margin": sum(r["margin"] for r in closed),
        "average_bill": round(revenue / len(closed)) if closed else 0,
        "average_minutes": round(sum(r["minutes"] for r in closed) / len(closed)) if closed else 0,
    }


def jobs_page(who, garage_id, from_="", to="", status="", mechanic="", q="", cursor="") -> dict:
    """One page (PAGE rows) plus totals for the whole filter. cursor = the next page's offset."""
    rows = job_rows(who, garage_id, from_, to, status, mechanic, q)
    start = int(cursor) if cursor.isdigit() else 0
    page = rows[start:start + PAGE]
    return {"jobs": page, "totals": totals(rows),
            "next_cursor": str(start + PAGE) if start + PAGE < len(rows) else ""}


CSV_FIELDS = ["date", "job_id", "vehicle", "plate", "customer", "mechanic", "status", "parts", "consumables", "labour",
              "bill", "cost", "margin", "minutes", "closed_at"]


def jobs_csv(who, garage_id, from_="", to="", status="", mechanic="", q="") -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for row in job_rows(who, garage_id, from_, to, status, mechanic, q):
        writer.writerow(row)
    return out.getvalue()


def job_detail(who, garage_id, job_id) -> dict:
    """Everything about one job: the job fields, timeline with time per stage, money, quotes and decisions,
    messages sent, photos (signed URLs)."""
    _owner(who, garage_id)
    job = get_doc(jobs.job_ref(garage_id, job_id))
    stages = sorted((d.to_dict() for d in jobs.job_ref(garage_id, job_id).collection("stages").stream()),
                    key=lambda s: s.get("started_at", ""))
    g = core.garage(garage_id)
    quotes = [d.to_dict() | {"id": d.id} for d in g.collection("quotes").where(
        filter=db.FieldFilter("job_id", "==", job_id)).stream()]
    messages = sorted((d.to_dict() for d in g.collection("messages").where(
        filter=db.FieldFilter("job_id", "==", job_id)).stream()), key=lambda m: m.get("at", ""))
    photos = sorted({p for p in [job.get("last_photo")] + [q.get("photo") for q in quotes] if p})
    return job | {
        "money": jobs.money(job),
        "minutes": minutes_taken(job, core.now()),
        "timeline": [{"name": s["name"], "label": jobs.STAGE_LABELS.get(s["name"], s["name"]),
                      "started_at": s["started_at"], "minutes": s.get("minutes")} for s in stages],
        "quotes": [{k: q.get(k) for k in ("id", "status", "total", "lines", "labour", "note", "by", "at", "sent_at",
                                           "auto", "quote_limit")} for q in quotes],
        "messages": [{k: m.get(k) for k in ("at", "kind", "channel", "to", "text")} for m in messages],
        "photos": [{"path": p, "url": _photo_url(garage_id, p)} for p in photos],
    }


# ---------------------------------------------------------------- customers and vehicles


def _key_phone(phone: str) -> str:
    return "".join(ch for ch in phone or "" if ch.isdigit())[-10:]


def customers(who, garage_id, q: str = "") -> list[dict]:
    """Every customer with their vehicles, visits, total spent and last visit, most recent first."""
    _owner(who, garage_id)
    tz = _tz(garage_id)
    all_jobs = _all_jobs(garage_id)
    out = []
    for snap in core.garage(garage_id).collection("customers").stream():
        c = snap.to_dict() | {"id": snap.id}
        mine = [j for j in all_jobs if j.get("customer_id") == c["id"]]
        last = max((j.get("created_at", "") for j in mine), default="")
        out.append({
            "id": c["id"], "name": c.get("name", ""), "phone": c.get("phone", ""), "lang": c.get("lang", "en"),
            "vehicles": sorted({f"{j.get('vehicle', '')} · {j.get('plate', '')}" for j in mine}),
            "visits": len(mine), "total_spent": sum(j.get("bill", 0) for j in mine if j.get("status") == "done"),
            "last_visit": str(_day(last, tz) or ""), "open_jobs": [j["id"] for j in mine if j.get("status") == "open"],
        })
    if q:
        needle = q.strip().lower()
        out = [c for c in out if needle in c["name"].lower() or _key_phone(q) and _key_phone(q) in _key_phone(c["phone"])
               or any(needle.replace(" ", "") in v.lower().replace(" ", "") for v in c["vehicles"])]
    return sorted(out, key=lambda c: c["last_visit"], reverse=True)


def customer_detail(who, garage_id, customer_id) -> dict:
    _owner(who, garage_id)
    c = get_doc(core.garage(garage_id).collection("customers").document(customer_id))
    tz, now = _tz(garage_id), core.now()
    mine = sorted((j for j in _all_jobs(garage_id) if j.get("customer_id") == customer_id),
                  key=lambda j: j.get("created_at", ""), reverse=True)
    summary = next((x for x in customers(who, garage_id) if x["id"] == customer_id), {})
    return summary | {"name": c.get("name", ""), "phone": c.get("phone", ""), "lang": c.get("lang", "en"),
                      "jobs": [_row(j, tz, now) for j in mine]}


def vehicles(who, garage_id, q: str = "") -> list[dict]:
    """Every plate the garage has seen: model, owner, visits, last service and what was done, total spent."""
    _owner(who, garage_id)
    tz = _tz(garage_id)
    by_plate: dict[str, list[dict]] = {}
    for j in _all_jobs(garage_id):
        if j.get("plate"):
            by_plate.setdefault(j["plate"], []).append(j)
    out = []
    for plate, visits in by_plate.items():
        visits.sort(key=lambda j: j.get("created_at", ""), reverse=True)
        last = visits[0]
        out.append({
            "plate": plate, "vehicle": last.get("vehicle", ""), "owner": last.get("owner", ""),
            "visits": len(visits), "last_visit": str(_day(last.get("created_at", ""), tz) or ""),
            "last_work": last.get("complaint", ""), "last_parts": [p["name"] for p in last.get("parts", [])],
            "total_spent": sum(j.get("bill", 0) for j in visits if j.get("status") == "done"),
            "in_now": any(j.get("status") == "open" for j in visits),
        })
    if q:
        plate, needle = jobs.normalise_plate(q), q.strip().lower()
        out = [v for v in out if (plate and plate in v["plate"]) or needle in v["vehicle"].lower() or needle in v["owner"].lower()]
    return sorted(out, key=lambda v: v["last_visit"], reverse=True)


def last_visit(who, garage_id, plate) -> dict:
    """ "When did MH12AB1234 last come in?" for the owner agent."""
    try:
        v = vehicle_detail(who, garage_id, plate)
    except NotFound:
        return {"plate": jobs.normalise_plate(plate), "found": False}
    last = v["history"][0]
    return {"plate": v["plate"], "found": True, "vehicle": v["vehicle"], "owner": v["owner"], "visits": v["visits"],
            "last_visit": last["date"], "work": last["complaint"], "parts": last["parts_fitted"], "bill": last["bill"],
            "status": last["status"]}


def vehicle_detail(who, garage_id, plate) -> dict:
    """Full service history of one plate (the same jobs get_vehicle_history uses, plus open ones)."""
    _owner(who, garage_id)
    p = jobs.normalise_plate(plate)
    tz, now = _tz(garage_id), core.now()
    visits = sorted((j for j in _all_jobs(garage_id) if j.get("plate") == p), key=lambda j: j.get("created_at", ""),
                    reverse=True)
    if not visits:
        raise NotFound(f"no visits for {p}")
    summary = next(v for v in vehicles(who, garage_id) if v["plate"] == p)
    return summary | {"history": [_row(j, tz, now) | {"complaint": j.get("complaint", ""),
                                                      "parts_fitted": [x["name"] for x in j.get("parts", [])]}
                                  for j in visits]}


# ---------------------------------------------------------------- staff


def staff(who, garage_id, period: str = "week") -> dict:
    """Each mechanic: jobs finished today / this week / this month, open now, average time per job, revenue on their
    jobs, parts logged and last active for the period, plus jobs finished per day (the bar chart)."""
    _owner(who, garage_id)
    if period not in ("today", "week", "month"):
        period = "week"
    tz, now = _tz(garage_id), core.now()
    today = _day(now, tz)
    start, end = period_range(period, today)
    all_jobs = _all_jobs(garage_id)
    audit = [d.to_dict() for d in core.garage(garage_id).collection("audit_log").stream()]
    people = [d.to_dict() | {"uid": d.id} for d in core.garage(garage_id).collection("mechanics").stream()
              if d.to_dict().get("role") == "mechanic"]
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    out = []
    for m in sorted(people, key=lambda p: p.get("name", "")):
        theirs = [j for j in all_jobs if j.get("mechanic_uid") == m["uid"]]
        closed = [j for j in theirs if j.get("status") == "done" and j.get("closed_at")]

        def finished(a, b):
            return [j for j in closed if a <= _day(j["closed_at"], tz) <= b]

        in_period = finished(start, end)
        mine_audit = [a for a in audit if a.get("by_uid") == m["uid"]]
        parts_logged = [a for a in mine_audit if a.get("action") == "log_part_used"
                        and start <= _day(a["at"], tz) <= end]
        out.append({
            "uid": m["uid"], "name": m.get("name", ""), "phone": m.get("phone", ""),
            "active": m.get("active", True),
            "finished": {"today": len(finished(today, today)), "week": len(finished(*period_range("week", today))),
                         "month": len(finished(*period_range("month", today)))},
            "open_now": sum(1 for j in theirs if j.get("status") == "open"),
            "average_minutes": round(sum(minutes_taken(j, now) for j in in_period) / len(in_period)) if in_period else 0,
            "revenue": sum(j.get("bill", 0) for j in in_period),
            "parts_logged": sum(a.get("details", {}).get("qty_used", 1) for a in parts_logged),
            "last_active": max((a["at"] for a in mine_audit), default=""),
            "per_day": [{"day": str(d), "jobs": len(finished(d, d))} for d in days],
        })
    return {"period": period, "from": str(start), "to": str(end), "mechanics": out,
            "count": sum(1 for m in out if m["active"])}


def set_mechanic_active(who, garage_id, request_id, uid: str, active: bool):
    """Deactivate (or bring back) a mechanic: a deactivated mechanic can't sign in; their history stays."""
    from app.services import people

    def work():
        _owner(who, garage_id)
        person = get_doc(people.mechanic_ref(garage_id, uid))
        if person.get("role") != "mechanic":
            raise Forbidden("only mechanics can be deactivated")
        people.mechanic_ref(garage_id, uid).update({"active": active, "active_changed_at": core.now()})
        return {"uid": uid, "name": person.get("name", ""), "active": active}, []

    return core.run(who, garage_id, request_id, "deactivate_mechanic" if not active else "reactivate_mechanic", work)


# ---------------------------------------------------------------- answers for the owner voice agent


def revenue(who, garage_id, period: str = "today") -> dict:
    _owner(who, garage_id)
    today = _day(core.now(), _tz(garage_id))
    start, end = period_range(period, today)
    rows = job_rows(who, garage_id, "", "", "closed")  # closed in the period, whenever they came in
    tz = _tz(garage_id)
    closed = [r for r in rows if start <= _day(r["closed_at"], tz) <= end]
    return {"period": period, "from": str(start), "to": str(end)} | totals(closed)
