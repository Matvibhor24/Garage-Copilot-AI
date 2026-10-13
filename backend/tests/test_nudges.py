import pytest
from fastapi.testclient import TestClient

from app import config, routes_tasks, seed
from app.main import app
from app.services import core, jobs, quotes
from tests.helpers import Clock, mechanic

G = "shree-auto"


@pytest.fixture
def client(fake_db, monkeypatch):
    seed.seed(fake_db)
    monkeypatch.setattr(config, "SCHEDULER_SA_EMAIL", "sched@p.iam.gserviceaccount.com")
    monkeypatch.setattr(routes_tasks, "verify_scheduler",
                        lambda t: {"email": "sched@p.iam.gserviceaccount.com"} if t == "oidc" else {"email": "x@y"})
    return TestClient(app)


def sweep(client, token="oidc"):
    return client.post("/api/tasks/sweep", headers={"Authorization": f"Bearer {token}"})


def nudges():
    return [d.to_dict() for d in core.garage(G).collection("messages").stream() if d.to_dict()["kind"] == "approval_nudge"]


def test_approval_nudge_after_30_minutes_once(client, monkeypatch):
    clock = Clock(monkeypatch)
    clock.at("10:58")
    jobs.create_job(mechanic(), G, "r1", "MH12AB1234", "Splendor Plus", "Ramesh", "+919800000101")
    quotes.draft_quote(mechanic(), G, "q1", "J-1042", ["clutch plate"])
    quotes.send_quote(mechanic(), G, "q2", "Q-77")
    clock.at("11:20")
    assert sweep(client).json()["shree-auto"]["approvals"] == []
    clock.at("11:29")
    assert sweep(client).json()["shree-auto"]["approvals"] == ["Q-77"]
    clock.at("11:35")
    sweep(client)
    [n] = nudges()
    assert n["to"] == "m-raju" and n["text"].endswith("Call Ramesh on +919800000101?")


def test_sweep_needs_scheduler_token(client):
    assert sweep(client, "user-token").status_code == 403


def test_low_stock_ask_safety_net(client, monkeypatch):
    from app.services import inventory
    from tests.helpers import owner

    clock = Clock(monkeypatch)
    clock.at("11:40")
    jobs.create_job(mechanic(), G, "r1", "MH12AB1234", "Splendor Plus", "Ramesh")
    inventory.log_part_used(mechanic(), G, "u1", "J-1042", "clutch plate")
    out = sweep(client).json()
    assert out["shree-auto"]["reorder_asks"] == ["clutch-splendor"] and out["ganesh-motors"]["reorder_asks"] == []
    assert sweep(client).json()["shree-auto"]["reorder_asks"] == []  # asked once
    inventory.reorder_later(owner(), G, "l1", "clutch-splendor")
    clock.at("18:00")
    assert sweep(client).json()["shree-auto"]["reorder_asks"] == []  # "Later" holds for the day
    clock.advance(24 * 60)
    assert sweep(client).json()["shree-auto"]["reorder_asks"] == ["clutch-splendor"]
    asks = [d.to_dict()["text"] for d in core.garage(G).collection("messages").stream() if d.to_dict()["kind"] == "reorder_ask"]
    assert asks == ["Clutch plate set down to 1. Reorder 5 from Sai Spares?"] * 2
