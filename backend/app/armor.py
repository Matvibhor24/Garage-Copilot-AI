"""Model Armor screening (C18): Google Cloud's check for prompt injection, jailbreaks, malicious URLs, harmful content
and sensitive data, at the points where untrusted text enters or leaves the agents.

An extra layer next to the topic guard (topic.py) and the web-search consent check (consent.py); it changes neither.
- screen_prompt(text, where): text from a person before or after it reached an agent (sanitizeUserPrompt).
- screen_response(text, where): text an agent or the web-search sub-agent produced (sanitizeModelResponse).
Both return {"ok": True | False | None, "reasons": [...]}: False = a filter matched (reasons name the filters, e.g.
"pi_and_jailbreak", "rai", "malicious_uris"), None = Model Armor couldn't be asked (each caller decides whether to fail
open or closed). Every call logs its verdict.

Off when MODEL_ARMOR_TEMPLATE is empty (tests, local dev, until the team creates the template): then no call is made
and everything passes. Called over REST (POST https://modelarmor.<location>.rep.googleapis.com/v1/<template>:
sanitizeUserPrompt) with the google-auth and requests libraries the Google clients already install, so there is no
new dependency. Calls run on their own small thread pool with a timeout, like the topic checks, so a slow Model Armor
can never hold up the threads the voice sessions need.
"""

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from app import config

log = logging.getLogger(__name__)

_pool = ThreadPoolExecutor(max_workers=config.MODEL_ARMOR_WORKERS, thread_name_prefix="armor")
_slots = threading.BoundedSemaphore(config.MODEL_ARMOR_WORKERS)
_session = None
_session_lock = threading.Lock()


def enabled() -> bool:
    return bool(config.MODEL_ARMOR_TEMPLATE)


def _location() -> str:
    """MODEL_ARMOR_LOCATION, else the location in the template's name (projects/p/locations/<loc>/templates/t)."""
    if config.MODEL_ARMOR_LOCATION:
        return config.MODEL_ARMOR_LOCATION
    parts = config.MODEL_ARMOR_TEMPLATE.split("/")
    return parts[parts.index("locations") + 1] if "locations" in parts else "us-central1"


def _authorized_session():
    global _session
    with _session_lock:
        if _session is None:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession

            credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            _session = AuthorizedSession(credentials)
        return _session


def _call(method: str, text: str) -> dict:
    """One sanitize call. Tests replace this function."""
    field = "userPromptData" if method == "sanitizeUserPrompt" else "modelResponseData"
    url = f"https://modelarmor.{_location()}.rep.googleapis.com/v1/{config.MODEL_ARMOR_TEMPLATE}:{method}"
    response = _authorized_session().post(url, json={field: {"text": text}}, timeout=config.MODEL_ARMOR_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def _matched(value) -> bool:
    """Any matchState MATCH_FOUND inside one filter's result (the nesting differs per filter)."""
    if isinstance(value, dict):
        return value.get("matchState") == "MATCH_FOUND" or any(_matched(v) for v in value.values())
    if isinstance(value, list):
        return any(_matched(v) for v in value)
    return False


def verdict(result: dict) -> dict:
    """{"ok", "reasons"} from a sanitize response: filterMatchState MATCH_FOUND means at least one filter matched."""
    sr = result.get("sanitizationResult") or {}
    reasons = sorted(name for name, value in (sr.get("filterResults") or {}).items() if _matched(value))
    if sr.get("filterMatchState") == "MATCH_FOUND":
        return {"ok": False, "reasons": reasons or ["match"]}
    if sr.get("filterMatchState") == "NO_MATCH_FOUND":
        return {"ok": True, "reasons": []}
    return {"ok": None, "reasons": ["no verdict"]}  # e.g. invocationResult FAILURE: treat as "couldn't check"


async def _screen(method: str, text: str, where: str) -> dict:
    if not enabled() or not (text or "").strip():
        return {"ok": True, "reasons": []}
    if not _slots.acquire(blocking=False):
        log.warning("model armor %s %s: too many checks running, not checked", method, where)
        return {"ok": None, "reasons": ["busy"]}
    try:
        work = _pool.submit(_call, method, text[:config.MODEL_ARMOR_MAX_CHARS])
    except Exception:
        _slots.release()
        raise
    work.add_done_callback(lambda _: _slots.release())
    try:
        out = verdict(await asyncio.wait_for(asyncio.wrap_future(work), timeout=config.MODEL_ARMOR_TIMEOUT_SECONDS + 1))
    except Exception as e:
        log.warning("model armor %s %s: not checked (%s)", method, where, e.__class__.__name__)
        return {"ok": None, "reasons": ["error"]}
    level = logging.WARNING if out["ok"] is False else logging.INFO
    log.log(level, "model armor %s %s: ok=%s reasons=%s", method, where, out["ok"], ",".join(out["reasons"]) or "-")
    return out


async def screen_prompt(text: str, where: str) -> dict:
    return await _screen("sanitizeUserPrompt", text, where)


async def screen_response(text: str, where: str) -> dict:
    return await _screen("sanitizeModelResponse", text, where)


def record(who: dict, where: str, reasons: list[str], action: str, text: str = "") -> None:
    """The owner's activity feed gets an "AI safety" line for each flag: what, where, what was done."""
    from app.services import core

    try:
        core.audit(who["garage_id"], who, "armor_flagged",
                   {"where": where, "reasons": reasons, "action": action, "text": (text or "")[:200]})
    except Exception:
        log.exception("could not record a Model Armor flag")
