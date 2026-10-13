"""Run the real ADK runner with scripted models (no Gemini) to check the wiring:
state reaches tools inside an AgentTool sub-agent, and the service layer is hit once."""

import asyncio

from google.adk.agents import Agent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.agent_tool import AgentTool
from google.genai import types

from app import agent, seed, tools
from app.services import core, jobs, quotes
from tests.helpers import mechanic

G = "shree-auto"


class ScriptedLlm(BaseLlm):
    """Replies with the next scripted step: ("call", name, args) or ("say", text)."""

    script: list = []

    async def generate_content_async(self, llm_request, stream=False):
        step = self.script.pop(0)
        if step[0] == "call":
            part = types.Part(function_call=types.FunctionCall(name=step[1], args=step[2]))
        else:
            part = types.Part(text=step[1])
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


def test_quote_sub_agent_through_adk(fake_db):
    seed.seed(fake_db)
    jobs.create_job(mechanic(), G, "r1", "MH12AB1234", "Splendor Plus", "Ramesh")

    quote_agent = agent.build_quote_agent()
    quote_agent.model = ScriptedLlm(model="scripted", script=[
        ("call", "draft_quote", {"parts": ["clutch plate"], "note": "plate worn", "job": ""}),
        ("say", "Q-77, ₹950, needs approval"),
    ])
    live = Agent(name="garage_copilot", instruction=agent.instruction, tools=[AgentTool(agent=quote_agent)],
                 model=ScriptedLlm(model="scripted", script=[
                     ("call", "quote_agent", {"request": "one clutch plate set, plate worn"}),
                     ("say", "Quote sent: ₹950"),
                 ]))

    async def run():
        runner = Runner(app_name="t", agent=live, session_service=InMemorySessionService())
        state = {"garage_id": G, "garage_name": "Shree Auto", "uid": "m-raju", "name": "Raju",
                 "role": "mechanic", tools.CURRENT_JOB: "J-1042"}
        session = await runner.session_service.create_session(app_name="t", user_id="m-raju", state=state)
        msg = types.Content(role="user", parts=[types.Part(text="Show Ramesh the worn plate")])
        return [e async for e in runner.run_async(user_id="m-raju", session_id=session.id, new_message=msg)]

    events = asyncio.run(run())
    final = [p.text for e in events if e.content for p in e.content.parts if p.text]
    assert final[-1] == "Quote sent: ₹950"
    quote = quotes.quote_ref(G, "Q-77").get().to_dict()
    assert quote["total"] == 950 and quote["job_id"] == "J-1042"
    audit = [d.to_dict() for d in core.garage(G).collection("audit_log").stream()]
    assert [a["action"] for a in audit].count("draft_quote") == 1
