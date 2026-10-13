import time

import pytest
from fastapi.testclient import TestClient

from app import links, seed
from app.main import app
from app.services import core, jobs
from tests.helpers import mechanic


def test_token_roundtrip_and_tamper():
    token = links.make_token("shree-auto", "J-1042")
    assert links.read_token(token) == ("shree-auto", "J-1042")
    payload, sig = token.split(".")
    forged = links.make_token("ganesh-motors", "J-1042").split(".")[0] + "." + sig
    with pytest.raises(links.BadLink):
        links.read_token(forged)
    with pytest.raises(links.BadLink):
        links.read_token("garbage")


def test_token_expires(monkeypatch):
    token = links.make_token("g", "j", ttl_hours=1)
    monkeypatch.setattr(time, "time", lambda: 10**11)
    with pytest.raises(links.BadLink, match="expired"):
        links.read_token(token)


def test_create_job_sends_link_and_status_page_works(fake_db):
    seed.seed(fake_db)
    jobs.create_job(mechanic(), "shree-auto", "r1", "MH12 AB 1234", "Splendor Plus", "Ramesh", "+919800000101")
    [msg] = [d.to_dict() for d in core.garage("shree-auto").collection("messages").stream()]
    assert msg["kind"] == "status_link" and msg["channel"] == "whatsapp"
    url = msg["text"].split("Track it: ")[1]
    assert url.startswith("https://gc.app/j/")
    client = TestClient(app)
    view = client.get("/api/j/" + url.rsplit("/", 1)[1]).json()
    assert view["job_id"] == "J-1042" and view["stage_label"] == "Checked in" and view["garage"] == "Shree Auto"
    assert client.get("/api/j/bad.token").status_code == 403


def test_resend_status_link(fake_db):
    seed.seed(fake_db)
    jobs.create_job(mechanic(), "shree-auto", "r1", "MH12 AB 1234", "Splendor Plus", "Ramesh")
    assert jobs.send_status_link(mechanic(), "shree-auto", "r2", "J-1042")["sent_to"] == "Ramesh"
    links_sent = [d for d in core.garage("shree-auto").collection("messages").stream() if d.to_dict()["kind"] == "status_link"]
    assert len(links_sent) == 2
