"""Owners and mechanics: invites, PIN check, phone -> garage lookup for claims."""

import re

from app import db
from app.auth import check_pin, hash_pin
from app.services import core
from app.services.core import Forbidden, NotFound, get_doc

MAX_PIN_FAILS = 5


def mechanic_ref(garage_id: str, uid: str):
    return core.garage(garage_id).collection("mechanics").document(uid)


def phone_ref(phone: str):
    """Top-level index phone -> {garage_id, uid}, so a first phone-OTP sign-in can find its garage."""
    return db.client().collection("phone_index").document(re.sub(r"[^\d+]", "", phone))


def invite_mechanic(who, garage_id, request_id, name, phone="", pin=""):
    def work():
        if who["role"] != "owner":
            raise Forbidden("only the owner can invite mechanics")
        uid = "m-" + re.sub(r"\W", "", name.lower())
        doc = {"name": name, "role": "mechanic", "phone": phone}
        if pin:
            doc["pin_hash"] = hash_pin(pin)
        mechanic_ref(garage_id, uid).set(doc, merge=True)
        if phone:
            phone_ref(phone).set({"garage_id": garage_id, "uid": uid, "role": "mechanic", "name": name})
        return {"uid": uid, "name": name, "phone": phone, "has_pin": bool(pin)}, []

    return core.run(who, garage_id, request_id, "invite_mechanic", work)


def check_mechanic_pin(garage_id: str, name: str, pin: str) -> dict:
    """Shared garage phone login. Returns the mechanic (uid, name, role) or raises Forbidden."""
    uid = "m-" + re.sub(r"\W", "", name.lower())
    ref = mechanic_ref(garage_id, uid)
    try:
        person = get_doc(ref)
    except NotFound:
        raise Forbidden("wrong name or PIN")
    if person.get("pin_fails", 0) >= MAX_PIN_FAILS:
        raise Forbidden("too many wrong PINs; ask the owner to reset")
    if not person.get("pin_hash") or not check_pin(pin, person["pin_hash"]):
        ref.update({"pin_fails": db.Increment(1)})
        raise Forbidden("wrong name or PIN")
    ref.update({"pin_fails": 0})
    return {"uid": uid, "name": person["name"], "role": person.get("role", "mechanic")}


def lookup_phone(phone: str) -> dict:
    snap = phone_ref(phone).get()
    if not snap.exists:
        raise Forbidden("this phone number has not been invited by a garage")
    return snap.to_dict()
