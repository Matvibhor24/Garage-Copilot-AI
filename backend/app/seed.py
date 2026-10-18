"""Seed two garages (config, people, ~30 parts each, one past job for vehicle history).

Run against the emulator or a real project:
    FIRESTORE_EMULATOR_HOST=localhost:8080 uv run python -m app.seed
Mechanic PIN comes from SEED_PIN (default 1234, demo only).
"""

import os

from app import db
from app.auth import hash_pin

# (id, name, fits, qty, price, labour)
TWO_WHEELER_PARTS = [
    ("clutch-splendor", "Clutch plate set", ["Splendor", "Splendor Plus", "Passion"], 2, 650, 300),
    ("clutch-pulsar", "Clutch plate set", ["Pulsar 150", "Pulsar"], 3, 820, 350),
    ("clutch-cable-splendor", "Clutch cable", ["Splendor", "Splendor Plus"], 6, 140, 80),
    ("brake-pad-activa", "Brake shoe set", ["Activa", "Jupiter"], 5, 280, 150),
    ("brake-pad-pulsar", "Front disc brake pad", ["Pulsar 150", "Pulsar", "Apache"], 4, 450, 150),
    ("brake-shoe-splendor", "Brake shoe set", ["Splendor", "Splendor Plus", "Passion"], 6, 260, 150),
    ("chain-kit-splendor", "Chain sprocket kit", ["Splendor", "Splendor Plus"], 3, 1150, 250),
    ("chain-kit-pulsar", "Chain sprocket kit", ["Pulsar 150", "Pulsar"], 2, 1650, 300),
    ("engine-oil-1l", "Engine oil 1L 10W30", ["universal"], 24, 380, 0),
    ("engine-oil-800", "Engine oil 800ml 10W30", ["universal"], 18, 320, 0),
    ("gear-oil-activa", "Gear oil 120ml", ["Activa", "Jupiter", "Access"], 10, 90, 0),
    ("air-filter-splendor", "Air filter", ["Splendor", "Splendor Plus", "Passion"], 7, 180, 50),
    ("air-filter-activa", "Air filter", ["Activa"], 6, 220, 50),
    ("spark-plug", "Spark plug", ["universal"], 20, 120, 50),
    ("oil-filter-pulsar", "Oil filter", ["Pulsar 150", "Pulsar"], 5, 150, 50),
    ("battery-12v-5ah", "Battery 12V 5Ah", ["universal"], 3, 1450, 100),
    ("headlight-bulb", "Headlight bulb 35W", ["universal"], 12, 110, 50),
    ("indicator-bulb", "Indicator bulb", ["universal"], 25, 30, 20),
    ("tyre-rear-splendor", "Rear tyre 2.75-18", ["Splendor", "Splendor Plus", "Passion"], 2, 1650, 150),
    ("tube-18", "Tube 18 inch", ["universal"], 8, 280, 100),
    ("accelerator-cable", "Accelerator cable", ["Splendor", "Splendor Plus", "Passion"], 5, 130, 80),
    ("brake-cable-activa", "Rear brake cable", ["Activa", "Jupiter"], 4, 160, 80),
    ("carburettor-kit", "Carburettor repair kit", ["Splendor", "Splendor Plus"], 3, 350, 250),
    ("drive-belt-activa", "Drive belt", ["Activa"], 2, 750, 300),
    ("roller-set-activa", "Variator roller set", ["Activa", "Jupiter"], 3, 420, 250),
    ("mirror-pair", "Mirror pair", ["universal"], 6, 240, 30),
    ("horn-12v", "Horn 12V", ["universal"], 5, 190, 50),
    ("fork-oil-seal", "Front fork oil seal", ["Splendor", "Splendor Plus", "Pulsar"], 4, 220, 300),
    ("coolant-500", "Coolant 500ml", ["universal"], 8, 180, 0),
    ("chain-lube", "Chain lube spray", ["universal"], 9, 260, 0),
]

