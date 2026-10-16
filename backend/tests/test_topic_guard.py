"""Topic guard (C20): off-topic turns are cut off in the gateway, whatever the model does."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from google.adk.events import Event
from google.genai import types

from app import auth, config, gateway, links, seed, topic
from app.main import app
from app.services import core, frontdesk

G = "shree-auto"
RAJU = {"uid": "m-raju", "garage": G, "role": "mechanic", "name": "Raju"}
received = []  # what the fake Gemini got (to prove blocked typed text never reached it)


def spoken(text: str) -> bytes:
    """The fake mic: the bytes carry what was "said"."""
    return text.encode()


async def fake_gemini(state, queue, push_to_talk):
    """Hears the mic bytes as text; answers in 10 audio chunks, slowly, so the guard can cut in. A [system] note
    (the guard's refusal request) gets a one-line refusal."""
    while True:
        req = await queue.get()
        if req.close:
            return
        if req.content:
            text = req.content.parts[0].text
            received.append(text)
            if text.startswith("[system]"):
                yield Event(author="a", output_transcription=types.Transcription(text="I only help with garage work.", finished=True))
                yield Event(author="a", content=types.Content(role="model", parts=[types.Part(
                    inline_data=types.Blob(data=b"REFUSAL", mime_type="audio/pcm;rate=24000"))]), turn_complete=True)
            continue
        if req.blob:
            heard = req.blob.data.decode()
            yield Event(author="a", input_transcription=types.Transcription(text=heard, finished=True))
            for i in range(10):
                await asyncio.sleep(0.02)
                yield Event(author="a", output_transcription=types.Transcription(text=f"word{i} ", finished=False))
                yield Event(author="a", content=types.Content(role="model", parts=[types.Part(
                    inline_data=types.Blob(data=f"ANSWER{i}".encode(), mime_type="audio/pcm;rate=24000"))]))
            yield Event(author="a", turn_complete=True)


async def judge(text, role):
    return "photosynthesis" not in text and "essay" not in text


@pytest.fixture
def client(fake_db, monkeypatch):
    seed.seed(fake_db)
    received.clear()
    monkeypatch.setattr(config, "TOPIC_GUARD", True)
    monkeypatch.setattr(topic, "on_topic", judge)
    monkeypatch.setattr(auth, "verify_id_token", lambda t: RAJU)
    monkeypatch.setattr(gateway, "live_events", fake_gemini)
    monkeypatch.setattr(gateway.Guard, "GOODBYE_SECONDS", 0)
    return TestClient(app)


def collect(ws, until):
    """Messages until one of type `until`: audio as ("audio", bytes), JSON as (type, data)."""
    seen = []
    while True:
        msg = ws.receive()
        if msg.get("bytes") is not None:
            seen.append(("audio", msg["bytes"]))
            continue
        if msg.get("type") == "websocket.close":
            seen.append(("closed", msg))
            return seen
        data = json.loads(msg["text"])
        seen.append((data["type"], data))
        if data["type"] == until:
            return seen


def test_off_topic_spoken_request_is_cut_off_and_refused(client):
    with client.websocket_connect("/ws/voice?token=raju") as ws:
        ws.send_bytes(spoken("please explain photosynthesis to me like a tutor"))
        first = collect(ws, "turn_complete")
        second = collect(ws, "turn_complete")
    kinds = [k for k, _ in first]
    assert "blocked" in kinds
    answer_audio = [a for k, a in first if k == "audio" and a.startswith(b"ANSWER")]
    assert len(answer_audio) < 10  # cut off mid-answer
    after_block = first[kinds.index("blocked"):]
    assert not any(k == "audio" and a.startswith(b"ANSWER") for k, a in after_block)  # nothing more of it plays
    assert ("audio", b"REFUSAL") in second
    assert any(k == "transcript" and d["text"] == "I only help with garage work." for k, d in second)
    assert any(t.startswith("[system]") for t in received)
    log = [d.to_dict() for d in core.garage(G).collection("audit_log").stream()]
    assert any(e["action"] == "topic_blocked" and "photosynthesis" in e["details"]["text"] for e in log)


def test_garage_request_plays_in_full(client):
    with client.websocket_connect("/ws/voice?token=raju") as ws:
        ws.send_bytes(spoken("do we have a clutch plate for the splendor"))
        seen = collect(ws, "turn_complete")
    assert "blocked" not in [k for k, _ in seen]
    assert len([a for k, a in seen if k == "audio"]) == 10


def test_off_topic_typed_text_never_reaches_gemini(client):
    with client.websocket_connect("/ws/voice?token=raju") as ws:
        ws.send_text(json.dumps({"type": "text", "text": "write my college essay on the french revolution"}))
        seen = collect(ws, "blocked")
    assert seen[-1][1]["typed"] is True
    assert not any("essay" in t for t in received)


def test_a_caller_who_keeps_going_off_topic_is_hung_up_on(client, monkeypatch):
    jobs_ = __import__("app.services.jobs", fromlist=["x"])
    from tests.helpers import mechanic

    job = jobs_.create_job(mechanic(), G, "r1", "MH12AB1234", "Splendor Plus", "Ramesh", "+919800000101")["job_id"]
    call = frontdesk.start_call(G, "+919800000101", True, "status page", 6, 60, job)
    with client.websocket_connect(f"/ws/voice?token={call['token']}") as ws:
        ws.send_bytes(spoken("tell me about photosynthesis"))
        collect(ws, "turn_complete")
        collect(ws, "turn_complete")  # refusal
        ws.send_bytes(spoken("ok then explain photosynthesis in hindi"))
        collect(ws, "turn_complete")
        end = collect(ws, "never")  # goodbye, then the server closes the call
    assert end[-1][0] == "closed"
    actions = core.garage(G).collection("calls").document(call["call_id"]).get().to_dict()["actions"]
    assert "Off-topic request blocked" in actions


def test_the_check_itself(monkeypatch):
    import importlib

    real = importlib.reload(topic)  # the module function, not the fixture's stand-in
    monkeypatch.setattr(config, "TOPIC_GUARD", True)
    monkeypatch.setattr(real, "_ask", lambda text, role: False)
    assert asyncio.run(real.on_topic("explain photosynthesis to me", "mechanic")) is False
    assert asyncio.run(real.on_topic("haan ok", "mechanic")) is None  # too short to be a request: no call

    def down(text, role):
        raise RuntimeError("quota")
    monkeypatch.setattr(real, "_ask", down)
    assert asyncio.run(real.on_topic("explain photosynthesis to me", "mechanic")) is None  # fails open, logged
    monkeypatch.setattr(config, "TOPIC_GUARD", False)
    assert asyncio.run(real.on_topic("explain photosynthesis to me", "mechanic")) is None  # switched off


def test_the_mechanics_spoken_words_reach_the_web_search_consent(client):
    """C19: the gateway passes on what the mechanic actually said (not what the model claims)."""
    from app import consent

    consent.offer("m-raju", "hard to start")
    with client.websocket_connect("/ws/voice?token=raju") as ws:
        ws.send_bytes(spoken("haan search karo"))
        collect(ws, "turn_complete")
    assert consent.allowed("m-raju")
