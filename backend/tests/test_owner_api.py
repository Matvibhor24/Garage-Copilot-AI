import pytest
from fastapi.testclient import TestClient

from app import auth, links, seed
from app.main import app
from app.services import core, inventory, jobs, quotes
from tests.helpers import Clock, mechanic

G = "shree-auto"
TOKENS = {
    "owner-token": {"uid": "o-asha", "garage": G, "role": "owner", "name": "Asha"},
    "raju-token": {"uid": "m-raju", "garage": G, "role": "mechanic", "name": "Raju"},
    "vikram-token": {"uid": "o-vikram", "garage": "ganesh-motors", "role": "owner", "name": "Vikram"},
    "new-phone": {"uid": "firebase-uid-9", "phone_number": "+919800000001"},
}


@pytest.fixture
def client(fake_db, monkeypatch):
    seed.seed(fake_db)
    minted = {}

    def verify(token):
        if token not in TOKENS:
            raise ValueError("bad")
        return TOKENS[token]

    monkeypatch.setattr(auth, "verify_id_token", verify)
    monkeypatch.setattr(auth, "custom_token", lambda uid, claims: minted.setdefault(uid, f"ct-{uid}"))
    monkeypatch.setattr(auth, "set_claims", lambda uid, claims: minted.update({uid: claims}))
    c = TestClient(app)
    c.minted = minted
    return c


def h(token):
    return {"Authorization": f"Bearer {token}"}


def test_owner_only_and_tenant_isolation(client):
    assert client.get("/api/owner/dashboard").status_code == 401
    assert client.get("/api/owner/dashboard", headers=h("forged")).status_code == 401
    assert client.get("/api/owner/dashboard", headers=h("raju-token")).status_code == 403
    jobs.create_job(mechanic(), G, "r1", "MH12AB1234", "Splendor Plus", "Ramesh")
    assert client.get("/api/owner/jobs/J-1042", headers=h("owner-token")).status_code == 200
    assert client.get("/api/owner/jobs/J-1042", headers=h("vikram-token")).status_code == 404
    vikram_parts = client.get("/api/owner/inventory", headers=h("vikram-token")).json()
    assert "clutch-splendor" not in {p["id"] for p in vikram_parts}


def test_dashboard_tiles_and_reorder(client, monkeypatch):
    clock = Clock(monkeypatch)
    clock.at("10:02")
    job = jobs.create_job(mechanic(), G, "r1", "MH12AB1234", "Splendor Plus", "Ramesh")["job_id"]
    quotes.draft_quote(mechanic(), G, "q1", job, ["clutch plate"])
    quotes.send_quote(mechanic(), G, "q2", "Q-77")
    d = client.get("/api/owner/dashboard", headers=h("owner-token")).json()
    assert d["open_jobs"] == 1 and len(d["pending_approvals"]) == 1
    customer = core.actor(G, "customer:J-1042", "customer", "Ramesh")
    quotes.decide_quote(customer, G, job, "Q-77", "approved")
    inventory.log_part_used(mechanic(), G, "r3", job, "clutch plate")
    clock.at("11:40")
    jobs.close_job(mechanic(), G, "r4", job)
    d = client.get("/api/owner/dashboard", headers=h("owner-token")).json()
    assert d["open_jobs"] == 0 and d["pending_approvals"] == [] and d["revenue_today"] == 950
    assert d["low_stock"] == [{"part_id": "clutch-splendor", "name": "Clutch plate set", "qty": 1}]
    clock.at("11:45")
    r = client.post("/api/owner/inventory/clutch-splendor/reorder", json={"request_id": "ro1"}, headers=h("owner-token"))
    assert r.json()["qty"] == 5 and r.json()["supplier"] == "Sai Spares"
    audit = client.get("/api/owner/audit", headers=h("owner-token")).json()
    assert audit[0]["action"] == "reorder" and {a["action"] for a in audit} >= {"create_job", "quote_approved", "close_job"}


def test_pin_login_invite_and_phone_claim(client):
    r = client.post("/api/auth/pin", json={"garage_id": G, "name": "Raju", "pin": "1234"})
    assert r.json()["claims"] == {"garage": G, "role": "mechanic", "name": "Raju"}
    assert client.post("/api/auth/pin", json={"garage_id": G, "name": "Raju", "pin": "9999"}).status_code == 401
    assert client.post("/api/auth/pin", json={"garage_id": "ganesh-motors", "name": "Raju", "pin": "1234"}).status_code == 401
    r = client.post("/api/owner/mechanics", json={"name": "Imran", "phone": "+91 98000 00077", "pin": "5555"}, headers=h("owner-token"))
    assert r.json()["uid"] == "m-imran"
    assert client.post("/api/auth/pin", json={"garage_id": G, "name": "imran", "pin": "5555"}).status_code == 200
    r = client.post("/api/auth/claim", headers=h("new-phone"))
    assert r.json()["claims"] == {"garage": G, "role": "owner", "name": "Asha"}
    assert client.minted["firebase-uid-9"]["garage"] == G


def test_pin_lockout(client):
    for _ in range(5):
        client.post("/api/auth/pin", json={"garage_id": G, "name": "Raju", "pin": "0000"})
    r = client.post("/api/auth/pin", json={"garage_id": G, "name": "Raju", "pin": "1234"})
    assert r.status_code == 401 and "too many" in r.json()["detail"]


def test_customer_session_token(client):
    jobs.create_job(mechanic(), G, "r1", "MH12AB1234", "Splendor Plus", "Ramesh")
    r = client.post(f"/api/j/{links.make_token(G, 'J-1042')}/session")
    assert r.json()["custom_token"] == "ct-customer:shree-auto:J-1042"


def test_dashboard_extras_and_staff_jobs(client):
    jobs.create_job(mechanic(), G, "r1", "MH12AB1234", "Splendor Plus", "Ramesh")
    inventory.log_part_used(mechanic(), G, "u1", "J-1042", "clutch plate")
    inventory.ask_reorder(mechanic(), G, "a1", "clutch-splendor")
    d = client.get("/api/owner/dashboard", headers=h("owner-token")).json()
    assert d["garage"] == {"id": G, "name": "Shree Auto", "city": "Pune"}
    assert d["reorder_asks"][0]["part_id"] == "clutch-splendor"
    assert d["jobs"][0]["id"] == "J-1042" and d["jobs"][0]["bill"] == 650
    assert {m["kind"] for m in d["messages"]} >= {"status_link", "reorder_ask"}
    staff = client.get("/api/jobs", headers=h("raju-token")).json()
    assert [j["id"] for j in staff] == ["J-1042"] and "parts" not in staff[0]


def test_pin_login_dev_token_when_auth_disabled(client, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "AUTH_DISABLED", True)
    r = client.post("/api/auth/pin", json={"garage_id": G, "name": "Raju", "pin": "1234"}).json()
    assert r["dev_token"] == "dev:shree-auto:m-raju:mechanic"
    assert client.get("/api/me", headers=h(r["dev_token"])).json()["uid"] == "m-raju"
