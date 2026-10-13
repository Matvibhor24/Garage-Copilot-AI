"""Customer link endpoints: /api/j/{token}. Read-only except approve/reject."""

from fastapi import APIRouter, HTTPException

from app import links
from app.services import core, jobs, quotes

router = APIRouter(prefix="/api/j")


def job_from_token(token: str) -> tuple[str, str]:
    try:
        return links.read_token(token)
    except links.BadLink as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/{token}")
def status(token: str):
    garage_id, job_id = job_from_token(token)
    return jobs.customer_view(garage_id, job_id)


def _decide(token: str, quote_id: str, decision: str):
    garage_id, job_id = job_from_token(token)
    job = jobs.customer_view(garage_id, job_id)
    customer = core.actor(garage_id, f"customer:{job_id}", "customer", job["owner"])
    return quotes.decide_quote(customer, garage_id, job_id, quote_id, decision)


@router.post("/{token}/quotes/{quote_id}/approve")
def approve(token: str, quote_id: str):
    return _decide(token, quote_id, "approved")


@router.post("/{token}/quotes/{quote_id}/reject")
def reject(token: str, quote_id: str):
    return _decide(token, quote_id, "rejected")
