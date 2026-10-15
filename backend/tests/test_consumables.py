"""C13 consumables: fitted with a part, out of stock together, billed or costed, in quotes and the owner's numbers."""

from types import SimpleNamespace

import pytest

from app import seed, tools
from app.services import core, inventory, jobs, owner, quotes
from tests.helpers import mechanic
from tests.helpers import owner as owner_actor

G = "shree-auto"


@pytest.fixture
def job(fake_db):
    seed.seed(fake_db)
    return jobs.create_job(mechanic(), G, "r0", "MH12AB1234", "Splendor Plus", "Ramesh", "+919800000101")["job_id"]


def qty(part_id):
    return inventory.part_ref(G, part_id).get().to_dict()["qty"]


def test_part_and_its_consumables_leave_stock_together_once(job):
    before = {p: qty(p) for p in ("clutch-splendor", "gasket-clutch-cover", "bolt-m6", "washer-m6", "grease-10g")}
    out = inventory.log_part_used(mechanic(), G, "u1", job, "clutch plate")
    assert out["say"] == "Logged 1 Clutch plate set and the usual fittings."
    assert inventory.log_part_used(mechanic(), G, "u1", job, "clutch plate") == out  # voice retry: no second decrement
    after = {p: qty(p) for p in before}
    assert {p: before[p] - after[p] for p in before} == {"clutch-splendor": 1, "gasket-clutch-cover": 1, "bolt-m6": 4,
                                                           "washer-m6": 4, "grease-10g": 1}


def test_billing_split_garage_cost_and_margin(job):
    inventory.log_part_used(mechanic(), G, "u1", job, "clutch plate")      # fittings are the garage's own cost
    inventory.log_part_used(mechanic(), G, "u2", job, "brake shoe")        # brake cleaner is billable
    j = jobs.get_job(mechanic(), G, job)
    billed = {line["name"]: line["total"] for line in j["parts"]}
    assert billed == {"Clutch plate set": 650, "Brake shoe set": 260, "Brake cleaner (one job)": 30}
    assert j["bill"] == 940
    assert {c["name"] for c in j["consumables"]} == {"Clutch cover gasket", "M6 bolt", "M6 washer", "Grease (10 g)",
                                                     "Split pin"}
    m = jobs.money(j)
    assert (m["parts"], m["consumables"], m["labour"], m["bill"]) == (910, 30, 0, 940)
    # cost: clutch 455 + brake shoe 180 + brake cleaner 20 + gasket 45 + bolts 4x2 + washers 4x1 + grease 2x8 + pins 2x1
    assert m["cost"] == 455 + 180 + 20 + 45 + 8 + 4 + 16 + 2
    assert m["margin"] == 940 - m["cost"]
    view = jobs.customer_view(G, job)
    assert [p["name"] for p in view["parts"]] == ["Clutch plate set", "Brake shoe set", "Brake cleaner (one job)"]


def test_shortfall_still_logs_the_main_part(job):
    inventory.part_ref(G, "bolt-m6").update({"qty": 1})
    out = inventory.log_part_used(mechanic(), G, "u1", job, "clutch plate")
    assert out["qty_used"] == 1 and qty("clutch-splendor") == 1
    assert out["shortfall"] == [{"part_id": "bolt-m6", "name": "M6 bolt", "needed": 4, "missing": 3}]
    assert out["say"].endswith("Short on M6 bolt (3 missing).")
    bolt = inventory.part_ref(G, "bolt-m6").get().to_dict()
    assert bolt["qty"] == 0 and bolt["low_stock"] is True
    assert "bolt-m6" in out["low_consumables"]


def test_quote_includes_billable_consumables(job):
    q = quotes.draft_quote(mechanic(), G, "q1", job, ["brake shoe", "chain kit"])
    lines = {line["name"]: (line["qty"], line["total"]) for line in q["lines"]}
    assert lines == {"Brake shoe set": (1, 260), "Brake cleaner (one job)": (1, 30), "Chain sprocket kit": (1, 1150),
                     "Chain lube (one job)": (1, 40)}
    assert q["total"] == 260 + 30 + 1150 + 40 + 250  # + the higher usual labour
    clutch = quotes.draft_quote(mechanic(), G, "q2", job, ["clutch plate"])
    assert clutch["total"] == 950  # its fittings are not billable: the demo quote is unchanged


def test_owner_sees_cost_and_margin(job):
    inventory.log_part_used(mechanic(), G, "u1", job, "clutch plate")
    jobs.close_job(mechanic(), G, "c1", job)
    d = owner.dashboard(owner_actor(), G)
    card = next(j for j in d["jobs"] if j["id"] == job)
    assert card["money"]["bill"] == 650 and card["money"]["cost"] == 455 + 45 + 8 + 4 + 8
    assert d["cost_today"] == card["money"]["cost"] and d["margin_today"] == 650 - card["money"]["cost"]
    ctx = SimpleNamespace(state={"garage_id": G, "uid": "o-asha", "name": "Asha", "role": "owner"}, function_call_id="o1")
    details = tools.job_details(job, ctx)
    assert details["money"]["margin"] == card["money"]["margin"]
    assert {c["name"] for c in details["garage_consumables"]} == {"Clutch cover gasket", "M6 bolt", "M6 washer",
                                                                 "Grease (10 g)"}


def test_consumables_have_their_own_low_flags(job):
    low = [p["id"] for p in inventory.list_inventory(owner_actor(), G, low_only=True)]
    assert "bolt-m6" not in low
    inventory.part_ref(G, "split-pin").update({"qty": 11})
    inventory.log_part_used(mechanic(), G, "u1", job, "brake shoe")  # uses 2 split pins: 9 left, low_at 10
    assert inventory.part_ref(G, "split-pin").get().to_dict()["low_stock"] is True
    assert core.garage(G).collection("inventory").document("split-pin").get().to_dict()["kind"] == "consumable"
