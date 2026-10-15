"""Garage settings the owner controls from the Settings tab (C09).

Name and city live on the garage doc; the rest on garages/{id}/config/settings, which the services already read
(quote_limit by send_quote at the moment a quote is sent, lang for new customers, supplier and reorder_qty for
reorders, low_at as the low-stock level of parts that don't set their own).
"""

from app import gemini
from app.services import core, inventory, jobs
from app.services.core import Forbidden, Invalid

MAX_QUOTE_LIMIT = 100_000
GARAGE_FIELDS = ("name", "city")
CONFIG_FIELDS = ("quote_limit", "lang", "supplier", "reorder_qty", "low_at")
LABELS = {"quote_limit": "auto-approve limit", "name": "garage name", "city": "city", "lang": "customer language",
          "supplier": "supplier", "reorder_qty": "reorder quantity", "low_at": "low-stock level"}
DEFAULTS = {"quote_limit": 0, "lang": "en", "supplier": "", "reorder_qty": 5, "low_at": 1}


def get_settings(who: dict, garage_id: str) -> dict:
    core.check_tenant(who, garage_id)
    garage_doc = core.garage(garage_id).get().to_dict() or {}
    config = jobs.config(garage_id)
    return ({f: garage_doc.get(f, "") for f in GARAGE_FIELDS}
            | {f: config.get(f, DEFAULTS[f]) for f in CONFIG_FIELDS}
            | {"languages": gemini.LANGUAGES})


def _whole(value, field: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise Invalid(f"{LABELS[field]} must be a whole number")
    try:
        number = float(str(value).replace(",", "").strip())
    except ValueError:
        raise Invalid(f"{LABELS[field]} must be a whole number")
    if number != int(number):
        raise Invalid(f"{LABELS[field]} must be a whole number")
    if not low <= number <= high:
        raise Invalid(f"{LABELS[field]} must be between {low:,} and {high:,}")
    return int(number)


def _text(value, field: str, required: bool) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise Invalid(f"{LABELS[field]} can't be empty")
    if len(text) > 60:
        raise Invalid(f"{LABELS[field]} is too long (60 characters at most)")
    return text


def validate(changes: dict) -> dict:
    """Only known fields; numbers are whole and in range; the language is one we can translate to."""
    unknown = set(changes) - set(GARAGE_FIELDS) - set(CONFIG_FIELDS)
    if unknown:
        raise Invalid(f"unknown setting: {', '.join(sorted(unknown))}")
    clean = {}
    for field, value in changes.items():
        if field == "quote_limit":
            clean[field] = _whole(value, field, 0, MAX_QUOTE_LIMIT)
        elif field == "reorder_qty":
            clean[field] = _whole(value, field, 1, 999)
        elif field == "low_at":
            clean[field] = _whole(value, field, 0, 999)
        elif field == "lang":
            if value not in gemini.LANGUAGES:
                raise Invalid(f"customer language must be one of {', '.join(gemini.LANGUAGES)}")
            clean[field] = value
        else:
            clean[field] = _text(value, field, required=field == "name")
    return clean


def _shown(field: str, value) -> str:
    if field == "quote_limit":
        return f"₹{value:,}"
    if field == "lang":
        return gemini.LANGUAGES.get(value, value)
    return str(value) if value != "" else "(empty)"


def update_settings(who, garage_id, request_id, changes: dict):
    """Save the fields that changed; the audit entry says what changed, e.g.
    "changed the auto-approve limit from ₹500 to ₹0"."""
    def work():
        if who["role"] != "owner":
            raise Forbidden("only the owner can change settings")
        clean = validate(changes)
        before = get_settings(who, garage_id)
        changed = {f: v for f, v in clean.items() if before.get(f) != v}
        garage_part = {f: v for f, v in changed.items() if f in GARAGE_FIELDS}
        config_part = {f: v for f, v in changed.items() if f in CONFIG_FIELDS}
        if garage_part:
            core.garage(garage_id).set(garage_part, merge=True)
        if config_part:
            core.garage(garage_id).collection("config").document("settings").set(config_part, merge=True)
        if "low_at" in changed:
            _refresh_low_stock(garage_id, changed["low_at"])
        lines = [f"the {LABELS[f]} from {_shown(f, before.get(f))} to {_shown(f, v)}" for f, v in changed.items()]
        summary = ("changed " + "; ".join(lines)) if lines else "saved settings (no changes)"
        return {"changes": [{"field": f, "from": before.get(f), "to": v} for f, v in changed.items()],
                "summary": summary}, []

    return core.run(who, garage_id, request_id, "update_settings", work)


def _refresh_low_stock(garage_id: str, low_at: int) -> None:
    """Parts without their own low_at follow the garage's level: recompute their low-stock flag."""
    for snap in core.garage(garage_id).collection("inventory").stream():
        part = snap.to_dict()
        if "low_at" not in part:
            inventory.part_ref(garage_id, snap.id).update({"low_stock": part.get("qty", 0) <= low_at})

