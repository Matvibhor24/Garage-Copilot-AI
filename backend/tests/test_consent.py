"""C19: the web search runs only after the mechanic's own "yes" to the agent's offer, not the model's word."""

import asyncio
from types import SimpleNamespace

import pytest

from app import consent, seed, tools
from app.services import jobs, manuals, websearch
from tests.helpers import mechanic

G = "shree-auto"


@pytest.mark.parametrize("words", ["yes", "Haan kar do", "ok search it", "ho, chalel", "हाँ कर दो", "theek hai", "sure",
                                   "yes, no problem", "ok no worries", "haan, koi dikkat nahi", "हाँ, कोई बात नहीं",
                                   "हो, काही हरकत नाही", "मतलब हाँ, देख लो", "no problem, ha"])
def test_yes_in_three_languages(words):
    assert consent.agrees(words)


@pytest.mark.parametrize("words", ["no", "nahi rehne do", "nako", "नहीं", "yes... actually no, don't", "", "what is the gap?",
                                   "मत करो", "kya ho raha hai", "pehle plug check kar", "don't do it",
                                   "ok, don't search", "haan... wait, don't", "ok, don’t",
                                   "No. Problem is the manual is wrong, search it", "दिक्कत। नहीं"])
def test_no_or_not_an_answer(words):
    assert not consent.agrees(words)


def test_needs_a_fresh_offer_and_a_yes_after_it():
    assert not consent.allowed("m-raju")  # no offer
    consent.heard("m-raju", "haan", now=100)
    consent.offer("m-raju", "hard start", now=200)
    assert not consent.allowed("m-raju", now=205)  # the yes came before the offer
    consent.heard("m-raju", "nahi", now=210)
    assert not consent.allowed("m-raju", now=211)
    consent.heard("m-raju", "haan, dekh lo", now=212)
    assert consent.allowed("m-raju", now=213)
    assert not consent.allowed("m-raju", now=200 + consent.OFFER_SECONDS + 1)  # offer too old
    consent.clear("m-raju")
    assert not consent.allowed("m-raju", now=213)  # one yes, one search


@pytest.fixture
def garage(fake_db, monkeypatch):
    seed.seed(fake_db)
    jobs.create_job(mechanic(), G, "r1", "MH12AB1234", "Splendor Plus", "Ramesh")
    searched = []

    async def fake_search(question, vehicle, model=None):
        searched.append(question)
        return {"points": ["Choke cable stuck: free and adjust it."], "sites": ["example.org"], "suggestions_html": ""}

    monkeypatch.setattr(websearch, "search", fake_search)
    monkeypatch.setattr(manuals, "lookup", lambda who, g, rid, q, model: {"found": False, "vehicle": model, "sources": []})
    return searched


def ctx(call_id):
    return SimpleNamespace(state={"garage_id": G, "uid": "m-raju", "name": "Raju", "role": "mechanic",
                                  tools.CURRENT_JOB: "J-1042"}, function_call_id=call_id)


def test_the_model_claiming_consent_is_not_enough(garage):
    out = asyncio.run(tools.web_search_fixes("hard to start", "", True, ctx("w1")))
    assert "hasn't said yes" in out["error"] and garage == []


def test_manual_miss_then_the_mechanics_yes_then_one_search(garage):
    assert tools.lookup_manual("hard to start in the morning", "", ctx("m1"))["found"] is False
    consent.agent_said("m-raju", "It isn't in the manual. Shall I search online for known causes and fixes?")
    consent.heard("m-raju", "nahi")
    assert "hasn't said yes" in asyncio.run(tools.web_search_fixes("hard to start", "", True, ctx("w2")))["error"]
    consent.heard("m-raju", "haan search karo")
    out = asyncio.run(tools.web_search_fixes("hard to start", "", True, ctx("w3")))
    assert out["source"] == "web" and garage == ["hard to start"]
    again = asyncio.run(tools.web_search_fixes("hard to start", "", True, ctx("w4")))  # needs a new offer and yes
    assert "hasn't said yes" in again["error"] and garage == ["hard to start"]


