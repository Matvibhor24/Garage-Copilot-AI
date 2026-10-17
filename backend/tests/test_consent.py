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


def test_the_offer_is_made_once_per_lookup():
    """'Searching online now...' after the yes must not move the offer past the yes."""
    consent.looked_up("m-raju", "hard start", now=100)
    consent.agent_said("m-raju", "Shall I search online?", now=101)
    consent.heard("m-raju", "haan", now=103)
    consent.agent_said("m-raju", "Okay, searching online now", now=104)
    assert consent.allowed("m-raju", now=105)
    consent.agent_said("m-raju", "Shall I search online?", now=100 + consent.OFFER_SECONDS + 1)  # lookup too old
    consent.clear("m-raju")
    consent.agent_said("m-raju", "Shall I search online?", now=110)  # no lookup since the search: no offer
    assert not consent.allowed("m-raju", now=111)
