"""Owner REST API. The PWA reads most things live from Firestore; these are the actions."""

import uuid

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel

from app.auth import current_owner, current_user
from app.services import frontdesk, inventory, jobs, owner, people, reports, settings

router = APIRouter(prefix="/api")


class Restock(BaseModel):
    qty: int
    request_id: str = ""


class Reorder(BaseModel):
    qty: int = 0
    request_id: str = ""


class Invite(BaseModel):
    name: str
    phone: str = ""
    pin: str = ""
    request_id: str = ""


class Estimate(BaseModel):
    total: int | None = None
    request_id: str = ""


class Action(BaseModel):
    request_id: str = ""


class Settings(BaseModel):
    changes: dict
    request_id: str = ""


def rid(request_id: str) -> str:
    return request_id or uuid.uuid4().hex


@router.get("/me")
def me(who=Depends(current_user)):
    return who


@router.get("/jobs")
def staff_jobs(who=Depends(current_user)):
    """Open jobs for any staff member (the mechanic screen's job picker)."""
    return [jobs.compact(j) for j in jobs.list_jobs(who, who["garage_id"])]


@router.get("/owner/dashboard")
def dashboard(who=Depends(current_owner)):
    return owner.dashboard(who, who["garage_id"])


@router.get("/owner/jobs")
def list_jobs(from_: str = Query("", alias="from"), to: str = "", status: str = "", mechanic: str = "", q: str = "",
              cursor: str = "", who=Depends(current_owner)):
    """Owner records (C17): every job, newest first, 50 per page, with totals for the whole filter.
    from/to: check-in dates YYYY-MM-DD (garage local); status: open | closed; mechanic: name or uid;
    q: plate, customer or job id."""
    return reports.jobs_page(who, who["garage_id"], from_, to, status, mechanic, q, cursor)


@router.get("/owner/jobs.csv")
def jobs_csv(from_: str = Query("", alias="from"), to: str = "", status: str = "", mechanic: str = "", q: str = "",
             who=Depends(current_owner)):
    body = reports.jobs_csv(who, who["garage_id"], from_, to, status, mechanic, q)
    return Response(body, media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="garage-jobs.csv"'})


@router.get("/owner/jobs/{job_id}")
def get_job(job_id: str, who=Depends(current_owner)):
    """The job plus its timeline, money, quotes, messages and photos."""
    return reports.job_detail(who, who["garage_id"], job_id)


@router.post("/owner/jobs/{job_id}/status-link")
def resend_status_link(job_id: str, body: Action, who=Depends(current_owner)):
    return jobs.send_status_link(who, who["garage_id"], rid(body.request_id), job_id)


@router.get("/owner/customers")
def customers(q: str = "", who=Depends(current_owner)):
    return reports.customers(who, who["garage_id"], q)


@router.get("/owner/customers/{customer_id}")
def customer(customer_id: str, who=Depends(current_owner)):
    return reports.customer_detail(who, who["garage_id"], customer_id)


@router.get("/owner/vehicles")
def vehicles(q: str = "", who=Depends(current_owner)):
    return reports.vehicles(who, who["garage_id"], q)


@router.get("/owner/vehicles/{plate}")
def vehicle(plate: str, who=Depends(current_owner)):
    return reports.vehicle_detail(who, who["garage_id"], plate)


@router.get("/owner/staff")
def staff(period: str = "week", who=Depends(current_owner)):
    return reports.staff(who, who["garage_id"], period)


@router.post("/owner/mechanics/{uid}/deactivate")
def deactivate(uid: str, body: Action, who=Depends(current_owner)):
    return reports.set_mechanic_active(who, who["garage_id"], rid(body.request_id), uid, False)


@router.post("/owner/mechanics/{uid}/reactivate")
def reactivate(uid: str, body: Action, who=Depends(current_owner)):
    return reports.set_mechanic_active(who, who["garage_id"], rid(body.request_id), uid, True)


@router.get("/owner/inventory")
def list_inventory(low_only: bool = False, who=Depends(current_owner)):
    return inventory.list_inventory(who, who["garage_id"], low_only)


@router.post("/owner/inventory/{part_id}/restock")
def restock(part_id: str, body: Restock, who=Depends(current_owner)):
    return inventory.restock(who, who["garage_id"], rid(body.request_id), part_id, body.qty)


@router.post("/owner/inventory/{part_id}/reorder")
def reorder(part_id: str, body: Reorder, who=Depends(current_owner)):
    return inventory.reorder(who, who["garage_id"], rid(body.request_id), part_id, body.qty)


@router.get("/owner/audit")
def audit(limit: int = 50, who=Depends(current_owner)):
    return owner.audit_log(who, who["garage_id"], limit)


@router.post("/owner/mechanics")
def invite(body: Invite, who=Depends(current_owner)):
    return people.invite_mechanic(who, who["garage_id"], rid(body.request_id), body.name, body.phone, body.pin)


@router.post("/owner/inventory/{part_id}/reorder-later")
def reorder_later(part_id: str, body: Reorder, who=Depends(current_owner)):
    return inventory.reorder_later(who, who["garage_id"], rid(body.request_id), part_id)


@router.get("/owner/settings")
def get_settings(who=Depends(current_owner)):
    return settings.get_settings(who, who["garage_id"])


@router.put("/owner/settings")
def put_settings(body: Settings, who=Depends(current_owner)):
    out = settings.update_settings(who, who["garage_id"], rid(body.request_id), body.changes)
    return out | {"settings": settings.get_settings(who, who["garage_id"])}


@router.get("/owner/calls")
def calls(who=Depends(current_owner)):
    """Front desk (C15): recent calls, open callbacks, estimates to confirm, drop-off bookings."""
    return frontdesk.calls_overview(who, who["garage_id"])


@router.post("/owner/estimates/{estimate_id}/send")
def send_estimate(estimate_id: str, body: Estimate, who=Depends(current_owner)):
    return frontdesk.answer_estimate(who, who["garage_id"], rid(body.request_id), estimate_id, True, body.total)


@router.post("/owner/estimates/{estimate_id}/drop")
def drop_estimate(estimate_id: str, body: Action, who=Depends(current_owner)):
    return frontdesk.answer_estimate(who, who["garage_id"], rid(body.request_id), estimate_id, False)


@router.post("/owner/callbacks/{callback_id}/done")
def callback_done(callback_id: str, body: Action, who=Depends(current_owner)):
    return frontdesk.close_callback(who, who["garage_id"], rid(body.request_id), callback_id)
