from types import SimpleNamespace

from google.adk.tools.agent_tool import AgentTool

from app import agent, config, tools


def test_live_agent_uses_config_model_and_fast_tools(monkeypatch):
    monkeypatch.setattr(config, "LIVE_MODEL", "test-live-model")
    monkeypatch.setattr(config, "TEXT_MODEL", "test-text-model")
    a = agent.build_live_agent()
    assert a.model == "test-live-model"
    fast = [t for t in a.tools if callable(t) and not isinstance(t, AgentTool)]
    assert {t.__name__ for t in fast} == {f.__name__ for f in tools.FAST_TOOLS}
    subs = {t.agent.name: t.agent for t in a.tools if isinstance(t, AgentTool)}
    assert subs["quote_agent"].model == "test-text-model"
    assert {f.__name__ for f in subs["quote_agent"].tools} == {"describe_photo", "draft_quote"}
    assert {f.__name__ for f in subs["comms_agent"].tools} == {"send_status_link", "send_quote"}
    assert {f.__name__ for f in subs["inventory_agent"].tools} == {"low_stock_report", "ask_owner_to_reorder"}


def test_instruction_reads_session_state():
    ctx = SimpleNamespace(state={"garage_name": "Shree Auto", "name": "Raju", "current_job": "J-1042"})
    text = agent.instruction(ctx)
    assert "Shree Auto" in text and "Raju" in text and "Current job: J-1042" in text


def test_voice_pace_and_voice_come_from_config(monkeypatch):
    from app import gateway

    ctx = SimpleNamespace(state={})
    monkeypatch.setattr(config, "VOICE_PACE", "slower")
    assert "a little slower than normal" in agent.instruction(ctx)
    monkeypatch.setattr(config, "VOICE_PACE", "normal")
    assert "slower" not in agent.instruction(ctx)

    monkeypatch.setattr(config, "LIVE_VOICE", "")
    assert gateway.run_config(False).speech_config is None
    monkeypatch.setattr(config, "LIVE_VOICE", "Charon")
    speech = gateway.run_config(False).speech_config
    assert speech.voice_config.prebuilt_voice_config.voice_name == "Charon"


def test_owner_agent_only_has_owner_tools(monkeypatch):
    from app import gateway

    monkeypatch.setattr(config, "LIVE_MODEL", "test-live-model")
    owner = gateway.agent_for("owner")
    assert owner.name == "owner_copilot" and owner.model == "test-live-model"
    names = {t.__name__ for t in owner.tools}
    assert names == {f.__name__ for f in tools.OWNER_TOOLS}
    assert names & {f.__name__ for f in tools.FAST_TOOLS} == {"lookup_manual", "list_open_jobs"}  # shared, read-only
    assert not any(isinstance(t, AgentTool) for t in owner.tools)
    mechanic = gateway.agent_for("mechanic")
    assert mechanic.name == "garage_copilot"
    assert {getattr(t, "__name__", "") for t in mechanic.tools} & names == {"lookup_manual", "list_open_jobs"}
    text = agent.owner_instruction(SimpleNamespace(state={"garage_name": "Shree Auto", "name": "Asha"}))
    assert "Asha" in text and "Never guess" in text


def test_every_agent_stays_on_topic():
    """C20: a garage assistant, not a general chatbot (it once tutored a teammate on an unrelated subject)."""
    from types import SimpleNamespace

    from app import agent

    ctx = SimpleNamespace(state={"garage_name": "Shree Auto", "name": "Raju", "role": "mechanic", "pinned_lang": ""})
    for build in (agent.instruction, agent.owner_instruction, agent.front_desk_instruction):
        text = build(ctx)
        assert "Stay on topic (strict)" in text and "Never answer the off-topic part" in text
        assert text.index("Stay on topic") < text.index("How to talk") if "How to talk" in text else True
    for sub in (agent.build_quote_agent(), agent.build_comms_agent(), agent.build_inventory_agent()):
        assert "Only do this garage task" in sub.instruction
    assert "Only search for vehicle repair" in agent.WEB_SEARCH_INSTRUCTION