FOUR_WHEELER_PARTS = [
    ("brake-pad-swift", "Front brake pad set", ["Swift", "Dzire"], 4, 1450, 400),
    ("brake-pad-i20", "Front brake pad set", ["i20", "Venue"], 3, 1650, 400),
    ("clutch-kit-swift", "Clutch kit", ["Swift", "Dzire", "Baleno"], 2, 5200, 1800),
    ("clutch-kit-alto", "Clutch kit", ["Alto", "WagonR"], 2, 3600, 1500),
    ("oil-filter-maruti", "Oil filter", ["Swift", "Dzire", "Baleno", "Alto", "WagonR"], 10, 220, 50),
    ("oil-filter-hyundai", "Oil filter", ["i20", "Venue", "Creta"], 8, 260, 50),
    ("air-filter-swift", "Air filter", ["Swift", "Dzire"], 6, 380, 50),
    ("air-filter-creta", "Air filter", ["Creta", "Venue"], 4, 520, 50),
    ("cabin-filter", "Cabin AC filter", ["universal"], 9, 350, 100),
    ("engine-oil-3l", "Engine oil 3L 5W30", ["universal"], 15, 1650, 0),
    ("engine-oil-4l", "Engine oil 4L 5W30", ["universal"], 10, 2150, 0),
    ("coolant-1l", "Coolant 1L", ["universal"], 12, 320, 0),
    ("wiper-blade-pair", "Wiper blade pair", ["universal"], 7, 450, 50),
    ("spark-plug-4w", "Spark plug (set of 4)", ["Swift", "Dzire", "Baleno", "i20"], 5, 1200, 200),
    ("battery-35ah", "Battery 35Ah", ["universal"], 3, 4200, 150),
    ("headlight-h4", "Headlight bulb H4", ["universal"], 10, 280, 80),
    ("brake-fluid", "Brake fluid DOT4 500ml", ["universal"], 8, 260, 100),
    ("timing-belt-alto", "Timing belt", ["Alto", "WagonR"], 2, 1350, 900),
    ("drive-belt-swift", "Alternator drive belt", ["Swift", "Dzire"], 3, 650, 300),
    ("disc-rotor-swift", "Front brake disc", ["Swift", "Dzire"], 2, 2400, 500),
    ("shock-absorber-swift", "Front shock absorber", ["Swift", "Dzire"], 2, 2900, 700),
    ("tie-rod-end", "Tie rod end", ["Swift", "Dzire", "Alto"], 4, 550, 400),
    ("ac-gas", "AC gas refill R134a", ["universal"], 6, 1200, 400),
    ("horn-pair", "Horn pair", ["universal"], 4, 650, 150),
    ("fuel-filter", "Fuel filter", ["Swift", "Dzire", "i20"], 5, 480, 150),
    ("clutch-cable-alto", "Clutch cable", ["Alto", "WagonR"], 4, 420, 250),
    ("tyre-185-65-r15", "Tyre 185/65 R15", ["Swift", "Dzire", "i20", "Baleno"], 4, 4800, 200),
    ("wheel-alignment", "Wheel alignment", ["universal"], 99, 0, 500),
    ("gear-oil-2l", "Gear oil 2L", ["universal"], 6, 900, 200),
    ("bulb-tail", "Tail lamp bulb", ["universal"], 20, 60, 30),
]

