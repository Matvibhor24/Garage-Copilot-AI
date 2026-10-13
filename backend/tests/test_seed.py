from app import seed
from app.auth import check_pin
from app.services import core


def test_seed_two_isolated_garages(fake_db):
    seed.seed(fake_db, pin="4321")
    for g in ("shree-auto", "ganesh-motors"):
        assert len(list(core.garage(g).collection("inventory").stream())) == 30
    raju = core.garage("shree-auto").collection("mechanics").document("m-raju").get().to_dict()
    assert check_pin("4321", raju["pin_hash"]) and not check_pin("0000", raju["pin_hash"])
    clutch = core.garage("shree-auto").collection("inventory").document("clutch-splendor").get().to_dict()
    assert (clutch["qty"], clutch["price"], clutch["labour"]) == (2, 650, 300)
    assert not core.garage("ganesh-motors").collection("inventory").document("clutch-splendor").get().exists