def test_a_manual_passage_that_doesnt_answer_still_lets_the_mechanic_say_yes(garage, monkeypatch):
    """The manual matched something (found=True) but not the answer: the agent offers a search, and the yes counts."""
    hit = {"title": "Splendor Plus owner's manual", "page": 12, "section": "Starting", "text": "Turn the key to ON."}
    monkeypatch.setattr(manuals, "lookup", lambda who, g, rid, q, model: {"found": True, "vehicle": model, "sources": [hit]})
    assert tools.lookup_manual("hard to start in the morning", "", ctx("m1"))["found"] is True
    consent.agent_said("m-raju", "मैनुअल में नहीं है। ऑनलाइन देखूँ?")
    consent.heard("m-raju", "haan, koi problem nahi, search karo")
    out = asyncio.run(tools.web_search_fixes("hard to start", "", True, ctx("w1")))
    assert out["source"] == "web" and garage == ["hard to start"]


def test_a_yes_to_some_other_question_after_a_lookup_is_not_consent(garage):
    """The manual answered; the agent asked something else. No search offer was made, so "haan" unlocks nothing."""
    tools.lookup_manual("clutch lever free play", "", ctx("m1"))
    consent.agent_said("m-raju", "10 to 20 mm, Splendor Plus manual page 42. Shall I log the part?")
    consent.heard("m-raju", "haan")
    assert "hasn't said yes" in asyncio.run(tools.web_search_fixes("free play", "", True, ctx("w1")))["error"]


def test_an_answered_offer_stays_put():
    """'Searching online now...' after the yes must not move the offer past the yes."""
    consent.agent_said("m-raju", "Shall I search online?", now=101)
    consent.heard("m-raju", "haan", now=103)
    consent.agent_said("m-raju", "Okay, searching online now", now=104)
    assert consent.allowed("m-raju", now=105)


def test_a_second_offer_can_be_answered_without_a_new_lookup():
    """Live, Oct 18: after one search the agent asked again and every "haa" was refused, because the offer needed a
    fresh manual lookup. Any offer in the agent's words now counts; the yes must still come after it."""
    consent.agent_said("m-raju", "Shall I search online?", now=100)
    consent.heard("m-raju", "haan", now=101)
    consent.clear("m-raju")  # that search ran
    consent.agent_said("m-raju", "क्या मैं फिर से ऑनलाइन सर्च करूँ?", now=110)
    assert not consent.allowed("m-raju", now=111)  # the old yes doesn't count
    consent.heard("m-raju", "Haa", now=112)
    assert consent.allowed("m-raju", now=113)


@pytest.mark.parametrize("words", ["Can you search on web how to fix the right indicator of Pulsar bike?",
                                   "phir se search karo na", "ऑनलाइन सर्च करो", "Google it"])
def test_the_mechanic_asking_for_a_search_is_their_yes(words):
    consent.heard("m-raju", words, now=100)
    assert consent.allowed("m-raju", now=101)
    assert not consent.allowed("m-raju", now=100 + consent.OFFER_SECONDS + 1)


@pytest.mark.parametrize("words", ["search mat karo", "don't search online", "ऑनलाइन मत देखो", "Ramesh is here"])
def test_refusing_a_search_or_other_talk_is_not_asking(words):
    consent.heard("m-raju", words, now=100)
    assert not consent.allowed("m-raju", now=101)


def test_a_no_after_asking_takes_it_back():
    consent.heard("m-raju", "search karo", now=100)
    consent.heard("m-raju", "nahi, rehne do", now=102)
    assert not consent.allowed("m-raju", now=103)


def test_asking_runs_one_search(garage):
    consent.heard("m-raju", "Google karo, right indicator kaam nahi kar raha")
    assert not consent.allowed("m-raju")  # "nahi" in the problem itself reads as a no: the agent asks instead
    consent.heard("m-raju", "online search karo indicator fix")
    out = asyncio.run(tools.web_search_fixes("indicator fix", "", True, ctx("w1")))
    assert out["source"] == "web" and garage == ["indicator fix"]
    again = asyncio.run(tools.web_search_fixes("indicator fix", "", True, ctx("w2")))
    assert "hasn't said yes" in again["error"]