# Consumables (C13): small items used every time a part is fitted. Plausible prices, not from any catalogue.
# (id, name, fits, qty, price, cost, billable, low_at). billable: charged to the customer; else the garage's own cost.
TWO_WHEELER_CONSUMABLES = [
    ("gasket-clutch-cover", "Clutch cover gasket", ["Splendor", "Splendor Plus", "Passion"], 12, 90, 45, False, 3),
    ("bolt-m6", "M6 bolt", ["universal"], 150, 5, 2, False, 20),
    ("bolt-m8", "M8 bolt", ["universal"], 90, 8, 3, False, 15),
    ("washer-m6", "M6 washer", ["universal"], 200, 2, 1, False, 30),
    ("split-pin", "Split pin", ["universal"], 80, 3, 1, False, 10),
    ("grease-10g", "Grease (10 g)", ["universal"], 60, 15, 8, False, 10),
    ("chain-lube-shot", "Chain lube (one job)", ["universal"], 40, 40, 18, True, 6),
    ("oil-topup-100", "Engine oil top-up 100 ml", ["universal"], 50, 45, 30, True, 8),
    ("drain-washer", "Oil drain plug washer", ["universal"], 100, 15, 4, True, 15),
    ("brake-cleaner-shot", "Brake cleaner (one job)", ["universal"], 30, 30, 20, True, 5),
]
FOUR_WHEELER_CONSUMABLES = [
    ("bolt-m8", "M8 bolt", ["universal"], 120, 10, 4, False, 15),
    ("bolt-m10", "M10 bolt", ["universal"], 80, 15, 6, False, 10),
    ("washer-m8", "M8 washer", ["universal"], 150, 3, 1, False, 20),
    ("split-pin", "Split pin", ["universal"], 60, 5, 2, False, 10),
    ("grease-20g", "Grease (20 g)", ["universal"], 40, 30, 15, False, 8),
    ("drain-washer-4w", "Sump plug washer", ["universal"], 80, 25, 8, True, 10),
    ("brake-cleaner-4w", "Brake cleaner (one job)", ["universal"], 25, 120, 80, True, 5),
    ("gasket-clutch-4w", "Clutch housing gasket", ["Swift", "Dzire", "Baleno"], 6, 180, 95, True, 2),
]
# What each common job uses besides the main part: part_id -> [(consumable_id, qty per part fitted)]
TWO_WHEELER_WITH = {
    "clutch-splendor": [("gasket-clutch-cover", 1), ("bolt-m6", 4), ("washer-m6", 4), ("grease-10g", 1)],
    "clutch-pulsar": [("bolt-m6", 4), ("washer-m6", 4), ("oil-topup-100", 1)],
    "brake-shoe-splendor": [("split-pin", 2), ("grease-10g", 1), ("brake-cleaner-shot", 1)],
    "brake-pad-activa": [("split-pin", 2), ("brake-cleaner-shot", 1)],
    "brake-pad-pulsar": [("brake-cleaner-shot", 1)],
    "chain-kit-splendor": [("bolt-m8", 4), ("split-pin", 1), ("chain-lube-shot", 1)],
    "chain-kit-pulsar": [("bolt-m8", 4), ("split-pin", 1), ("chain-lube-shot", 1)],
    "engine-oil-1l": [("drain-washer", 1)],
    "engine-oil-800": [("drain-washer", 1)],
}
FOUR_WHEELER_WITH = {
    "clutch-kit-swift": [("gasket-clutch-4w", 1), ("bolt-m10", 6), ("grease-20g", 1)],
    "brake-pad-swift": [("brake-cleaner-4w", 1), ("grease-20g", 1)],
    "brake-pad-i20": [("brake-cleaner-4w", 1), ("grease-20g", 1)],
    "engine-oil-3l": [("drain-washer-4w", 1)],
    "engine-oil-4l": [("drain-washer-4w", 1)],
}


def part_cost(price: int) -> int:
    """What the garage paid for a part: about 70% of the selling price, in steps of ₹5 (seed data only)."""
    return int(round(price * 0.7 / 5) * 5)


