"""C19: the web search runs only after the mechanic's own "yes" to the agent's offer, not the model's word."""

import asyncio
from types import SimpleNamespace

import pytest

from app import consent, seed, tools
from app.services import jobs, manuals, websearch
from tests.helpers import mechanic

G = "shree-auto"


@pytest.mark.parametrize("words", ["yes", "Haan kar do", "ok search it", "ho, chalel", "हाँ कर दो", "theek hai", "sure"])
def test_yes_in_three_languages(words):
    assert consent.agrees(words)


@pytest.mark.parametrize("words", ["no", "nahi rehne do", "nako", "नहीं", "yes... actually no, don't", "", "what is the gap?"])
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
    assert tools.lookup_manual("hard to start in the morning", "", ctx("m1"))["found"] is False  # records the offer
    consent.heard("m-raju", "nahi")
    assert "hasn't said yes" in asyncio.run(tools.web_search_fixes("hard to start", "", True, ctx("w2")))["error"]
    consent.heard("m-raju", "haan search karo")
    out = asyncio.run(tools.web_search_fixes("hard to start", "", True, ctx("w3")))
    assert out["source"] == "web" and garage == ["hard to start"]
    again = asyncio.run(tools.web_search_fixes("hard to start", "", True, ctx("w4")))  # needs a new offer and yes
    assert "hasn't said yes" in again["error"] and garage == ["hard to start"]
