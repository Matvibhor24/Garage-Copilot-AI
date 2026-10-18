import pytest

from app.services import core, jobs
from tests.helpers import Clock, mechanic

G = "shree-auto"


@pytest.fixture
def garage(fake_db):
    core.garage(G).set({"name": "Shree Auto", "next_job_no": 1042})
    core.garage(G).collection("config").document("settings").set({"quote_limit": 500, "lang": "mr"})


def test_create_job_numbers_and_snapshot(garage, monkeypatch):
    Clock(monkeypatch).at("10:02")
    out = jobs.create_job(mechanic(), G, "r1", "MH12 AB 1234", "Splendor Plus", "Ramesh", "98xxxxxx01", "clutch slipping, service")
    assert out["job_id"] == "J-1042"
    job = jobs.get_job(mechanic(), G, "J-1042")
    assert job["plate"] == "MH12AB1234"
    assert job["quote_limit"] == 500 and job["lang"] == "mr" and job["stage"] == "intake"
    assert jobs.create_job(mechanic(), G, "r2", "MH12 X 1", "Activa", "Seema")["job_id"] == "J-1043"
    assert jobs.create_job(mechanic(), G, "r1", "ignored", "ignored", "ignored")["job_id"] == "J-1042"


def test_stage_minutes_and_close(garage, monkeypatch):
    clock = Clock(monkeypatch)
    clock.at("10:02")
    jobs.create_job(mechanic(), G, "r1", "MH12AB1234", "Splendor Plus", "Ramesh")
    clock.at("10:23")
    jobs.update_stage(mechanic(), G, "r2", "J-1042", "washing")
    clock.at("10:41")
    out = jobs.update_stage(mechanic(), G, "r3", "J-1042", "service")
    assert out["previous_minutes"] == 18
    job = jobs.get_job(mechanic(), G, "J-1042")
    assert job["stage_minutes"] == {"intake": 21, "washing": 18}
    clock.at("11:40")
    closed = jobs.close_job(mechanic(), G, "r4", "J-1042")
    assert closed["bill"] == 350 and closed["stage"] == "done"  # the service charge alone
    with pytest.raises(core.Invalid):
        jobs.update_stage(mechanic(), G, "r5", "J-1042", "washing")
    stages = [d.to_dict() for d in jobs.job_ref(G, "J-1042").collection("stages").stream()]
    assert [s["name"] for s in stages] == ["intake", "washing", "service", "done"]


def test_unknown_stage_rejected(garage):
    jobs.create_job(mechanic(), G, "r1", "MH12AB1234", "Splendor Plus", "Ramesh")
    with pytest.raises(core.Invalid):
        jobs.update_stage(mechanic(), G, "r2", "J-1042", "painting")


def test_other_garage_cannot_read_job(garage):
    jobs.create_job(mechanic(), G, "r1", "MH12AB1234", "Splendor Plus", "Ramesh")
    with pytest.raises(core.Forbidden):
        jobs.get_job(mechanic("other"), G, "J-1042")


def test_vehicle_history_first_visit(garage):
    out = jobs.vehicle_history(mechanic(), G, "h1", "MH12 AB 1234")
    assert out == {"plate": "MH12AB1234", "visits": [], "summary": "First visit to this garage."}


def test_washing_comes_last_before_delivery():
    """C10: real garages wash after the repair."""
    assert jobs.STAGES == ["intake", "service", "waiting_approval", "washing", "ready", "done"]
    assert list(jobs.STAGE_LABELS) == jobs.STAGES


def test_dashboard_lists_stages_in_garage_order(fake_db):
    from app import seed
    from app.services import owner as owner_service
    from tests.helpers import owner

    seed.seed(fake_db)
    assert list(owner_service.dashboard(owner(), G)["jobs_by_stage"]) == ["intake", "service", "waiting_approval", "washing", "ready"]



def test_every_job_has_the_service_charge(fake_db):
    """A job with no parts still bills the garage's service charge: ₹350 by default, the owner's amount once set."""
    from app import seed
    from app.services import settings

    seed.seed(fake_db)
    first = jobs.create_job(mechanic(), G, "s1", "MH12AB9999", "Activa", "Rahul")["job_id"]
    assert jobs.get_job(mechanic(), G, first)["bill"] == 350
    core.garage(G).collection("config").document("settings").update(settings.validate({"service_fee": "400"}))
    second = jobs.create_job(mechanic(), G, "s2", "MH12AB8888", "Activa", "Rahul")["job_id"]
    assert jobs.money(jobs.get_job(mechanic(), G, second))["service"] == 400
    assert jobs.get_job(mechanic(), G, first)["bill"] == 350  # jobs already open keep their charge