GARAGES = [
    {
        "id": "shree-auto",
        "doc": {"name": "Shree Auto", "city": "Pune", "next_job_no": 1042, "next_quote_no": 77},
        "config": {"quote_limit": 500, "service_fee": 350, "lang": "en", "supplier": "Sai Spares", "reorder_qty": 5, "low_at": 1, "currency": "INR"},
        "owner": {"uid": "o-asha", "name": "Asha", "phone": "+919800000001"},
        "mechanics": [{"uid": "m-raju", "name": "Raju"}, {"uid": "m-salim", "name": "Salim"}],
        "parts": TWO_WHEELER_PARTS,
        "consumables": TWO_WHEELER_CONSUMABLES,
        "with": TWO_WHEELER_WITH,
        "customers": [{"id": "c-919800000101", "name": "Ramesh", "phone": "+919800000101", "lang": "mr"}],
        "history": [{
            "id": "J-0957", "plate": "MH12AB1234", "vehicle": "Splendor Plus", "owner": "Ramesh",
            "customer_id": "c-919800000101", "complaint": "clutch hard, service",
            "created_at": "2026-02-12T05:00:00+00:00", "closed_at": "2026-02-12T09:30:00+00:00",
            "parts": [{"part_id": "clutch-cable-splendor", "name": "Clutch cable", "qty": 1, "price": 140, "total": 140}],
            "labour": 80, "bill": 220,
        }],
    },
    {
        "id": "ganesh-motors",
        "doc": {"name": "Ganesh Motors", "city": "Nashik", "next_job_no": 310, "next_quote_no": 12},
        "config": {"quote_limit": 2000, "service_fee": 350, "lang": "en", "supplier": "Nashik Auto Parts", "reorder_qty": 3, "low_at": 1, "currency": "INR"},
        "owner": {"uid": "o-vikram", "name": "Vikram", "phone": "+919800000002"},
        "mechanics": [{"uid": "m-sunil", "name": "Sunil"}],
        "parts": FOUR_WHEELER_PARTS,
        "consumables": FOUR_WHEELER_CONSUMABLES,
        "with": FOUR_WHEELER_WITH,
        "customers": [],
        "history": [],
    },
]


def seed(client, pin: str = "1234") -> None:
    for g in GARAGES:
        ref = client.collection("garages").document(g["id"])
        ref.set(g["doc"] | {"owner_uid": g["owner"]["uid"]})
        ref.collection("config").document("settings").set(g["config"])
        ref.collection("mechanics").document(g["owner"]["uid"]).set(g["owner"] | {"role": "owner"})
        client.collection("phone_index").document(g["owner"]["phone"]).set(
            {"garage_id": g["id"], "uid": g["owner"]["uid"], "role": "owner", "name": g["owner"]["name"]})
        for m in g["mechanics"]:
            ref.collection("mechanics").document(m["uid"]).set(m | {"role": "mechanic", "pin_hash": hash_pin(pin)})
        for part_id, name, fits, qty, price, labour in g["parts"]:
            doc = {"name": name, "fits": fits, "qty": qty, "price": price, "cost": part_cost(price), "labour": labour,
                   "low_stock": qty <= g["config"]["low_at"], "reorder_qty": g["config"]["reorder_qty"]}
            if part_id in g["with"]:
                doc["with"] = [{"part_id": c, "qty": n} for c, n in g["with"][part_id]]
            ref.collection("inventory").document(part_id).set(doc)
        for part_id, name, fits, qty, price, cost, billable, low_at in g["consumables"]:
            ref.collection("inventory").document(part_id).set({
                "name": name, "fits": fits, "qty": qty, "price": price, "cost": cost, "labour": 0, "kind": "consumable",
                "billable": billable, "low_at": low_at, "low_stock": qty <= low_at, "reorder_qty": low_at * 4,
            })
        for c in g["customers"]:
            ref.collection("customers").document(c["id"]).set({k: v for k, v in c.items() if k != "id"})
        for h in g["history"]:
            job = {k: v for k, v in h.items() if k != "id"}
            ref.collection("jobs").document(h["id"]).set(job | {"stage": "done", "status": "done", "lang": "mr"})


if __name__ == "__main__":
    seed(db.client(), os.environ.get("SEED_PIN", "1234"))
    print("Seeded:", ", ".join(g["id"] for g in GARAGES))
