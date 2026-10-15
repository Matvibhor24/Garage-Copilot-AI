from app import seed
from app.auth import check_pin
from app.services import core


def test_seed_two_isolated_garages(fake_db):
    seed.seed(fake_db, pin="4321")
    for g in ("shree-auto", "ganesh-motors"):
        items = [d.to_dict() for d in core.garage(g).collection("inventory").stream()]
        assert sum(1 for i in items if i.get("kind") != "consumable") == 30
        consumables = [i for i in items if i.get("kind") == "consumable"]
        assert len(consumables) >= 8 and all({"price", "cost", "billable", "low_at"} <= set(i) for i in consumables)
        assert all(i["cost"] <= i["price"] or not i["billable"] for i in items)
    raju = core.garage("shree-auto").collection("mechanics").document("m-raju").get().to_dict()
    assert check_pin("4321", raju["pin_hash"]) and not check_pin("0000", raju["pin_hash"])
    clutch = core.garage("shree-auto").collection("inventory").document("clutch-splendor").get().to_dict()
    assert (clutch["qty"], clutch["price"], clutch["labour"], clutch["cost"]) == (2, 650, 300, 455)
    assert {w["part_id"] for w in clutch["with"]} == {"gasket-clutch-cover", "bolt-m6", "washer-m6", "grease-10g"}
    assert not core.garage("ganesh-motors").collection("inventory").document("clutch-splendor").get().exists
