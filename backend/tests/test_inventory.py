import pytest

from app.services import core, inventory, jobs
from tests.helpers import mechanic, owner

G = "shree-auto"


@pytest.fixture
def garage(fake_db):
    core.garage(G).set({"name": "Shree Auto", "next_job_no": 1042})
    inv = core.garage(G).collection("inventory")
    inv.document("clutch-splendor").set({"name": "Clutch plate set", "fits": ["Splendor", "Splendor Plus"],
                                         "qty": 2, "price": 650, "labour": 300, "low_at": 1})
    inv.document("clutch-activa").set({"name": "Clutch shoe set", "fits": ["Activa"], "qty": 4, "price": 900, "labour": 350, "low_at": 1})
    inv.document("engine-oil").set({"name": "Engine oil 1L", "fits": ["universal"], "qty": 20, "price": 380, "low_at": 5})
    jobs.create_job(mechanic(), G, "r0", "MH12AB1234", "Splendor Plus", "Ramesh")


def test_check_stock_by_spoken_name(garage):
    out = inventory.check_stock(mechanic(), G, "r1", "clutch plates", "Splendor")
    assert out["matches"][0] == {"part_id": "clutch-splendor", "name": "Clutch plate set", "qty": 2,
                                 "price": 650, "labour": 300, "low_stock": False}
    assert all(m["part_id"] != "clutch-activa" for m in out["matches"])


def test_log_part_used_decrements_once(garage):
    out = inventory.log_part_used(mechanic(), G, "r2", "J-1042", "clutch plate")
    assert out["qty_left"] == 1 and out["low_stock"] is True and out["bill"] == 350 + 650
    again = inventory.log_part_used(mechanic(), G, "r2", "J-1042", "clutch plate")  # voice retry
    assert again == out
    assert inventory.part_ref(G, "clutch-splendor").get().to_dict()["qty"] == 1
    job = jobs.get_job(mechanic(), G, "J-1042")
    assert job["bill"] == 350 + 650 and len(job["parts"]) == 1


def test_cannot_use_more_than_stock(garage):
    with pytest.raises(core.Invalid):
        inventory.log_part_used(mechanic(), G, "r3", "J-1042", "clutch-splendor", qty=3)


def test_restock_clears_low_flag(garage):
    inventory.log_part_used(mechanic(), G, "r2", "J-1042", "clutch plate")
    assert [p["id"] for p in inventory.list_inventory(owner(), G, low_only=True)] == ["clutch-splendor"]
    inventory.restock(owner(), G, "r4", "clutch-splendor", 5)
    assert inventory.list_inventory(owner(), G, low_only=True) == []


def test_reorder_ask_once_then_owner_answers(garage):
    inventory.log_part_used(mechanic(), G, "r2", "J-1042", "clutch plate")
    first = inventory.ask_reorder(mechanic(), G, "a1", "clutch-splendor")
    assert first["already_asked"] is False
    assert inventory.ask_reorder(mechanic(), G, "a2", "clutch-splendor")["already_asked"] is True
    owner_msgs = [d.to_dict() for d in core.garage(G).collection("messages").stream() if d.to_dict()["to"] == "owner"]
    assert len(owner_msgs) == 1
    inventory.reorder_later(owner(), G, "l1", "clutch-splendor")
    assert inventory.ask_ref(G, "clutch-splendor").get().to_dict()["status"] == "later"
    inventory.restock(owner(), G, "s1", "clutch-splendor", 5)
    assert not inventory.ask_ref(G, "clutch-splendor").get().exists
