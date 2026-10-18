"""Web search for known causes and fixes (C14), only after the manual had nothing and the mechanic said yes.

A small ADK sub-agent on WEB_SEARCH_MODEL with the built-in google_search tool (Gemini grounding with Google
Search). Built-in tools can't share an agent with function tools, so it is its own agent, run here from the Live
agent's `web_search_fixes` function tool (which can enforce `confirmed=True` and write the audit entry).
Lookup, not diagnosis: the answer is 2-3 short "common causes and known fixes" points with the source sites.
"""

import logging
import re

from app.services import core

log = logging.getLogger(__name__)

APP_NAME = "garage_web_search"
SAFETY_WORDS = re.compile(r"\b(brakes?|braking|abs|fuel|petrol|diesel|leak\w*|electric\w*|wiring|battery|ev|"
                          r"high[- ]voltage|short circuit|airbags?)\b", re.I)
SAFETY_NOTE = "Check against the workshop manual."


def needs_safety_note(question: str, points: list[str]) -> bool:
    """Brakes, fuel leaks and electrical / EV high-voltage parts always end with "check against the workshop manual"."""
    return bool(SAFETY_WORDS.search(question + " " + " ".join(points)))


def parse_points(text: str) -> list[str]:
    """The sub-agent answers as "- point" lines; keep at most three, without the dashes."""
    points = [re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip() for line in (text or "").splitlines()]
    return [p for p in points if p][:3]


def site_names(chunks) -> list[str]:
    """Readable source sites from grounding chunks (title holds the site name; else the domain), no repeats."""
    names = []
    for chunk in chunks or []:
        web = getattr(chunk, "web", None)
        name = web and (web.title or web.domain or "")
        if name and name not in names:
            names.append(name)
    return names[:4]


async def search(question: str, vehicle: str, model=None) -> dict:
    """Run the search sub-agent once. Returns {points, sites, suggestions_html}. Tests replace this function."""
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    from app import agent

    search_agent = agent.build_web_search_agent()
    if model is not None:
        search_agent.model = model
    runner = Runner(app_name=APP_NAME, agent=search_agent, session_service=InMemorySessionService())
    session = await runner.session_service.create_session(app_name=APP_NAME, user_id="garage")
    ask = f"Vehicle: {vehicle or 'not given'}. Problem: {question}"
    text, sites, html = "", [], ""
    async for event in runner.run_async(user_id="garage", session_id=session.id,
                                        new_message=types.Content(role="user", parts=[types.Part(text=ask)])):
        if event.content and event.content.parts:
            text += "".join(p.text or "" for p in event.content.parts if not getattr(p, "thought", False))
        meta = getattr(event, "grounding_metadata", None)
        if meta:
            sites = sites or site_names(meta.grounding_chunks)
            entry = getattr(meta, "search_entry_point", None)
            html = html or (entry.rendered_content if entry and entry.rendered_content else "")
    return {"points": parse_points(text), "sites": sites, "suggestions_html": html}


async def screen(who: dict, found: dict) -> dict:
    """Model Armor on the results before the Live agent sees them (C18). Flagged → dropped. Fails closed: if Model
    Armor can't be asked, the results aren't used either. Does nothing when screening is off."""
    import asyncio

    from app import armor

    text = "\n".join(found.get("points", []))
    if not armor.enabled() or not text:
        return found
    screened = await armor.screen_response(text, "web search")
    if screened["ok"] is True:
        return found
    if screened["ok"] is False:
        await asyncio.to_thread(armor.record, who, "web search", screened["reasons"], "results dropped", text)
        note = "results failed a safety check"
    else:
        note = "the search results couldn't be safety-checked, so they weren't used"
    return {"points": [], "sites": [], "suggestions_html": "", "blocked": note}


def record(who: dict, garage_id: str, request_id: str, question: str, vehicle: str, found: dict) -> dict:
    """Audit the search (owner's feed: "Raju searched the web · ...") and return what the agent may say."""
    def work():
        points = found.get("points", [])
        out = {"question": question, "vehicle": vehicle, "found": bool(points), "source": "web",
               "sites": found.get("sites", []), "points": points,
               "note": "From the web, not the manual. Not a diagnosis.",
               "safety": SAFETY_NOTE if needs_safety_note(question, points) else ""}
        if found.get("blocked"):  # Model Armor dropped the results (C18)
            out["note"] = found["blocked"]
        if found.get("suggestions_html"):
            # Google's grounding rules ask apps to show the search suggestions; kept with the search for the UI
            core.garage(garage_id).collection("web_searches").document(request_id).set(
                {"question": question, "vehicle": vehicle, "sites": out["sites"], "at": core.now(),
                 "suggestions_html": found["suggestions_html"]})
        return out, []

    return core.run(who, garage_id, request_id, "web_search_fixes", work)
