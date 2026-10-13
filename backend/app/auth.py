"""Auth: Firebase ID tokens with a `garage` custom claim, mechanic PINs, custom tokens.

Claims on every staff user: {garage, role (owner|mechanic), name}.
Customers get a custom token scoped to one job: {garage, job, role: customer}.
"""

import hashlib
import hmac
import os

from fastapi import Header, HTTPException

from app import config
from app.services import core

_app = None


def hash_pin(pin: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 100_000)
    return f"{salt.hex()}:{digest.hex()}"


def check_pin(pin: str, stored: str) -> bool:
    salt_hex, _ = stored.split(":", 1)
    return hmac.compare_digest(hash_pin(pin, bytes.fromhex(salt_hex)), stored)


def _firebase():
    global _app
    import firebase_admin

    if _app is None:
        _app = firebase_admin.initialize_app(options={"projectId": config.GCP_PROJECT} if config.GCP_PROJECT else None)
    return _app


def verify_id_token(token: str) -> dict:
    from firebase_admin import auth

    return auth.verify_id_token(token, app=_firebase())


def custom_token(uid: str, claims: dict) -> str:
    from firebase_admin import auth

    return auth.create_custom_token(uid, claims, app=_firebase()).decode()


def set_claims(uid: str, claims: dict) -> None:
    from firebase_admin import auth

    auth.set_custom_user_claims(uid, claims, app=_firebase())


def claims_from_header(authorization: str) -> dict:
    """Decoded token claims from "Bearer <ID token>". With AUTH_DISABLED=1 (local demo only)
    the token may be "dev:<garage>:<uid>:<role>"."""
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(401, "missing ID token")
    if config.AUTH_DISABLED and token.startswith("dev:"):
        _, garage, uid, role = token.split(":", 3)
        return {"uid": uid, "garage": garage, "role": role, "name": uid}
    try:
        return verify_id_token(token)
    except Exception:
        raise HTTPException(401, "invalid ID token")


def to_actor(claims: dict) -> dict:
    if not claims.get("garage") or claims.get("role") not in ("owner", "mechanic"):
        raise HTTPException(403, "no garage access on this account yet")
    return core.actor(claims["garage"], claims["uid"], claims["role"], claims.get("name", ""))


def current_user(authorization: str = Header("")) -> dict:
    """FastAPI dependency: the signed-in owner or mechanic as a service-layer actor."""
    return to_actor(claims_from_header(authorization))


def current_owner(authorization: str = Header("")) -> dict:
    who = current_user(authorization)
    if who["role"] != "owner":
        raise HTTPException(403, "owner only")
    return who
