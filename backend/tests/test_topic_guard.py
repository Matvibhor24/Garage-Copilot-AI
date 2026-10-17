"""Topic guard (C20): off-topic turns are cut off in the gateway, whatever the model does."""

import asyncio
import json
from types import SimpleNamespace

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


# ---- turn timing: the guard driven by a scripted event stream (no socket timing involved)

class FakeWs:
    def __init__(self, broken=False):
        self.sent, self.closed, self.broken = [], False, broken

    async def send_json(self, data):
        if self.broken:
            raise RuntimeError("websocket is closed")
        self.sent.append(("json", data))

    async def send_bytes(self, data):
        self.sent.append(("audio", data))

    async def close(self, code=1000, reason=""):
        self.closed = True


class FakeQueue:
    def __init__(self):
        self.notes = []

    def send_content(self, content, partial=False):
        self.notes.append(content.parts[0].text)


def heard_ev(text):
    return Event(author="a", input_transcription=types.Transcription(text=text, finished=True))


def said_ev(text):
    return Event(author="a", output_transcription=types.Transcription(text=text, finished=False))


def audio_ev(data):
    return Event(author="a", content=types.Content(role="model", parts=[types.Part(
        inline_data=types.Blob(data=data, mime_type="audio/pcm;rate=24000"))]))


async def until(condition):
    for _ in range(200):
        if condition():
            return
        await asyncio.sleep(0)
    raise AssertionError("never happened")


LONG_OFF_TOPIC = " ".join(["photosynthesis"] + [f"w{i}" for i in range(20)])


def run_downstream(script, who, guard_setup=lambda g: None):
    ws, queue = FakeWs(), FakeQueue()

    async def go():
        guard = gateway.Guard(ws, queue, who)
        guard_setup(guard)
        await gateway.downstream(ws, script(guard), who, {}, queue, guard)
        await asyncio.gather(*guard.tasks)
        return guard
    return ws, queue, asyncio.run(go())


def test_one_off_topic_question_is_one_strike_even_when_its_reply_is_checked_too(fake_db, monkeypatch):
    seed.seed(fake_db)
    monkeypatch.setattr(config, "TOPIC_GUARD", True)
    verdicts = []

    async def slow_judge(text, role):
        await until(lambda: verdicts)  # both checks come back after the turn is over
        return "photosynthesis" not in text
    monkeypatch.setattr(topic, "on_topic", slow_judge)

    async def script(guard):
        yield heard_ev("please explain photosynthesis to me")
        yield said_ev(LONG_OFF_TOPIC)  # a long reply: its own check starts too
        yield Event(author="a", turn_complete=True)
        assert len(guard.tasks) == 2
        verdicts.append(True)

    ws, queue, guard = run_downstream(script, {"garage_id": G, "uid": "m-raju", "role": "mechanic", "name": "Raju"})
    assert guard.strikes == 1
    assert queue.notes == [topic.REFUSAL_NOTE]


def test_a_refusal_that_interrupts_the_long_reply_is_not_blocked_again(fake_db, monkeypatch):
    seed.seed(fake_db)
    monkeypatch.setattr(config, "TOPIC_GUARD", True)

    async def judge_(text, role):
        return "photosynthesis" not in text
    monkeypatch.setattr(topic, "on_topic", judge_)

    async def script(guard):
        yield heard_ev("photosynthesis batao")  # too short to check: only the long reply is
        yield said_ev(LONG_OFF_TOPIC)
        await until(lambda: guard.blocking)
        yield Event(author="a", interrupted=True)  # the refusal note cuts into the reply
        yield Event(author="a", output_transcription=types.Transcription(text="I only help with garage work.", finished=True))
        yield audio_ev(b"REFUSAL")
        yield Event(author="a", turn_complete=True)

    ws, queue, guard = run_downstream(script, {"garage_id": G, "uid": "m-raju", "role": "mechanic", "name": "Raju"})
    assert guard.strikes == 1 and queue.notes == [topic.REFUSAL_NOTE]
    assert ("audio", b"REFUSAL") in ws.sent


