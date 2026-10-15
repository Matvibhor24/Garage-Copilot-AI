"""Language guardrails for the voice agents (C11).

Rule: the agent answers in the language of the person's latest turn, unless the screen pinned a language.
Gemini Live follows the instruction; this module adds a light check on the transcriptions: if a turn was heard
in one script and answered in another (Devanagari vs Latin), the gateway logs it and reminds the model once.
Hindi and Marathi share Devanagari, so they can't be told apart here; that is left to the instruction.
"""

import re

PINNED = {"en": "English", "hi": "Hindi", "mr": "Marathi"}  # the voice screens' picker; "" / "auto" = follow the speaker
LANGUAGE_CODES = {"en": "en-IN", "hi": "hi-IN", "mr": "mr-IN"}  # for Live models that accept speech_config.language_code

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
LATIN = re.compile(r"[A-Za-z]")


def pinned(lang: str) -> str:
    """The pinned language code, or "" for Auto (unknown values count as Auto)."""
    return lang if lang in PINNED else ""


def rule(person: str, lang: str = "") -> str:
    """The first and strictest line of an agent's instruction."""
    keep = "Names, number plates, part names and numbers stay as they are."
    if pinned(lang):
        return (f"LANGUAGE (first and strictest rule): always answer in {PINNED[lang]}, whatever language you hear. "
                f"Summarise tool results that are in another language in {PINNED[lang]}. {keep}")
    return f"""LANGUAGE (first and strictest rule): reply in the language of the {person}'s LATEST turn: English ->
English, Hindi -> Hindi, Marathi -> Marathi, Hinglish -> Hinglish (any language you support works the same way).
Never switch on your own: not because the customer speaks another language, not because a tool result or an
earlier turn is in another language. Summarise tool results in another language (e.g. a Marathi quote text) in
the {person}'s language. {keep}
Examples: "Send Ramesh the quote" (English, though Ramesh speaks Marathi) -> answer in English.
"क्लच प्लेट है क्या?" (Hindi) -> answer in Hindi. "Ramesh ka quote bhej do" (Hinglish) -> answer in Hinglish."""


def script(text: str) -> str:
    """"devanagari" or "latin" when the text is clearly in one script (at least 4 letters, 80% of them), else ""."""
    deva, latin = len(DEVANAGARI.findall(text or "")), len(LATIN.findall(text or ""))
    total = deva + latin
    if total < 4:
        return ""
    if deva >= 0.8 * total:
        return "devanagari"
    if latin >= 0.8 * total:
        return "latin"
    return ""


def mismatch(heard: str, said: str) -> bool:
    """True when the reply is clearly in a different script from what was heard (e.g. Hindi in, English out)."""
    a, b = script(heard), script(said)
    return bool(a and b and a != b)


def reminder(heard: str) -> str:
    """One-line note added to the session (without asking for a reply) after a mismatched turn."""
    kind = "Hindi or Marathi (Devanagari)" if script(heard) == "devanagari" else "English or Hinglish (Latin letters)"
    return (f"[system] Your last reply was in a different language from the user's. The user spoke {kind}. "
            "Answer the next turn in the language the user speaks. Do not reply to this note.")
