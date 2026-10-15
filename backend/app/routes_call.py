"""Start a front-desk call (C15). No login: a short-lived caller token for /ws/voice, rate-limited per number."""

from fastapi import APIRouter
from pydantic import BaseModel

from app import config
from app.routes_customer import job_from_token
from app.services import frontdesk, jobs

router = APIRouter(prefix="/api")


class StartCall(BaseModel):
    garage_id: str
    phone: str


def _start(garage_id: str, phone: str, verified: bool, via: str, job_id: str = "") -> dict:
    return frontdesk.start_call(garage_id, phone, verified, via, config.CALLS_PER_PHONE_HOUR,
                                config.CALLS_PER_GARAGE_HOUR, job_id)


@router.post("/call/start")
def start(body: StartCall):
    """From the website: the number is typed in, so the call is not verified (no job details are shared)."""
    return _start(body.garage_id, body.phone, False, "web")


@router.post("/j/{token}/call")
def start_from_status_page(token: str):
    """From the customer's own status link: the link proves the caller may see this job, so the call is verified
    for it, whether or not the job has a phone number on file."""
    garage_id, job_id = job_from_token(token)
    phone = (jobs.job_ref(garage_id, job_id).get().to_dict() or {}).get("phone", "")
    return _start(garage_id, phone, True, "status page", job_id)