def test_the_callers_goodbye_plays_before_the_call_is_closed(fake_db, monkeypatch):
    seed.seed(fake_db)
    monkeypatch.setattr(config, "TOPIC_GUARD", True)
    monkeypatch.setattr(gateway.Guard, "GOODBYE_SECONDS", 0)
    playing = []

    async def late_judge(text, role):
        await until(lambda: playing)  # the reply is playing when the verdict lands
        return await judge(text, role)
    monkeypatch.setattr(topic, "on_topic", late_judge)
    monkeypatch.setattr(frontdesk, "note_heard", lambda *a: None)
    caller = frontdesk.caller(G, "+919800000101", True, "call-1", "")
    log = []

    async def script(guard):
        yield heard_ev("ok then explain photosynthesis in hindi")
        yield audio_ev(b"ANSWER0")
        playing.append(True)
        await until(lambda: guard.ending)
        yield audio_ev(b"ANSWER1")  # the rest of the blocked reply: dropped
        yield Event(author="a", turn_complete=True)
        log.append(("closed after blocked turn", ws.closed))
        yield Event(author="a", output_transcription=types.Transcription(text="Sorry, ending the call.", finished=True))
        yield audio_ev(b"GOODBYE")
        yield Event(author="a", turn_complete=True)
        log.append(("still streaming after goodbye", True))  # never reached: downstream returns first

    ws = None

    def setup(guard):
        nonlocal ws
        ws = guard.ws
        guard.strikes = 1  # one strike already: this one ends the call
    _, queue, guard = run_downstream(script, caller, setup)
    assert queue.notes == [topic.END_CALL_NOTE]
    assert log == [("closed after blocked turn", False)]
    assert ws.closed
    audio = [d for k, d in ws.sent if k == "audio"]
    assert audio == [b"ANSWER0", b"GOODBYE"]


def test_a_verdict_after_hang_up_is_still_recorded(fake_db):
    seed.seed(fake_db)
    who = {"garage_id": G, "uid": "m-raju", "role": "mechanic", "name": "Raju"}
    queue = FakeQueue()
    guard = gateway.Guard(FakeWs(broken=True), queue, who)
    asyncio.run(guard.block("explain photosynthesis to me", "request"))  # no exception
    log = [d.to_dict() for d in core.garage(G).collection("audit_log").stream()]
    assert any(e["action"] == "topic_blocked" for e in log)
    assert queue.notes == []  # nobody left to refuse


def test_checks_are_bounded_and_have_a_request_timeout(monkeypatch):
    import importlib
    import threading

    from app import gemini

    real = importlib.reload(topic)
    monkeypatch.setattr(config, "TOPIC_GUARD", True)
    seen = {}

    class Models:
        def generate_content(self, model, contents, config):
            seen["timeout"] = config.http_options.timeout
            return SimpleNamespace(text='{"on_topic": false}')
    monkeypatch.setattr(gemini, "_get_client", lambda: SimpleNamespace(models=Models()))
    assert asyncio.run(real.on_topic("explain photosynthesis to me", "mechanic")) is False
    assert seen["timeout"] == int(config.TOPIC_TIMEOUT_SECONDS * 1000)

    monkeypatch.setattr(real, "_slots", threading.BoundedSemaphore(1))
    real._slots.acquire()  # every slot busy with a check that hasn't returned
    seen.clear()
    assert asyncio.run(real.on_topic("explain photosynthesis to me", "mechanic")) is None  # fails open, no call
    assert seen == {}


def test_a_late_request_transcription_is_still_the_same_exchange(fake_db, monkeypatch):
    """Live sends the caller's words after the reply: the reply check and the request check are one strike."""
    seed.seed(fake_db)
    monkeypatch.setattr(config, "TOPIC_GUARD", True)
    monkeypatch.setattr(topic, "on_topic", judge)
    monkeypatch.setattr(frontdesk, "note_heard", lambda *a: None)

    async def script(guard):
        yield said_ev(LONG_OFF_TOPIC)  # the reply runs long before the request's words arrive
        await until(lambda: guard.strikes == 1)
        yield Event(author="a", turn_complete=True)
        yield heard_ev("tell me about photosynthesis please")  # late
        await until(lambda: not guard.tasks)
        yield Event(author="a", output_transcription=types.Transcription(text="Only garage questions.", finished=True))
        yield Event(author="a", turn_complete=True)

    _, queue, guard = run_downstream(script, frontdesk.caller(G, "+919800000101", True, "call-1", ""))
    assert guard.strikes == 1 and queue.notes == [topic.REFUSAL_NOTE]


