"""Voice gateway with Gemini replaced by a scripted stub that reads the LiveRequestQueue."""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from google.adk.events import Event, EventActions
from google.genai import types

from app import auth, gateway, notify, seed, tools
from app.main import app
from app.services import core, voice

G = "shree-auto"
RAJU = {"uid": "m-raju", "garage": G, "role": "mechanic", "name": "Raju"}


async def scripted_gemini(state, queue, push_to_talk):
    """Echo mic audio; turn typed text into tool calls; repeat [notice] lines."""
    calls = 0
    while True:
        req = await queue.get()
        if req.close:
            return
        if req.blob:
            yield Event(author="garage_copilot", content=types.Content(
                role="model", parts=[types.Part(inline_data=types.Blob(data=req.blob.data[::-1], mime_type="audio/pcm;rate=24000"))]))
        elif req.content:
            text = req.content.parts[0].text
            calls += 1
            ctx = SimpleNamespace(state=dict(state), function_call_id=f"call-{calls}")
            if text.startswith("[notice]"):
                yield Event(author="garage_copilot", output_transcription=types.Transcription(text=text[9:], finished=True),
                            turn_complete=True)
                continue
            result = tools.create_job("MH12 AB 1234", "Splendor Plus", "Ramesh", "", "clutch slipping", ctx)
            yield Event(author="garage_copilot",
                        content=types.Content(role="user", parts=[types.Part(function_response=types.FunctionResponse(
                            name="create_job", response=result))]),
                        actions=EventActions(state_delta={"current_job": ctx.state["current_job"]}))
            yield Event(author="garage_copilot", input_transcription=types.Transcription(text=text, finished=True))
            yield Event(author="garage_copilot", output_transcription=types.Transcription(text="Job open", finished=True),
                        turn_complete=True)


@pytest.fixture
def client(fake_db, monkeypatch):
    seed.seed(fake_db)
    monkeypatch.setattr(auth, "verify_id_token", lambda t: RAJU if t == "raju" else (_ for _ in ()).throw(ValueError()))
    monkeypatch.setattr(gateway, "live_events", scripted_gemini)
    monkeypatch.setattr(gateway, "NOTICE_POLL_SECONDS", 0.05)
    return TestClient(app)


def receive_until(ws, kind):
    seen = []
    while True:
        msg = ws.receive()
        if msg.get("bytes") is not None:
            seen.append(("audio", msg["bytes"]))
            if kind == "audio":
                return seen
            continue
        data = json.loads(msg["text"])
        seen.append((data["type"], data))
        if data["type"] == kind:
            return seen


def test_rejects_bad_token(client):
    with client.websocket_connect("/ws/voice?token=nope") as ws:
        msg = ws.receive()
        assert msg["type"] == "websocket.close" and msg["code"] == 4401


def test_audio_tools_state_and_notices(client):
    with client.websocket_connect("/ws/voice?token=raju") as ws:
        ws.send_bytes(b"\x01\x02\x03")
        assert receive_until(ws, "audio")[-1] == ("audio", b"\x03\x02\x01")
        ws.send_json({"type": "text", "text": "New bike, Splendor Plus, MH12 AB 1234, owner Ramesh"})
        seen = receive_until(ws, "turn_complete")
        tool = next(d for k, d in seen if k == "tool")
        assert tool["name"] == "create_job" and tool["result"]["job_id"] == "J-1042"
        assert voice.session_ref(G, "m-raju").get().to_dict()["current_job"] == "J-1042"

        notify.notify(G, "m-raju", "Ramesh approved. Go ahead.", kind="quote_approved")
        seen = receive_until(ws, "turn_complete")
        assert ("transcript", {"type": "transcript", "role": "agent", "text": "Ramesh approved. Go ahead.", "final": True}) in seen
    assert voice.take_headset_messages(core.actor(G, "m-raju", "mechanic")) == []
    # the next connection starts on the same job (state lives in Firestore, not in the instance)
    assert voice.load_session({"garage_id": G, "uid": "m-raju", "name": "Raju", "role": "mechanic"})["current_job"] == "J-1042"


