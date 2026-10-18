"""C14: manual first, then (only with the mechanic's OK) a web search for known causes and fixes."""

import asyncio
from types import SimpleNamespace

import pytest
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from app import agent, consent, seed, tools
from app.services import core, jobs, websearch
from tests.helpers import mechanic

G = "shree-auto"


@pytest.fixture
def garage(fake_db, monkeypatch):
    seed.seed(fake_db)
    jobs.create_job(mechanic(), G, "r1", "MH12AB1234", "Splendor Plus", "Ramesh")
    calls = []

    async def fake_search(question, vehicle, model=None):
        calls.append((question, vehicle))
        return {"points": ["Choke cable stuck: free and adjust it.", "Old spark plug: check the gap and replace."],
                "sites": ["bikeservice.example", "mechanicforum.example"], "suggestions_html": "<div>chips</div>"}

    monkeypatch.setattr(websearch, "search", fake_search)
    return calls


def ctx(call_id):
    state = {"garage_id": G, "uid": "m-raju", "name": "Raju", "role": "mechanic", tools.CURRENT_JOB: "J-1042"}
    return SimpleNamespace(state=state, function_call_id=call_id)


def agree():
    """The manual had nothing, the agent asked, and the mechanic said "haan" (C19)."""
    consent.offer("m-raju", "hard to start")
    consent.heard("m-raju", "haan, search karo")


def audit(action):
    return [d.to_dict() for d in core.garage(G).collection("audit_log").stream() if d.to_dict()["action"] == action]


def test_never_searches_without_the_mechanics_yes(garage):
    for confirmed in (False, None, "yes"):
        out = asyncio.run(tools.web_search_fixes("hard to start in the morning", "", confirmed, ctx("w0")))
        assert "Shall I search online" in out["error"]
    assert garage == [] and audit("web_search_fixes") == []


def test_confirmed_search_returns_points_and_sites_and_is_audited(garage):
    agree()
    out = asyncio.run(tools.web_search_fixes("hard to start in the morning", "", True, ctx("w1")))
    assert garage == [("hard to start in the morning", "Splendor Plus")]  # the job's vehicle
    assert out["source"] == "web" and out["sites"] == ["bikeservice.example", "mechanicforum.example"]
    assert len(out["points"]) == 2 and out["note"].startswith("From the web, not the manual")
    assert out["safety"] == ""
    [entry] = audit("web_search_fixes")
    assert entry["details"]["sites"] == out["sites"] and entry["by_name"] == "Raju"
    saved = core.garage(G).collection("web_searches").document("w1").get().to_dict()
    assert saved["suggestions_html"] == "<div>chips</div>"  # Google's search suggestions, kept for the UI
    agree()
    again = asyncio.run(tools.web_search_fixes("hard to start in the morning", "", True, ctx("w1")))
    assert again == out and len(audit("web_search_fixes")) == 1


def test_brakes_fuel_and_electrical_end_with_the_workshop_manual(garage):
    agree()
    out = asyncio.run(tools.web_search_fixes("rear brake squeals", "Splendor Plus", True, ctx("w2")))
    assert out["safety"] == "Check against the workshop manual."
    assert websearch.needs_safety_note("petrol smell near the tank, leak?", [])
    assert websearch.needs_safety_note("EV won't charge", ["check the high-voltage connector"])
    assert not websearch.needs_safety_note("hard to start in the morning", ["choke cable stuck"])


def test_instruction_asks_first_and_the_tools_are_wired():
    text = " ".join(agent.instruction(SimpleNamespace(state={})).split())
    assert 'ASK "Shall I search online for known causes and fixes?"' in text
    assert "confirmed=true" in text and "from the web, not the manual" in text
    assert "check against the workshop manual" in text
    assert tools.web_search_fixes in tools.FAST_TOOLS and tools.web_search_fixes not in tools.OWNER_TOOLS
    sub = agent.build_web_search_agent()
    assert [type(t).__name__ for t in sub.tools] == ["GoogleSearchTool"]  # built-in tool alone on its own agent


class GroundedLlm(BaseLlm):
    """Stands in for Gemini with Google Search grounding."""

    async def generate_content_async(self, llm_request, stream=False):
        assert any(t.google_search for t in llm_request.config.tools)  # the built-in search tool was requested
        meta = types.GroundingMetadata(
            grounding_chunks=[types.GroundingChunk(web=types.GroundingChunkWeb(title="bikeservice.example", uri="u1")),
                              types.GroundingChunk(web=types.GroundingChunkWeb(domain="forum.example", uri="u2")),
                              types.GroundingChunk(web=types.GroundingChunkWeb(title="bikeservice.example", uri="u3"))],
            search_entry_point=types.SearchEntryPoint(rendered_content="<div>suggestions</div>"))
        text = "- Choke stuck: free it.\n- Weak spark: check the plug.\n- Old fuel: drain it.\n- Extra line"
        yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]), grounding_metadata=meta)


def test_the_sub_agent_reads_points_and_site_names():
    out = asyncio.run(websearch.search("hard to start", "Splendor Plus", model=GroundedLlm(model="gemini-2.5-flash")))
    assert out["points"] == ["Choke stuck: free it.", "Weak spark: check the plug.", "Old fuel: drain it."]
    assert out["sites"] == ["bikeservice.example", "forum.example"]
    assert out["suggestions_html"] == "<div>suggestions</div>"


def test_a_lead_in_line_before_the_points_is_dropped():
    text = "Here are common causes and fixes:\n- Burnt bulb: replace it.\n- Bad flasher relay.\n- Loose earth wire.\n- Fourth."
    assert websearch.parse_points(text) == ["Burnt bulb: replace it.", "Bad flasher relay.", "Loose earth wire."]
    assert websearch.parse_points("Just one line.") == ["Just one line."]
