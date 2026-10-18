"""C17 owner records: jobs (filters, pagination, totals, CSV), customers, vehicles, staff, deactivation, voice tools."""

import csv
import io
from types import SimpleNamespace

import pytest

from app import tools
from app.services import core, jobs, people, reports
from tests.helpers import Clock, owner
from tests.test_owner_api import client, h  # noqa: F401  (fixture)

G = "shree-auto"


def add_job(job_id, day, mechanic=("m-raju", "Raju"), status="done", plate="MH12AB1234", owner_name="Ramesh",
            customer_id="c-919800000101", bill=950, minutes=(15, 60), garage=G, vehicle="Splendor Plus"):
    """A finished (or open) job written straight to Firestore, like the ones the service layer leaves behind."""
    created = f"{day}T04:30:00+00:00"  # 10:00 IST
    closed = f"{day}T06:00:00+00:00" if status == "done" else None
    core.garage(garage).collection("jobs").document(job_id).set({
        "plate": plate, "vehicle": vehicle, "owner": owner_name, "phone": "+919800000101", "customer_id": customer_id,
        "complaint": "service", "stage": "done" if status == "done" else "service", "status": status,
        "mechanic_uid": mechanic[0], "mechanic_name": mechanic[1], "created_at": created, "closed_at": closed,
        "stage_started_at": created, "stage_minutes": {"intake": minutes[0], "service": minutes[1]},
        "parts": [{"part_id": "x", "name": "Clutch plate set", "qty": 1, "price": bill - 300, "total": bill - 300,
                   "cost": 455}],
        "labour": 300, "bill": bill if status == "done" else 0})


@pytest.fixture
def history(client, monkeypatch):  # noqa: F811
    clock = Clock(monkeypatch, start="2026-10-15T12:00:00+05:30")  # a Thursday
    add_job("J-0901", "2026-09-20", bill=950)
    add_job("J-0950", "2026-10-02", mechanic=("m-salim", "Salim"), plate="MH14GH7710", owner_name="Vikas",
            customer_id="c-919800000303", bill=1450, vehicle="Pulsar 150")
    add_job("J-1001", "2026-10-13", bill=1250)
    add_job("J-1002", "2026-10-15", mechanic=("m-salim", "Salim"), bill=2000, plate="MH12CD5678", owner_name="Sunita",
            customer_id="c-919800000202", vehicle="Activa 6G")
    add_job("J-1003", "2026-10-15", status="open", plate="MH12XY0001", owner_name="Kiran", customer_id="c-919800000404")
    for cid, name, phone in (("c-919800000303", "Vikas", "+919800000303"), ("c-919800000202", "Sunita", "+919800000202"),
                             ("c-919800000404", "Kiran", "+919800000404")):
        core.garage(G).collection("customers").document(cid).set({"name": name, "phone": phone, "lang": "en"})
    core.audit(G, core.actor(G, "m-raju", "mechanic", "Raju"), "log_part_used", {"qty_used": 2, "job_id": "J-1003"}, "p1")
    add_job("J-0300", "2026-10-15", garage="ganesh-motors", mechanic=("m-sunil", "Sunil"), plate="MH15ZZ9999")
    return clock


def get(client, path, token="owner-token"):  # noqa: F811
    r = client.get(path, headers=h(token))
    assert r.status_code == 200, r.text
    return r.json()


def test_jobs_newest_first_with_filters_and_totals(client, history):  # noqa: F811
    out = get(client, "/api/owner/jobs")
    assert [j["job_id"] for j in out["jobs"]] == ["J-1003", "J-1002", "J-1001", "J-0950", "J-0901", "J-0957"]  # not J-0300
    row = out["jobs"][1]
    assert row | {} == row and (row["bill"], row["parts"], row["labour"], row["minutes"], row["status"]) == \
        (2000, 1700, 300, 75, "closed")
    # + the seed's J-0957 (Feb, ₹220, no stage times or costs recorded)
    assert out["totals"] == {"jobs": 6, "closed": 5, "revenue": 5870, "cost": 4 * 455, "margin": 5870 - 4 * 455,
                             "average_bill": 1174, "average_minutes": 60}
    month = get(client, "/api/owner/jobs?from=2026-10-01&to=2026-10-31&status=closed")
    assert [j["job_id"] for j in month["jobs"]] == ["J-1002", "J-1001", "J-0950"]
    assert [j["job_id"] for j in get(client, "/api/owner/jobs?mechanic=Salim")["jobs"]] == ["J-1002", "J-0950"]
    assert [j["job_id"] for j in get(client, "/api/owner/jobs?q=mh12 cd")["jobs"]] == ["J-1002"]
    assert [j["job_id"] for j in get(client, "/api/owner/jobs?q=vikas")["jobs"]] == ["J-0950"]
    assert [j["job_id"] for j in get(client, "/api/owner/jobs?status=open")["jobs"]] == ["J-1003"]
    assert get(client, "/api/owner/jobs?q=MH12AB1234", "vikram-token")["jobs"] == []  # garage B never sees A


def test_pagination_50_per_page(client, history):  # noqa: F811
    for n in range(60):
        add_job(f"J-2{n:03d}", "2026-08-01")
    first = get(client, "/api/owner/jobs")
    assert len(first["jobs"]) == 50 and first["next_cursor"] == "50" and first["totals"]["jobs"] == 66
    second = get(client, f"/api/owner/jobs?cursor={first['next_cursor']}")
    assert len(second["jobs"]) == 16 and second["next_cursor"] == ""
    assert not {j["job_id"] for j in first["jobs"]} & {j["job_id"] for j in second["jobs"]}


