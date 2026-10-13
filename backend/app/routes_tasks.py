"""Endpoints for Cloud Scheduler. Auth: Google-signed OIDC token from SCHEDULER_SA_EMAIL."""

from fastapi import APIRouter, Header, HTTPException

from app import config
from app.services import nudges

router = APIRouter(prefix="/api/tasks")


def verify_scheduler(token: str) -> dict:
    from google.auth.transport import requests
    from google.oauth2 import id_token

    return id_token.verify_oauth2_token(token, requests.Request(), audience=config.SCHEDULER_AUDIENCE)


@router.post("/sweep")
def sweep(authorization: str = Header("")):
    try:
        claims = verify_scheduler(authorization.removeprefix("Bearer ").strip())
    except Exception:
        raise HTTPException(401, "invalid scheduler token")
    if not config.SCHEDULER_SA_EMAIL or claims.get("email") != config.SCHEDULER_SA_EMAIL:
        raise HTTPException(403, "not the scheduler service account")
    return nudges.sweep()
