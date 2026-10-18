import pytest
from fastapi.testclient import TestClient

from app import links, seed
from app.main import app
from app.services import core, jobs, quotes
from tests.helpers import mechanic

G = "shree-auto"


@pytest.fixture
def job(fake_db):
    seed.seed(fake_db)
    return jobs.create_job(mechanic(), G, "r1", "MH12AB1234", "Splendor Plus", "Ramesh", "+919800000101")["job_id"]


def messages(kind):
    return [d.to_dict() for d in core.garage(G).collection("messages").stream() if d.to_dict()["kind"] == kind]


def test_over_limit_waits_for_customer_then_approve(job):
    draft = quotes.draft_quote(mechanic(), G, "q1", job, ["clutch plate"], note="worn plate")
    assert draft["quote_id"] == "Q-77" and draft["total"] == 950 and draft["needs_approval"]
    sent = quotes.send_quote(mechanic(), G, "q2", "Q-77")
    assert sent["status"] == "pending"
    [msg] = messages("quote")
    assert "Total: ₹950" in msg["text"] and msg["lang"] == "mr"

    token = links.make_token(G, job)
    client = TestClient(app)
    assert client.post(f"/api/j/{token}/quotes/Q-77/approve").json()["status"] == "approved"
    assert client.post(f"/api/j/{token}/quotes/Q-77/approve").json()["status"] == "approved"  # double tap
    assert client.post(f"/api/j/{token}/quotes/Q-77/reject").json()["status"] == "approved"  # first decision stands
    [heard] = messages("quote_approved")
    assert heard["to"] == "m-raju" and heard["text"] == "Ramesh approved. Go ahead."
    job_doc = jobs.get_job(mechanic(), G, job)
    assert job_doc["labour"] == 300 and job_doc["bill"] == 350 + 300 and job_doc["pending_quote"] is None


def test_under_limit_is_auto_approved(job):
    quotes.draft_quote(mechanic(), G, "q1", job, ["spark plug"])
    assert quotes.send_quote(mechanic(), G, "q2", "Q-77")["status"] == "approved"
    assert messages("quote") == []


def test_reject_and_wrong_job_link(job):
    quotes.draft_quote(mechanic(), G, "q1", job, ["clutch plate"])
    quotes.send_quote(mechanic(), G, "q2", "Q-77")
    other = jobs.create_job(mechanic(), G, "r2", "MH12ZZ1", "Activa", "Seema")["job_id"]
    client = TestClient(app)
    assert client.post(f"/api/j/{links.make_token(G, other)}/quotes/Q-77/approve").status_code == 404
    assert client.post(f"/api/j/{links.make_token(G, job)}/quotes/Q-77/reject").json()["status"] == "rejected"
    assert messages("quote_rejected")[0]["to"] == "m-raju"


def test_translation_falls_back_to_english(job, monkeypatch):
    from app import gemini

    def broken(*a, **k):
        raise RuntimeError("quota")

    monkeypatch.setattr(gemini, "generate", broken)
    quotes.draft_quote(mechanic(), G, "q1", job, ["clutch plate"])
    quotes.send_quote(mechanic(), G, "q2", "Q-77")
    [msg] = messages("quote")
    assert msg["text"].startswith("Hi Ramesh, quote for your Splendor Plus")


def test_a_reused_quote_id_gets_its_own_decision(job, monkeypatch):
    """C05 root cause: after a re-seed Q-77 exists again, but requests/ still held the old "Q-77-decision"
    claim, so Approve returned the stored "approved" without writing and the card never went away."""
    token = links.make_token(G, job)
    client = TestClient(app)
    quotes.draft_quote(mechanic(), G, "q1", job, ["clutch plate"])
    quotes.send_quote(mechanic(), G, "q2", "Q-77")
    assert client.post(f"/api/j/{token}/quotes/Q-77/approve").json()["status"] == "approved"

    # The same id is used again for a new quote (a re-seed resets the counter; requests/ is kept)
    monkeypatch.setattr(core, "now", lambda: "2026-10-12T05:00:00+00:00")
    quotes.quote_ref(G, "Q-77").delete()
    quotes.quote_ref(G, "Q-77").set({"job_id": job, "status": "draft", "total": 950, "quote_limit": 500, "labour": 300,
                                     "lines": [], "lang": "mr", "customer_id": "c-919800000101"})
    quotes.send_quote(mechanic(), G, "q3", "Q-77")
    assert client.get(f"/api/j/{token}").json()["quotes"][0]["status"] == "pending"
    assert client.post(f"/api/j/{token}/quotes/Q-77/reject").json()["status"] == "rejected"
    assert client.get(f"/api/j/{token}").json()["quotes"][0]["status"] == "rejected"
