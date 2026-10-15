"""Signed, expiring per-job customer links: /j/{token}. No login needed.

token = base64url(json {g, j, exp}) + "." + base64url(HMAC-SHA256(LINK_SECRET, payload))
"""

import base64
import hashlib
import hmac
import json
import time

from app import config


class BadLink(Exception):
    pass


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload: str) -> str:
    if not config.LINK_SECRET:
        raise RuntimeError("LINK_SECRET is not set")
    return _b64(hmac.new(config.LINK_SECRET.encode(), payload.encode(), hashlib.sha256).digest())


def make_token(garage_id: str, job_id: str, ttl_hours: int | None = None) -> str:
    exp = int(time.time()) + 3600 * (ttl_hours or config.LINK_TTL_HOURS)
    payload = _b64(json.dumps({"g": garage_id, "j": job_id, "exp": exp}, separators=(",", ":")).encode())
    return f"{payload}.{_sign(payload)}"


def read_token(token: str) -> tuple[str, str]:
    """Return (garage_id, job_id) or raise BadLink."""
    try:
        payload, sig = token.split(".", 1)
        ok = hmac.compare_digest(sig, _sign(payload))
        data = json.loads(_unb64(payload))
    except (ValueError, json.JSONDecodeError) as e:
        raise BadLink("malformed link") from e
    if not ok:
        raise BadLink("invalid link")
    if data["exp"] < time.time():
        raise BadLink("link expired")
    return data["g"], data["j"]


def make_caller_token(garage_id: str, phone: str, verified: bool, call_id: str, job_id: str = "") -> str:
    """Short-lived token for one front-desk call (C15): "call." + signed {g, p, v, c, j, exp}.
    j: the job whose status link the call was started from (that link already proves who the caller is)."""
    exp = int(time.time()) + 60 * config.CALL_TOKEN_MINUTES
    payload = _b64(json.dumps({"g": garage_id, "p": phone, "v": verified, "c": call_id, "j": job_id, "exp": exp},
                              separators=(",", ":")).encode())
    return f"call.{payload}.{_sign(payload)}"


def read_caller_token(token: str) -> dict:
    """{garage_id, phone, verified, call_id} or raise BadLink."""
    if not token.startswith("call."):
        raise BadLink("not a call token")
    try:
        payload, sig = token[5:].split(".", 1)
        ok = hmac.compare_digest(sig, _sign(payload))
        data = json.loads(_unb64(payload))
    except (ValueError, json.JSONDecodeError) as e:
        raise BadLink("malformed call token") from e
    if not ok:
        raise BadLink("invalid call token")
    if data["exp"] < time.time():
        raise BadLink("call token expired")
    return {"garage_id": data["g"], "phone": data["p"], "verified": bool(data["v"]), "call_id": data["c"],
            "job_id": data.get("j", "")}


def job_url(garage_id: str, job_id: str) -> str:
    return f"{config.PUBLIC_BASE_URL}/j/{make_token(garage_id, job_id)}"
