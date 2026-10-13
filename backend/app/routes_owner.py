"""Owner REST API. The PWA reads most things live from Firestore; these are the actions."""

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import current_owner, current_user
from app.services import inventory, jobs, owner, people

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
def list_jobs(open_only: bool = True, who=Depends(current_owner)):
    return jobs.list_jobs(who, who["garage_id"], open_only)


@router.get("/owner/jobs/{job_id}")
def get_job(job_id: str, who=Depends(current_owner)):
    return jobs.get_job(who, who["garage_id"], job_id)


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
