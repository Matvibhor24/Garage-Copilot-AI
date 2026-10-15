"""C12: the customer page gets English and Hindi texts; new customers default to English."""

from types import SimpleNamespace

import pytest

from app import seed, tools
from app.services import core, jobs, quotes
from tests.helpers import Clock, mechanic

G = "shree-auto"


@pytest.fixture
def garage(fake_db):
    seed.seed(fake_db)
    return fake_db


def test_view_returns_english_and_hindi_for_quotes_and_messages(garage, monkeypatch):
    clock = Clock(monkeypatch)
    job = jobs.create_job(mechanic(), G, "r1", "MH12AB1234", "Splendor Plus", "Ramesh", "+919800000101")["job_id"]
    clock.advance(30)
    quotes.draft_quote(mechanic(), G, "q1", job, ["clutch plate"])
    quotes.send_quote(mechanic(), G, "q2", "Q-77")
    view = jobs.customer_view(G, job)
    [q] = view["quotes"]
    assert q["text_en"].startswith("Hi Ramesh, quote for your Splendor Plus") and "Total: ₹950" in q["text_en"]
    assert q["text_hi"] == "[Hindi] " + q["text_en"]
    assert q["text"] == "[Marathi] " + q["text_en"]  # Ramesh's WhatsApp stays in his language (mr)
    kinds = [m["kind"] for m in view["messages"]]
    assert kinds == ["status_link", "quote"]
    assert all(m["text_en"] and m["text_hi"].startswith("[Hindi] ") for m in view["messages"])
    assert not any("[Marathi]" in m["text_en"] for m in view["messages"])


def test_new_customers_default_to_english_unless_the_mechanic_says(garage):
    out = jobs.create_job(mechanic(), G, "r1", "MH12CD0001", "Activa 6G", "Neha", "+919811111111")
    assert jobs.job_ref(G, out["job_id"]).get().to_dict()["lang"] == "en"
    [msg] = [d.to_dict() for d in core.garage(G).collection("messages").stream()]
    assert msg["text"] == msg["text_en"] and msg["text"].startswith("Hi Neha")  # no translation for English

    ctx = SimpleNamespace(state={"garage_id": G, "uid": "m-raju", "name": "Raju", "role": "mechanic"}, function_call_id="c2")
    out = tools.create_job("MH12CD0002", "Pulsar 150", "Sunil", "+919822222222", "service", ctx, customer_language="hi")
    assert jobs.job_ref(G, out["job_id"]).get().to_dict()["lang"] == "hi"
    ramesh = jobs.create_job(mechanic(), G, "r3", "MH12AB1234", "Splendor Plus", "Ramesh", "+919800000101")
    assert jobs.job_ref(G, ramesh["job_id"]).get().to_dict()["lang"] == "mr"  # returning customer keeps theirs
