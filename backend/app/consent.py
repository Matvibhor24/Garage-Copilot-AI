"""Web-search consent (C19): the search for known fixes runs only after the mechanic really said yes.

`web_search_fixes` used to trust the model's `confirmed=True`, which only proves the model *claimed* consent. Now:
1. The gateway passes on the agent's own words: when it talks about searching online, that is the offer.
2. The gateway passes on what the mechanic actually said (the input transcription, or typed text).
3. The search runs only if there is a fresh offer (2 minutes) and the mechanic's words after it are a yes in English,
   Hindi or Marathi (Latin or Devanagari) with no "no" in them, or if the mechanic asked for an online search in
   their own words ("search karo", "Google it"), with no "no" in them.
Oct 18: the offer used to need a fresh manual lookup first, so a second "shall I search online?" (or a mechanic
asking for a search outright) could never be answered with a yes.

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
SEP = r"\s,.!?।॥;:\"()\-"  # word separators; not the apostrophe, so "don't" stays one word
SPLIT = re.compile(rf"[{SEP}]+")  # Devanagari matras aren't \w, so its words are matched whole, not by \b
# Yeses that contain a "no" word: taken out before looking for a no. Matched before punctuation is dropped, so
# "No. Problem is the manual" keeps its no.
NO_PROBLEM = re.compile(rf"(?<![^{SEP}])(no (problem|problems|worries|issue|issues)|(koi )?(problem|dikkat|baat|"
                        rf"chinta|tension) (nahi|nahin|nai)|(kahi )?harkat nahi|(कोई )?(बात|दिक्कत|प्रॉब्लम|चिंता) "
                        rf"(नहीं|नही)|(काही )?(हरकत|प्रॉब्लम) नाही)(?![^{SEP}])", re.I)
# The agent talking about looking it up online (in any of the three languages): its search offer
OFFER_WORDS = re.compile(r"search|online|internet|web|google|सर्च|ऑनलाइन|इंटरनेट|वेब|गूगल|शोध|खोज", re.I)

_lookups: dict[str, dict] = {}  # mechanic uid -> {"question", "at"} of their last manual lookup
_asked: dict[str, float] = {}  # mechanic uid -> when they asked for an online search themselves
_offers: dict[str, dict] = {}  # mechanic uid -> {"question", "at"}
_heard: dict[str, tuple[str, float]] = {}  # mechanic uid -> (last words, when)


def _has_words(text: str, phrases) -> bool:
    """Whole words or phrases only: "मत" is in "मत करो", not in "मतलब"."""
    return any(f" {p} " in text for p in phrases)


def agrees(text: str) -> bool:
    """A yes, and no no: "haan kar do" yes; "nahi, rehne do" no; "yes... actually no" no; "yes, no problem" yes."""
    t = NO_PROBLEM.sub(" ", " ".join((text or "").replace("’", "'").split()))
    t = " " + " ".join(w for w in SPLIT.split(t) if w) + " "
    if not t.strip():
        return False
    if NO.search(t) or _has_words(t, NO_DEVANAGARI):
        return False
    return bool(YES.search(t) or YES_FIRST.match(t)) or _has_words(t, YES_DEVANAGARI)


def looked_up(uid: str, question: str, now: float | None = None) -> None:
    _lookups[uid] = {"question": question, "at": time.time() if now is None else now}


def agent_said(uid: str, text: str, now: float | None = None) -> None:
    """The agent's words so far this turn. Talking about an online search is the offer. An offer already answered
    with a yes stays put, so "Searching online now..." after the yes doesn't move it past the yes."""
    now = time.time() if now is None else now
    if OFFER_WORDS.search(text or "") and not allowed(uid, now):
        lookup = _lookups.get(uid)
        offer(uid, lookup["question"] if lookup else "", now)


def offer(uid: str, question: str, now: float | None = None) -> None:
    _offers[uid] = {"question": question, "at": time.time() if now is None else now}


def _words(text: str) -> str:
    return " " + " ".join(w for w in SPLIT.split(" ".join((text or "").replace("’", "'").split())) if w) + " "


def _says_no(text: str) -> bool:
    t = _words(NO_PROBLEM.sub(" ", text or ""))
    return bool(NO.search(t)) or _has_words(t, NO_DEVANAGARI)


def asks_to_search(text: str) -> bool:
    """The mechanic asking for an online search outright ("search karo", "Google it", "ऑनलाइन देखो"), not refusing one."""
    return bool(OFFER_WORDS.search(text or "")) and not _says_no(text)


def heard(uid: str, text: str, now: float | None = None) -> None:
    if text and text.strip():
        now = time.time() if now is None else now
        _heard[uid] = (text, now)
        if asks_to_search(text):
            _asked[uid] = now
        elif _says_no(text):
            _asked.pop(uid, None)  # "nahi, rehne do" after asking takes it back


def allowed(uid: str, now: float | None = None) -> bool:
    """The mechanic asked for a search in the last 2 minutes, or a fresh offer and their words after it say yes."""
    now = time.time() if now is None else now
    if now - _asked.get(uid, float("-inf")) <= OFFER_SECONDS:
        return True
    o = _offers.get(uid)
    if not o or now - o["at"] > OFFER_SECONDS:
        return False
    words, at = _heard.get(uid, ("", 0.0))
    return at >= o["at"] and agrees(words)


def clear(uid: str) -> None:
    _offers.pop(uid, None)
    _lookups.pop(uid, None)
    _asked.pop(uid, None)


def reset() -> None:
    """Tests: forget everything."""
    _offers.clear()
    _lookups.clear()
    _heard.clear()
    _asked.clear()