def test_a_new_request_after_a_refusal_is_a_new_exchange(fake_db, monkeypatch):
    seed.seed(fake_db)
    monkeypatch.setattr(config, "TOPIC_GUARD", True)
    monkeypatch.setattr(topic, "on_topic", judge)
    monkeypatch.setattr(gateway.Guard, "LATE_HEARD_SECONDS", 0)  # the second question comes well after the refusal

    async def script(guard):
        yield heard_ev("explain photosynthesis to me")
        await until(lambda: guard.strikes == 1)
        yield Event(author="a", turn_complete=True)  # the (dropped) reply
        yield Event(author="a", output_transcription=types.Transcription(text="I only help with garage work.", finished=True))
        yield Event(author="a", turn_complete=True)  # the refusal: a turn with no request of its own
        await asyncio.sleep(0.01)
        yield heard_ev("now write my essay on photosynthesis")
        await until(lambda: guard.strikes == 2)
        yield audio_ev(b"ESSAY")  # the reply to the new off-topic request: dropped
        yield Event(author="a", turn_complete=True)

    ws, queue, guard = run_downstream(script, {"garage_id": G, "uid": "m-raju", "role": "mechanic", "name": "Raju"})
    assert guard.strikes == 2 and ("audio", b"ESSAY") not in ws.sent


def test_the_refusal_is_not_held_up_by_the_audit_write(fake_db, monkeypatch):
    seed.seed(fake_db)
    queue = FakeQueue()
    guard = gateway.Guard(FakeWs(), queue, {"garage_id": G, "uid": "m-raju", "role": "mechanic", "name": "Raju"})
    order = []
    monkeypatch.setattr(guard, "_record", lambda text, source: order.append(("audit", list(queue.notes))))
    asyncio.run(guard.block("explain photosynthesis to me", "request"))
    assert guard.ws.sent[0][1]["type"] == "blocked"
    assert order == [("audit", [topic.REFUSAL_NOTE])]  # phone told and refusal asked for before the audit


def test_typed_text_check_does_not_hold_up_the_mic(monkeypatch):
    monkeypatch.setattr(config, "TOPIC_GUARD", True)
    sent = []

    class Mic:
        def __init__(self):
            self.msgs = [{"type": "websocket.receive", "text": json.dumps({"type": "text", "text": "how many clutch plates left"})},
                         {"type": "websocket.receive", "bytes": b"MIC"}]

        async def receive(self):
            if self.msgs:
                return self.msgs.pop(0)
            await until(lambda: len(sent) == 2)
            return {"type": "websocket.disconnect"}

    class Queue:
        def send_realtime(self, blob):
            sent.append("mic")

        def send_content(self, content, partial=False):
            sent.append("typed")

    async def slow_judge(text, role):
        await until(lambda: "mic" in sent)  # the check is still running when the mic audio arrives
        return True
    monkeypatch.setattr(topic, "on_topic", slow_judge)
    ws, queue = Mic(), Queue()
    guard = gateway.Guard(ws, queue, {"garage_id": G, "uid": "m-raju", "role": "mechanic", "name": "Raju"})
    asyncio.run(gateway.upstream(ws, queue, False, guard))
    assert sent == ["mic", "typed"]


def test_a_check_cancelled_before_it_starts_gives_its_slot_back(monkeypatch):
    import importlib
    import threading

    real = importlib.reload(topic)
    monkeypatch.setattr(config, "TOPIC_GUARD", True)
    monkeypatch.setattr(config, "TOPIC_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(real, "_slots", threading.BoundedSemaphore(2))
    busy = threading.Event()
    monkeypatch.setattr(real, "_pool", __import__("concurrent.futures").futures.ThreadPoolExecutor(max_workers=1))
    monkeypatch.setattr(real, "_ask", lambda text, role: busy.wait(1) or True)

    async def two():  # the second check queues behind the first and times out before a thread picks it up
        return await asyncio.gather(real.on_topic("explain photosynthesis to me", "mechanic"),
                                    real.on_topic("explain photosynthesis to me", "mechanic"))
    assert asyncio.run(two()) == [None, None]
    busy.set()  # the first check's thread finishes; the second never started
    assert real._slots.acquire(timeout=1) and real._slots.acquire(timeout=1), "a slot leaked"


def test_the_agents_own_search_question_is_the_offer(fake_db, monkeypatch):
    """C19: the offer comes from what the agent says after a manual lookup, and the mechanic's yes follows it."""
    from app import consent

    seed.seed(fake_db)
    consent.looked_up("m-raju", "hard to start")

    async def script(guard):
        yield heard_ev("haan")  # a yes before any offer counts for nothing
        yield said_ev("It isn't in the manual. Shall I search online for known causes and fixes?")
        yield Event(author="a", turn_complete=True)
        assert not consent.allowed("m-raju")
        yield heard_ev("haan, search karo")

    run_downstream(script, {"garage_id": G, "uid": "m-raju", "role": "mechanic", "name": "Raju"})
    assert consent.allowed("m-raju")
