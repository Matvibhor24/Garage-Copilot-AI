"""Sign-in helpers that hand out Firebase custom tokens / claims."""

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app import auth, config
from app.routes_customer import job_from_token
from app.services import core, people

router = APIRouter(prefix="/api")


class PinLogin(BaseModel):
    garage_id: str
    name: str
    pin: str


@router.post("/auth/pin")
def pin_login(body: PinLogin):
    """Shared garage phone: name + PIN -> Firebase custom token with the garage claim."""
    try:
        m = people.check_mechanic_pin(body.garage_id, body.name, body.pin)
    except core.Forbidden as e:
        raise HTTPException(401, str(e))
    claims = {"garage": body.garage_id, "role": m["role"], "name": m["name"]}
    if config.AUTH_DISABLED:  # local development without Firebase: a dev token the API accepts
        return {"dev_token": f"dev:{body.garage_id}:{m['uid']}:{m['role']}", "claims": claims}
    return {"custom_token": auth.custom_token(f"{body.garage_id}:{m['uid']}", claims), "claims": claims}


@router.post("/auth/claim")
def claim(authorization: str = Header("")):
    """After a first phone-OTP sign-in: attach the garage claim from the owner's invite.
    The client then refreshes its ID token."""
    token = auth.claims_from_header(authorization)
    phone = token.get("phone_number")
    if not phone:
        raise HTTPException(400, "sign in with phone OTP first")
    try:
        invite = people.lookup_phone(phone)
    except core.Forbidden as e:
        raise HTTPException(403, str(e))
    claims = {"garage": invite["garage_id"], "role": invite["role"], "name": invite["name"]}
    auth.set_claims(token["uid"], claims)
    return {"claims": claims}


@router.post("/j/{token}/session")
def customer_session(token: str):
    """Custom token that lets the customer page listen live to its one job (see firestore.rules)."""
    garage_id, job_id = job_from_token(token)
    claims = {"garage": garage_id, "job": job_id, "role": "customer"}
    return {"custom_token": auth.custom_token(f"customer:{garage_id}:{job_id}", claims)}
