"""C15 AI front desk: caller isolation, estimates go to the owner first, callbacks, bookings, the gateway's agent
choice for a call token, and call rate limits."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import agent, auth, gateway, links, seed, tools
from app.main import app
from app.services import core, frontdesk, jobs, quotes
from tests.helpers import mechanic, owner

G = "shree-auto"
RAMESH = "+919800000101"


@pytest.fixture
def garage(fake_db):
    seed.seed(fake_db)
    jobs.create_job(mechanic(), G, "r1", "MH12AB1234", "Splendor Plus", "Ramesh", RAMESH, "clutch slipping")
    jobs.create_job(mechanic(), G, "r2", "MH12CD5678", "Activa 6G", "Sunita", "+919800000202", "service")
    return fake_db


def call_ctx(phone, verified, call_id="C-1", n=[0]):
    n[0] += 1
    state = {"garage_id": G, "garage_name": "Shree Auto", "uid": f"caller:{frontdesk.digits(phone)}", "name": "Caller",
             "role": "caller", "phone": frontdesk.digits(phone), "verified": verified, "call_id": call_id}
    return SimpleNamespace(state=state, function_call_id=f"f{n[0]}")


def messages(kind=None):
    out = [d.to_dict() for d in core.garage(G).collection("messages").stream()]
    return [m for m in out if kind is None or m["kind"] == kind]


def test_a_verified_caller_sees_only_their_own_jobs(garage):
    out = tools.my_vehicle_status("", call_ctx(RAMESH, True))
    assert [j["plate"] for j in out["jobs"]] == ["MH12AB1234"]
    assert out["jobs"][0]["stage"] == "Checked in"
    assert tools.my_vehicle_status("MH12CD5678", call_ctx(RAMESH, True))["jobs"] == []  # Sunita's plate: nothing


def test_an_unverified_caller_gets_no_job_details(garage):
    out = tools.my_vehicle_status("MH12AB1234", call_ctx("+919999999999", False))
    assert out["verified"] is False and out["jobs"] == [] and "can't share job details" in out["say"]
    # ...but can have the link sent to the number on file (never to the caller)
    sent = tools.send_status_link_again("MH12AB1234", call_ctx("+919999999999", False))
    assert sent == {"sent": True, "sent_to": "the number we have on file"}
    assert sum(1 for m in messages("status_link") if m["to"] == "c-919800000101") == 2  # check-in + this one
    assert "error" in tools.send_status_link_again("", call_ctx("+919999999999", False))


def test_front_desk_tools_refuse_staff_and_staff_tools_refuse_callers(garage):
    staff = SimpleNamespace(state={"garage_id": G, "uid": "m-raju", "name": "Raju", "role": "mechanic"},
                            function_call_id="x1")
    assert "error" in tools.my_vehicle_status("", staff)
    assert "error" in tools.check_stock("clutch plate", "", call_ctx(RAMESH, True))
    names = {t.__name__ for t in tools.FRONT_DESK_TOOLS}
    assert not names & {t.__name__ for t in tools.FAST_TOOLS + tools.OWNER_TOOLS}


def test_quote_sent_again_to_the_number_on_file(garage):
    quotes.draft_quote(mechanic(), G, "q1", "J-1042", ["clutch plate"])
    quotes.send_quote(mechanic(), G, "q2", "Q-77")
    before = len(messages("quote"))
    out = tools.send_quote_again("", call_ctx(RAMESH, True))
    assert out["quote_id"] == "Q-77" and len(messages("quote")) == before + 1
    assert {m["to"] for m in messages("quote")} == {"c-919800000101"}


def test_estimate_goes_to_the_owner_first(garage):
    out = tools.request_estimate("clutch plate change", "Splendor Plus", "Kiran", call_ctx("+919811112222", False))
    assert out["status"] == "sent to the owner to confirm"
    est = frontdesk.estimate_ref(G, out["estimate_id"]).get().to_dict()
    assert est["total"] == 350 + 650 + 300 and est["status"] == "asked"
    assert messages("estimate_ask")[-1]["to"] == "owner"
    assert messages("estimate") == []  # the caller gets nothing until the owner confirms
    assert frontdesk.calls_overview(owner(), G)["estimates"][0]["id"] == out["estimate_id"]
    with pytest.raises(core.Forbidden):
        frontdesk.answer_estimate(mechanic(), G, "a0", out["estimate_id"], True)
    sent = frontdesk.answer_estimate(owner(), G, "a1", out["estimate_id"], True, total=1000)
    assert sent["total"] == 1000
    [msg] = messages("estimate")
    assert msg["to"] == "c-9811112222" and "about ₹1000" in msg["text"]
    with pytest.raises(core.Invalid):
        frontdesk.answer_estimate(owner(), G, "a2", out["estimate_id"], False)


def test_callback_and_booking_reach_the_owner(garage):
    cb = tools.request_callback("Ramesh", "the bill for the Splendor", call_ctx(RAMESH, True, "C-9"))
    assert cb["status"] == "someone will call back"
    assert messages("callback")[-1]["text"] == "Call back Ramesh (9800000101) about the bill for the Splendor."
    bk = tools.book_dropoff("Kiran", "Pulsar 150", "tomorrow 10 am", "service", call_ctx("+919811112222", False))
    assert bk["when"] == "tomorrow 10 am"
    view = frontdesk.calls_overview(owner(), G)
    assert [c["reason"] for c in view["callbacks"]] == ["the bill for the Splendor"]
    assert view["bookings"][0]["when"] == "tomorrow 10 am"
    frontdesk.close_callback(owner(), G, "d1", cb["callback_id"])
    assert frontdesk.calls_overview(owner(), G)["callbacks"] == []


@pytest.fixture
def api(garage, monkeypatch):
    monkeypatch.setattr(auth, "verify_id_token", lambda t: {"uid": "o-asha", "garage": G, "role": "owner", "name": "Asha"}
                        if t == "owner" else (_ for _ in ()).throw(ValueError()))
    return TestClient(app)


def test_starting_calls_rate_limits_and_verification(api, monkeypatch):
    from app import config

    r = api.post("/api/call/start", json={"garage_id": G, "phone": "98111 12222"})
    assert r.status_code == 200 and r.json()["verified"] is False
    call = links.read_caller_token(r.json()["token"])
    assert call == {"garage_id": G, "phone": "9811112222", "verified": False, "call_id": r.json()["call_id"], "job_id": ""}
    assert api.post("/api/call/start", json={"garage_id": G, "phone": "12"}).status_code == 409
    assert api.post("/api/call/start", json={"garage_id": "nope", "phone": "9811112222"}).status_code == 404

    token = links.make_token(G, "J-1042")
    verified = api.post(f"/api/j/{token}/call").json()
    assert verified["verified"] is True and links.read_caller_token(verified["token"])["phone"] == "9800000101"

    monkeypatch.setattr(config, "CALLS_PER_PHONE_HOUR", 2)
    assert api.post("/api/call/start", json={"garage_id": G, "phone": "9811112222"}).status_code == 200
    blocked = api.post("/api/call/start", json={"garage_id": G, "phone": "9811112222"})
    assert blocked.status_code == 409 and "too many calls" in blocked.json()["detail"]
    assert api.post("/api/call/start", json={"garage_id": G, "phone": "9822223333"}).status_code == 200  # others fine

    overview = api.get("/api/owner/calls", headers={"Authorization": "Bearer owner"}).json()
    assert len(overview["calls"]) == 4


def test_gateway_picks_the_front_desk_for_a_call_token(api, monkeypatch):
    seen = {}

    async def scripted(state, queue, push_to_talk):
        seen.update(state)
        seen["agent"] = gateway.agent_for(state["role"]).name
        from google.adk.events import Event
        from google.genai import types

        yield Event(author="front_desk", input_transcription=types.Transcription(text="Is my bike ready?", finished=True))
        yield Event(author="front_desk", output_transcription=types.Transcription(text="It's in service.", finished=True),
                    turn_complete=True)
        while True:
            req = await queue.get()
            if req.close:
                return

    monkeypatch.setattr(gateway, "live_events", scripted)
    started = api.post(f"/api/j/{links.make_token(G, 'J-1042')}/call").json()
    with api.websocket_connect(f"/ws/voice?token={started['token']}") as ws:
        assert ws.receive_json() == {"type": "transcript", "role": "caller", "text": "Is my bike ready?", "final": True}
        ws.receive_json()
    assert seen["agent"] == "front_desk" and seen["role"] == "caller" and seen["verified"] is True
    assert seen["phone"] == "9800000101" and seen["current_job"] == ""
    record = frontdesk.call_ref(G, started["call_id"]).get().to_dict()
    assert record["heard"] == ["Is my bike ready?"]
    with api.websocket_connect("/ws/voice?token=call.bad.sig") as ws:
        assert ws.receive()["code"] == 4401


def test_front_desk_instruction():
    text = agent.front_desk_instruction(SimpleNamespace(state={"garage_name": "Shree Auto", "verified": False}))
    assert "LANGUAGE (first and strictest rule)" in text.split("\n\n")[1]
    assert "share no job details" in text and "never quote a price yourself" in text
    assert "There is no live transfer" in text



def test_status_page_call_works_without_a_phone_on_file(api):
    """The job's private link proves who is calling, so a job with no phone number can still call (bug, Oct 16)."""
    nophone = jobs.create_job(mechanic(), G, "r3", "MH10VP1093", "Pulsar", "Ashwini")["job_id"]
    r = api.post(f"/api/j/{links.make_token(G, nophone)}/call")
    assert r.status_code == 200 and r.json()["verified"] is True
    call = links.read_caller_token(r.json()["token"])
    assert call["phone"] == "" and call["job_id"] == nophone

    ctx = call_ctx("", True, r.json()["call_id"])
    ctx.state["call_job"] = nophone
    assert [j["job_id"] for j in tools.my_vehicle_status("", ctx)["jobs"]] == [nophone]  # only that job
    ctx2 = call_ctx("", True, r.json()["call_id"])  # a new tool call = a new request id
    ctx2.state["call_job"] = nophone
    out = tools.request_callback("Ashwini", "the bill", ctx2)
    assert out.get("status") == "someone will call back", out
    cb = [d.to_dict() for d in core.garage(G).collection("callbacks").stream()][-1]
    assert cb["job_id"] == nophone
    assert any(f"the customer on {nophone}" in m["text"] for m in messages("callback"))


def test_wait_time_gives_ranges_without_anyone_elses_details(garage):
    """'If I bring my bike now, how long?': counts and rough ranges only (bug report, Oct 16)."""
    out = tools.service_wait_time("general service", call_ctx("+919811112222", False))
    assert out["vehicles_ahead"] == 2  # the two seeded open jobs, both checked in
    lo, hi = out["start_in_minutes"]
    assert 0 < lo < hi and out["job_takes_minutes"][0] < out["job_takes_minutes"][1]
    text = str(out)
    assert "MH12AB1234" not in text and "Ramesh" not in text and "Sunita" not in text


def test_front_desk_is_customer_care_not_a_brush_off():
    text = agent.FRONT_DESK_INSTRUCTION
    assert "service_wait_time" in text and "Never end the call" in text
    assert "only after they say yes" in text
