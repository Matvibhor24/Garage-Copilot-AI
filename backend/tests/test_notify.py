from app import notify
from app.services import core


def test_notify_writes_simulated_message(fake_db):
    notify.notify("g1", "c-9800", "Hi Ramesh", kind="status_link", job_id="J-1")
    notify.notify("g1", "owner", "Low stock")
    msgs = [d.to_dict() for d in core.garage("g1").collection("messages").stream()]
    by_to = {m["to"]: m for m in msgs}
    assert by_to["c-9800"]["channel"] == "whatsapp" and by_to["c-9800"]["job_id"] == "J-1"
    assert by_to["owner"]["channel"] == "owner_app"