def test_audio_is_forwarded_once_per_turn(client, monkeypatch):
    """Streamed chunks, then an aggregate (partial=False) event repeating them: the phone gets each chunk once."""
    def audio(data, **kw):
        return Event(author="garage_copilot", content=types.Content(
            role="model", parts=[types.Part(inline_data=types.Blob(data=data, mime_type="audio/pcm;rate=24000"))]), **kw)

    async def gemini(state, queue, push_to_talk):
        await queue.get()  # the mechanic's typed message
        yield audio(b"aa")
        yield audio(b"bb")
        yield audio(b"aabb", partial=False)  # final aggregate of the same turn
        yield Event(author="garage_copilot", turn_complete=True)
        yield audio(b"cc", partial=False)  # next turn: one non-streamed chunk is still sent
        yield Event(author="garage_copilot", turn_complete=True)
        await queue.get()

    monkeypatch.setattr(gateway, "live_events", gemini)
    with client.websocket_connect("/ws/voice?token=raju") as ws:
        ws.send_json({"type": "text", "text": "hello"})
        first = receive_until(ws, "turn_complete")
        second = receive_until(ws, "turn_complete")
    assert [d for k, d in first if k == "audio"] == [b"aa", b"bb"]
    assert [d for k, d in second if k == "audio"] == [b"cc"]


def test_a_second_connection_closes_the_first(client):
    """Two tabs or phones for the same mechanic must not run two Gemini sessions on one mic."""
    with client.websocket_connect("/ws/voice?token=raju") as first:
        first.send_bytes(b"\x01\x02")
        receive_until(first, "audio")
        with client.websocket_connect("/ws/voice?token=raju") as second:
            msg = first.receive()
            assert msg["type"] == "websocket.close" and msg["code"] == 4409
            second.send_bytes(b"\x05\x06")
            assert receive_until(second, "audio")[-1] == ("audio", b"\x06\x05")


def test_owner_token_gets_the_owner_agent(client, monkeypatch):
    seen_roles = []

    async def gemini(state, queue, push_to_talk):
        seen_roles.append(gateway.agent_for(state["role"]).name)
        await queue.get()
        yield Event(author="owner_copilot", input_transcription=types.Transcription(text="Kitni bikes?", finished=True))
        yield Event(author="owner_copilot", output_transcription=types.Transcription(text="Four open jobs.", finished=True),
                    turn_complete=True)
        await queue.get()

    monkeypatch.setattr(gateway, "live_events", gemini)
    asha = {"uid": "o-asha", "garage": G, "role": "owner", "name": "Asha"}
    monkeypatch.setattr(auth, "verify_id_token", lambda t: asha if t == "asha" else RAJU)
    with client.websocket_connect("/ws/voice?token=asha") as ws:
        ws.send_json({"type": "text", "text": "Kitni bikes?"})
        seen = receive_until(ws, "turn_complete")
    assert seen_roles == ["owner_copilot"]
    assert ("transcript", {"type": "transcript", "role": "owner", "text": "Kitni bikes?", "final": True}) in seen
    with client.websocket_connect("/ws/voice?token=raju") as ws:
        ws.send_json({"type": "text", "text": "hi"})
        receive_until(ws, "turn_complete")
    assert seen_roles == ["owner_copilot", "garage_copilot"]


def test_push_to_talk_turn_without_speech_never_reaches_gemini(client, monkeypatch):
    """C06: a tap, a silent hold or background noise must not become a turn (Gemini would answer it)."""
    from tests.test_speech import noise, pcm, silence, voice

    seen = []

    async def gemini(state, queue, push_to_talk):
        assert push_to_talk
        while True:
            req = await queue.get()
            if req.close:
                return
            kind = "start" if req.activity_start else "end" if req.activity_end else "audio" if req.blob else "text"
            seen.append(kind)
            if kind == "end":
                yield Event(author="garage_copilot", output_transcription=types.Transcription(text="ok", finished=True),
                            turn_complete=True)

    monkeypatch.setattr(gateway, "live_events", gemini)
    with client.websocket_connect("/ws/voice?token=raju&ptt=1") as ws:
        for audio in (b"", pcm(silence(300)), pcm(silence(1000)), pcm(noise(1000, 1500))):
            ws.send_json({"type": "start"})
            for i in range(0, len(audio), 1280):
                ws.send_bytes(audio[i:i + 1280])
            ws.send_json({"type": "stop"})
            assert json.loads(ws.receive_text()) == {"type": "ignored", "reason": "no speech"}
        assert seen == []

        spoken = pcm(silence(150) + voice(500) + silence(150))  # "washing"
        ws.send_json({"type": "start"})
        for i in range(0, len(spoken), 1280):
            ws.send_bytes(spoken[i:i + 1280])
        ws.send_json({"type": "stop"})
        receive_until(ws, "turn_complete")
    assert seen[0] == "start" and seen[-1] == "end" and set(seen[1:-1]) == {"audio"}
