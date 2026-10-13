import pytest
from fastapi.testclient import TestClient

from app import auth, seed, storage
from app.main import app
from app.services import core, jobs, photos
from tests.helpers import mechanic

G = "shree-auto"


@pytest.fixture
def client(fake_db, monkeypatch):
    seed.seed(fake_db)
    jobs.create_job(mechanic(), G, "r1", "MH12AB1234", "Splendor Plus", "Ramesh")
    claims = {"raju": {"uid": "m-raju", "garage": G, "role": "mechanic", "name": "Raju"},
              "sunil": {"uid": "m-sunil", "garage": "ganesh-motors", "role": "mechanic", "name": "Sunil"}}
    monkeypatch.setattr(auth, "verify_id_token", lambda t: claims[t])
    return TestClient(app)


def test_upload_photo_to_garage_folder(client):
    r = client.post("/api/jobs/J-1042/photos?request_id=p1", content=b"\xff\xd8jpeg",
                    headers={"Authorization": "Bearer raju", "Content-Type": "image/jpeg"})
    body = r.json()
    assert body["path"].startswith("photos/shree-auto/J-1042/") and body["path"].endswith(".jpg")
    assert body["url"].startswith("memory://photos/shree-auto/J-1042/")
    assert storage.download(body["path"]) == (b"\xff\xd8jpeg", "image/jpeg")
    assert jobs.get_job(mechanic(), G, "J-1042")["last_photo"] == body["path"]


def test_bad_type_and_other_garage(client):
    r = client.post("/api/jobs/J-1042/photos", content=b"x", headers={"Authorization": "Bearer raju", "Content-Type": "text/plain"})
    assert r.status_code == 409
    r = client.post("/api/jobs/J-1042/photos", content=b"x", headers={"Authorization": "Bearer sunil", "Content-Type": "image/jpeg"})
    assert r.status_code == 404  # J-1042 does not exist in ganesh-motors
    with pytest.raises(core.Forbidden):
        photos.photo_url("ganesh-motors", "photos/shree-auto/J-1042/x.jpg")


def test_describe_photo_with_stubbed_vision(client, monkeypatch):
    from app import gemini

    seen = {}

    def fake_generate(model, prompt, image=None, mime_type=""):
        seen.update(model=model, image=image, mime=mime_type)
        return "Friction surface glazed."

    monkeypatch.setattr(gemini, "generate", fake_generate)
    with pytest.raises(core.Invalid):
        photos.describe_photo(mechanic(), G, "d0", "J-1042")
    path = photos.add_photo(mechanic(), G, "p1", "J-1042", b"img", "image/jpeg")["path"]
    out = photos.describe_photo(mechanic(), G, "d1", "J-1042")
    assert out == {"job_id": "J-1042", "path": path, "caption": "Friction surface glazed"}
    assert seen["image"] == b"img" and seen["mime"] == "image/jpeg"
    assert jobs.get_job(mechanic(), G, "J-1042")["last_photo_caption"] == "Friction surface glazed"
