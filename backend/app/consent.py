"""Web-search consent (C19): the search for known fixes runs only after the mechanic really said yes.

`web_search_fixes` used to trust the model's `confirmed=True`, which only proves the model *claimed* consent. Now:
1. Every `lookup_manual` by a mechanic records an offer (when the manual has nothing, or its passages don't answer
   the question, the agent asks "Shall I search online?").
2. The gateway passes on what the mechanic actually said next (the input transcription, or typed text).
3. The search runs only if there is a fresh offer (2 minutes) and the mechanic's words after it are a yes in English,
   Hindi or Marathi (Latin or Devanagari) with no "no" in them.

Kept in memory per mechanic: a voice session stays on one Cloud Run instance for its whole WebSocket, and an offer
is only good for two minutes anyway.
"""

import re
import time

OFFER_SECONDS = 120

YES = re.compile(r"\b(yes|yeah|yep|yup|ok|okay|sure|go ahead|search( it)?|do it|please do|haan|haa|hoy|"
                 r"chalo|chalega|kar do|karo|kara|dekh lo|dekho|bilkul|theek hai|thik hai|chalel)\b", re.I)
YES_DEVANAGARI = ("हाँ", "हां", "ठीक", "कर दो", "करो", "करा", "चालेल", "बिल्कुल", "देख लो", "चलो")
# Also everyday words ("kya ho raha hai"), so a yes only as the first word of the answer
YES_FIRST = re.compile(r"^ (ha|han|ho|हो) ", re.I)
NO = re.compile(r"\b(no|nope|nah|don'?t|do not|not now|nahi|nahin|nai|nako|naka|mat|rehne do|leave it|skip)\b", re.I)
NO_DEVANAGARI = ("नहीं", "नही", "नको", "नाही", "मत", "रहने दो")
# Yeses that contain a "no" word: taken out before looking for a no
NO_PROBLEM = re.compile(r"\b(no (problem|problems|worries|issue|issues)|(koi )?(problem|dikkat|baat|chinta|tension) "
                        r"(nahi|nahin|nai)|(kahi )?(harkat|problem) (nahi|nahi re))\b", re.I)
NO_PROBLEM_DEVANAGARI = ("कोई बात नहीं", "कोई दिक्कत नहीं", "कोई प्रॉब्लम नहीं", "दिक्कत नहीं", "चिंता नहीं",
                         "हरकत नाही", "काही हरकत नाही", "प्रॉब्लम नाही")
SPLIT = re.compile(r"[\s,.!?।॥;:'\"()-]+")  # Devanagari matras aren't \w, so its words are matched whole, not by \b

_offers: dict[str, dict] = {}  # mechanic uid -> {"question", "at"}
_heard: dict[str, tuple[str, float]] = {}  # mechanic uid -> (last words, when)


def _has_words(text: str, phrases) -> bool:
    """Whole words or phrases only: "मत" is in "मत करो", not in "मतलब"."""
    return any(f" {p} " in text for p in phrases)


def agrees(text: str) -> bool:
    """A yes, and no no: "haan kar do" yes; "nahi, rehne do" no; "yes... actually no" no; "yes, no problem" yes."""
    t = " " + " ".join(w for w in SPLIT.split(text or "") if w) + " "
    if not t.strip():
        return False
    t = NO_PROBLEM.sub(" ", t)
    for phrase in NO_PROBLEM_DEVANAGARI:
        t = t.replace(f" {phrase} ", " ")
    if NO.search(t) or _has_words(t, NO_DEVANAGARI):
        return False
    return bool(YES.search(t) or YES_FIRST.match(t)) or _has_words(t, YES_DEVANAGARI)


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
