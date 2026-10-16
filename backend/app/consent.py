"""Web-search consent (C19): the search for known fixes runs only after the mechanic really said yes.

`web_search_fixes` used to trust the model's `confirmed=True`, which only proves the model *claimed* consent. Now:
1. `lookup_manual` finding nothing records an offer for that mechanic (the agent then asks "Shall I search online?").
2. The gateway passes on what the mechanic actually said next (the input transcription, or typed text).
3. The search runs only if there is a fresh offer (2 minutes) and the mechanic's words after it are a yes in English,
   Hindi or Marathi (Latin or Devanagari) with no "no" in them.

Kept in memory per mechanic: a voice session stays on one Cloud Run instance for its whole WebSocket, and an offer
is only good for two minutes anyway.
"""

import re
import time

OFFER_SECONDS = 120

YES = re.compile(r"\b(yes|yeah|yep|yup|ok|okay|sure|go ahead|search( it)?|do it|please do|haan|haa|han|ha|ho|hoy|"
                 r"ji|chalo|chalega|kar do|karo|kara|kar|dekh lo|dekho|bilkul|theek hai|thik hai|chalel)\b", re.I)
YES_DEVANAGARI = ("हाँ", "हां", "हो", "ठीक", "कर दो", "करो", "करा", "चालेल", "बिल्कुल", "देख लो", "चलो", "जी")
NO = re.compile(r"\b(no|nope|nah|don'?t|do not|not now|nahi|nahin|nai|nako|naka|mat|rehne do|leave it|skip)\b", re.I)
NO_DEVANAGARI = ("नहीं", "नही", "नको", "नाही", "मत", "रहने दो")

_offers: dict[str, dict] = {}  # mechanic uid -> {"question", "at"}
_heard: dict[str, tuple[str, float]] = {}  # mechanic uid -> (last words, when)


def agrees(text: str) -> bool:
    """A yes, and no no: "haan kar do" yes; "nahi, rehne do" no; "yes... actually no" no."""
    t = (text or "").strip()
    if not t:
        return False
    if NO.search(t) or any(w in t for w in NO_DEVANAGARI):
        return False
    return bool(YES.search(t)) or any(w in t for w in YES_DEVANAGARI)


def offer(uid: str, question: str, now: float | None = None) -> None:
    _offers[uid] = {"question": question, "at": time.time() if now is None else now}


def heard(uid: str, text: str, now: float | None = None) -> None:
    if text and text.strip():
        _heard[uid] = (text, time.time() if now is None else now)


def allowed(uid: str, now: float | None = None) -> bool:
    """A fresh offer, and the mechanic's words after it say yes."""
    now = time.time() if now is None else now
    o = _offers.get(uid)
    if not o or now - o["at"] > OFFER_SECONDS:
        return False
    words, at = _heard.get(uid, ("", 0.0))
    return at >= o["at"] and agrees(words)


def clear(uid: str) -> None:
    _offers.pop(uid, None)


def reset() -> None:
    """Tests: forget everything."""
    _offers.clear()
    _heard.clear()
