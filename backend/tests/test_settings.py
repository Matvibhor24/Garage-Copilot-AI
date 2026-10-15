"""C09 owner Settings: read, validate, save with an audit line; send_quote uses the current auto-approve limit."""

from types import SimpleNamespace

import pytest

from app import seed, tools
from app.services import core, inventory, jobs, quotes, settings
from app.services.core import Forbidden, Invalid
from tests.helpers import mechanic, owner
from tests.test_owner_api import client, h  # noqa: F401  (fixture)

G = "shree-auto"


@pytest.fixture
def garage(fake_db):
    seed.seed(fake_db)
    return fake_db


def audit_entries(action):
    return [d.to_dict() for d in core.garage(G).collection("audit_log").stream() if d.to_dict()["action"] == action]


def test_read_and_save_with_an_audit_line(garage):
    s = settings.get_settings(owner(), G)
    assert (s["quote_limit"], s["name"], s["city"], s["lang"], s["supplier"], s["reorder_qty"], s["low_at"]) == \
        (500, "Shree Auto", "Pune", "en", "Sai Spares", 5, 1)
    out = settings.update_settings(owner(), G, "s1", {"quote_limit": "0", "city": "Pune", "supplier": "Om Spares"})
    assert out["summary"] == "changed the auto-approve limit from ₹500 to ₹0; the supplier from Sai Spares to Om Spares"
    s = settings.get_settings(owner(), G)
    assert s["quote_limit"] == 0 and s["supplier"] == "Om Spares"
    [entry] = audit_entries("update_settings")
    assert entry["by_name"] == "Asha" and "₹500 to ₹0" in entry["details"]["summary"]


@pytest.mark.parametrize("changes, message", [
    ({"quote_limit": -1}, "between 0 and 100,000"),
    ({"quote_limit": 100_001}, "between 0 and 100,000"),
    ({"quote_limit": 99.5}, "whole number"),
    ({"quote_limit": "lots"}, "whole number"),
    ({"quote_limit": True}, "whole number"),
    ({"reorder_qty": 0}, "between 1 and 999"),
    ({"lang": "xx"}, "customer language"),
    ({"name": "  "}, "can't be empty"),
    ({"owner_uid": "o-evil"}, "unknown setting"),
])
def test_validation(garage, changes, message):
    with pytest.raises(Invalid, match=message):
        settings.update_settings(owner(), G, "bad", changes)
    assert settings.get_settings(owner(), G)["quote_limit"] == 500


def test_only_the_owner_of_this_garage(garage):
    with pytest.raises(Forbidden):
        settings.update_settings(mechanic(), G, "m1", {"quote_limit": 0})
    with pytest.raises(Forbidden):
        settings.update_settings(owner("ganesh-motors") | {"uid": "o-vikram"}, G, "v1", {"quote_limit": 0})


def test_send_quote_uses_the_setting_at_send_time(garage):
    job = jobs.create_job(mechanic(), G, "r1", "MH12AB1234", "Splendor Plus", "Ramesh")["job_id"]
    quotes.draft_quote(mechanic(), G, "q1", job, ["clutch plate"])  # ₹950 > ₹500: needs the customer
    settings.update_settings(owner(), G, "s1", {"quote_limit": 1000})  # owner raises the limit before it is sent
    out = quotes.send_quote(mechanic(), G, "q2", "Q-77")
    assert out["status"] == "approved" and out["auto"] and out["say"] == "Approved automatically: within the ₹1000 limit"
    view = jobs.customer_view(G, job)
    assert view["quotes"][0]["auto"] and view["quotes"][0]["status"] == "approved"
    assert not [m for m in (d.to_dict() for d in core.garage(G).collection("messages").stream()) if m["kind"] == "quote"]

    quotes.draft_quote(mechanic(), G, "q3", job, ["clutch plate"])
    settings.update_settings(owner(), G, "s2", {"quote_limit": 0})  # 0 = always ask the customer
    assert quotes.send_quote(mechanic(), G, "q4", "Q-78")["status"] == "pending"


def test_low_stock_level_applies_to_parts_without_their_own(garage):
    settings.update_settings(owner(), G, "s1", {"low_at": 3})
    part = inventory.part_ref(G, "clutch-splendor").get().to_dict()  # 2 in stock
    assert part["low_stock"] is True and inventory.low_at(G, part) == 3


def test_api_owner_only(client):  # noqa: F811
    assert client.get("/api/owner/settings", headers=h("raju-token")).status_code == 403
    assert client.put("/api/owner/settings", json={"changes": {"quote_limit": 0}}, headers=h("raju-token")).status_code == 403
    assert client.get("/api/owner/settings", headers=h("vikram-token")).json()["name"] == "Ganesh Motors"
    r = client.put("/api/owner/settings", json={"changes": {"quote_limit": 250}}, headers=h("owner-token"))
    assert r.status_code == 200 and r.json()["settings"]["quote_limit"] == 250
    assert client.put("/api/owner/settings", json={"changes": {"quote_limit": -5}}, headers=h("owner-token")).status_code == 409
    assert client.get("/api/owner/settings", headers=h("vikram-token")).json()["quote_limit"] == 2000  # untouched


def test_owner_voice_reads_the_limit(garage):
    ctx = SimpleNamespace(state={"garage_id": G, "uid": "o-asha", "name": "Asha", "role": "owner"}, function_call_id="t1")
    assert tools.garage_settings(ctx)["auto_approve_limit"] == 500
    mech = SimpleNamespace(state={"garage_id": G, "uid": "m-raju", "name": "Raju", "role": "mechanic"}, function_call_id="t2")
    assert "error" in tools.garage_settings(mech)