def test_csv_export_follows_the_filter(client, history):  # noqa: F811
    r = client.get("/api/owner/jobs.csv?mechanic=Raju", headers=h("owner-token"))
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert [x["job_id"] for x in rows] == ["J-1003", "J-1001", "J-0901"] and rows[1]["bill"] == "1250"
    assert client.get("/api/owner/jobs.csv", headers=h("raju-token")).status_code == 403


def test_job_detail_has_timeline_money_and_messages(client, history):  # noqa: F811
    from tests.helpers import mechanic

    job = jobs.create_job(mechanic(), G, "r9", "MH12QQ1111", "Splendor Plus", "Neha", "+919811111111")["job_id"]
    d = get(client, f"/api/owner/jobs/{job}")
    assert d["timeline"][0]["label"] == "Checked in" and d["money"]["bill"] == 350 and d["customer_url"].startswith("http")
    assert d["messages"][0]["kind"] == "status_link" and d["quotes"] == [] and d["photos"] == []
    assert client.get(f"/api/owner/jobs/{job}", headers=h("vikram-token")).status_code == 404


def test_customers_and_vehicles(client, history):  # noqa: F811
    cs = get(client, "/api/owner/customers")
    ramesh = next(c for c in cs if c["name"] == "Ramesh")
    assert (ramesh["visits"], ramesh["total_spent"], ramesh["last_visit"]) == (3, 2420, "2026-10-13")
    assert ramesh["vehicles"] == ["Splendor Plus · MH12AB1234"]
    assert [c["name"] for c in get(client, "/api/owner/customers?q=sun")] == ["Sunita"]
    kiran = get(client, "/api/owner/customers/c-919800000404")
    assert kiran["open_jobs"] == ["J-1003"] and kiran["jobs"][0]["status"] == "open"
    assert get(client, "/api/owner/customers", "vikram-token") == []

    vs = get(client, "/api/owner/vehicles")
    splendor = next(v for v in vs if v["plate"] == "MH12AB1234")
    assert (splendor["visits"], splendor["total_spent"], splendor["last_visit"]) == (3, 2420, "2026-10-13")
    hist = get(client, "/api/owner/vehicles/MH12 AB 1234")
    assert [x["job_id"] for x in hist["history"]] == ["J-1001", "J-0901", "J-0957"]
    assert client.get("/api/owner/vehicles/MH12AB1234", headers=h("vikram-token")).status_code == 404


def test_staff_numbers_and_chart(client, history):  # noqa: F811
    week = get(client, "/api/owner/staff?period=week")
    assert (week["from"], week["to"]) == ("2026-10-12", "2026-10-15")
    raju = next(m for m in week["mechanics"] if m["name"] == "Raju")
    assert raju["finished"] == {"today": 0, "week": 1, "month": 1}
    assert (raju["open_now"], raju["revenue"], raju["average_minutes"], raju["parts_logged"]) == (1, 1250, 75, 2)
    assert [d["jobs"] for d in raju["per_day"]] == [0, 1, 0, 0]
    salim = next(m for m in get(client, "/api/owner/staff?period=month")["mechanics"] if m["name"] == "Salim")
    assert salim["finished"]["month"] == 2 and salim["revenue"] == 3450
    assert week["count"] == 2


def test_deactivated_mechanic_cannot_sign_in_but_history_stays(client, history):  # noqa: F811
    r = client.post("/api/owner/mechanics/m-raju/deactivate", json={}, headers=h("owner-token"))
    assert r.status_code == 200 and r.json()["active"] is False
    login = client.post("/api/auth/pin", json={"garage_id": G, "name": "Raju", "pin": "1234"})
    assert login.status_code == 401 and "switched off" in login.json()["detail"]
    assert [j["job_id"] for j in get(client, "/api/owner/jobs?mechanic=Raju")["jobs"]] == ["J-1003", "J-1001", "J-0901"]
    assert not next(m for m in get(client, "/api/owner/staff")["mechanics"] if m["name"] == "Raju")["active"]
    assert client.post("/api/owner/mechanics/o-asha/deactivate", json={}, headers=h("owner-token")).status_code == 403
    assert client.post("/api/owner/mechanics/m-raju/deactivate", json={}, headers=h("raju-token")).status_code == 403
    client.post("/api/owner/mechanics/m-raju/reactivate", json={}, headers=h("owner-token"))
    assert client.post("/api/auth/pin", json={"garage_id": G, "name": "Raju", "pin": "1234"}).status_code == 200
    people.mechanic_ref(G, "m-raju").update({"active": False})
    with pytest.raises(core.Forbidden):
        people.check_mechanic_pin(G, "Raju", "1234")


def test_owner_voice_answers_from_records(client, history):  # noqa: F811
    ctx = SimpleNamespace(state={"garage_id": G, "uid": "o-asha", "name": "Asha", "role": "owner"}, function_call_id="v1")
    out = tools.mechanic_jobs("Raju", "week", ctx)
    assert out["mechanics"][0]["finished"]["week"] == 1
    month = tools.revenue_for("month", ctx)
    assert (month["closed"], month["revenue"]) == (3, 4700)  # closed this month, whenever they came in
    last = tools.vehicle_last_visit("MH12 AB 1234", ctx)
    assert (last["last_visit"], last["bill"], last["found"]) == ("2026-10-13", 1250, True)
    assert tools.vehicle_last_visit("MH99ZZ0000", ctx)["found"] is False
    assert "error" in tools.mechanic_jobs("Nobody", "week", ctx)
    assert reports.period_range("month", reports.date(2026, 10, 15))[0] == reports.date(2026, 10, 1)
    _ = owner  # the helper is used by other test modules
