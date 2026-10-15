"""C11 language guardrails: the instruction rule, a pinned language reaching the Live config, the script check."""

import asyncio
from types import SimpleNamespace

from google.adk.events import Event
from google.genai import types

from app import agent, config, gateway, language


def ctx(**state):
    return SimpleNamespace(state={"garage_name": "Shree Auto", "name": "Raju"} | state)


def test_language_is_the_first_and_strictest_rule_for_both_agents():
    for text in (agent.instruction(ctx()), agent.owner_instruction(ctx())):
        first_rule = text.split("\n\n")[1]
        assert first_rule.startswith("LANGUAGE (first and strictest rule): reply in the language of the")
        assert "LATEST turn" in first_rule and "Never switch on your own" in first_rule
        assert "though Ramesh speaks Marathi) -> answer in English" in first_rule
        assert "(Hindi) -> answer in Hindi" in first_rule
        assert "Summarise tool results in another language" in first_rule


def test_pinned_language_goes_into_the_instruction():
    text = agent.instruction(ctx(pinned_lang="hi"))
    assert "always answer in Hindi, whatever language you hear" in text and "LATEST turn" not in text
    assert "always answer in Marathi" in agent.owner_instruction(ctx(pinned_lang="mr"))
    assert language.pinned("auto") == "" and language.pinned("fr") == "" and language.pinned("en") == "en"


def test_pinned_language_reaches_the_live_config(monkeypatch):
    assert gateway.run_config(False, "hi").speech_config is None  # native audio (default): instruction only
    monkeypatch.setattr(config, "LIVE_LANGUAGE_CODE", True)
    assert gateway.run_config(False, "hi").speech_config.language_code == "hi-IN"
    assert gateway.run_config(False, "mr").speech_config.language_code == "mr-IN"
    assert gateway.run_config(False, "").speech_config is None  # Auto: nothing pinned
    monkeypatch.setattr(config, "LIVE_VOICE", "Kore")
    both = gateway.run_config(True, "en").speech_config
    assert both.language_code == "en-IN" and both.voice_config.prebuilt_voice_config.voice_name == "Kore"


def test_script_check():
    assert language.script("Do we have a clutch plate?") == "latin"
    assert language.script("क्लच प्लेट है क्या?") == "devanagari"
    assert language.script("Ramesh ka quote bhej do") == "latin"  # Hinglish is Latin script: no false alarm
    assert language.script("ok") == "" and language.script("₹950, 2") == ""
    assert language.mismatch("क्लच प्लेट है क्या?", "Two in stock, ₹650.")
    assert language.mismatch("Do we have a clutch plate?", "हाँ, दो हैं।")
    assert not language.mismatch("क्लच प्लेट है क्या?", "हाँ, दो हैं, ₹650.")
    assert not language.mismatch("हो", "Okay")  # too short to tell


class FakeWS:
    def __init__(self):
        self.sent = []

    async def send_json(self, data):
        self.sent.append(data)

    async def send_bytes(self, data):
        self.sent.append(data)


class FakeQueue:
    def __init__(self):
        self.contents = []

    def send_content(self, content, partial=False):
        self.contents.append((content.parts[0].text, partial))


def turn(heard, said):
    return [Event(author="a", input_transcription=types.Transcription(text=heard, finished=True)),
            Event(author="a", output_transcription=types.Transcription(text=said, finished=True), turn_complete=True)]


async def events(*turns):
    for t in turns:
        for e in t:
            yield e


def run_downstream(state, *turns):
    queue = FakeQueue()
    who = {"garage_id": "g", "uid": "m-raju", "role": "mechanic", "name": "Raju"}
    asyncio.run(gateway.downstream(FakeWS(), events(*turns), who, state, queue))
    return queue.contents


def test_mismatch_adds_one_silent_reminder_for_the_next_turn(caplog):
    reminders = run_downstream({}, turn("क्लच प्लेट है क्या?", "Two in stock, rupees 650."),
                               turn("और ब्रेक शू?", "हाँ, छह हैं।"))
    assert len(reminders) == 1  # only after the mismatched turn
    text, partial = reminders[0]
    assert partial is True  # added to the session without asking Gemini for a reply
    assert text.startswith("[system]") and "Hindi or Marathi" in text
    assert "language mismatch" in caplog.text


def test_no_reminder_when_languages_match_or_a_language_is_pinned():
    assert run_downstream({}, turn("Used one clutch plate", "Logged one clutch plate set.")) == []
    assert run_downstream({"pinned_lang": "en"}, turn("क्लच प्लेट है क्या?", "Two in stock.")) == []
