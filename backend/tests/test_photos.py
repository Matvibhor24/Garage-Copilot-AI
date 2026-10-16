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


def _signing_fails(monkeypatch):
    def boom(path, minutes=15):
        raise PermissionError("iam.serviceAccounts.signBlob denied")
    monkeypatch.setattr(storage, "signed_url", boom)


def test_signing_failure_still_uploads_and_serves_through_the_backend(client, monkeypatch):
    """C21: no IAM signing permission must not look like a failed upload; the photo is served by the backend."""
    _signing_fails(monkeypatch)
    r = client.post("/api/jobs/J-1042/photos?request_id=p9", content=b"\xff\xd8jpeg",
                    headers={"Authorization": "Bearer raju", "Content-Type": "image/jpeg"})
    assert r.status_code == 200
    url = r.json()["url"]
    assert url.startswith("/api/photos/ph.")
    got = client.get(url)
    assert got.status_code == 200 and got.content == b"\xff\xd8jpeg" and got.headers["content-type"] == "image/jpeg"


def test_photo_token_rules(client):
    from app import links

    storage.upload("photos/shree-auto/J-1042/a.jpg", b"img", "image/jpeg")
    good = links.make_photo_token(G, "photos/shree-auto/J-1042/a.jpg")
    assert client.get(f"/api/photos/{good}").status_code == 200
    assert client.get(f"/api/photos/{good[:-3]}xyz").status_code == 403          # tampered
    assert client.get(f"/api/photos/{links.make_photo_token(G, 'photos/shree-auto/J-1042/a.jpg', -1)}").status_code == 403  # expired
    assert client.get(f"/api/photos/{links.make_photo_token(G, 'photos/ganesh-motors/J-1/b.jpg')}").status_code == 403  # other garage


def test_customer_page_survives_a_signing_failure(client, monkeypatch):
    """C21: a quote with a photo must not take the customer page down when signing fails."""
    from app import links

    client.post("/api/jobs/J-1042/photos?request_id=p10", content=b"\xff\xd8jpeg",
                headers={"Authorization": "Bearer raju", "Content-Type": "image/jpeg"})
    core.garage(G).collection("quotes").document("Q-1").set(
        {"job_id": "J-1042", "status": "pending", "photo": jobs.get_job(mechanic(), G, "J-1042")["last_photo"],
         "lines": [], "labour": 0, "total": 0})
    _signing_fails(monkeypatch)
    view = client.get(f"/api/j/{links.make_token(G, 'J-1042')}")
    assert view.status_code == 200
    assert view.json()["quotes"][0]["photo_url"].startswith("/api/photos/ph.")


def test_storage_check_is_owner_only_and_names_the_failing_step(client, monkeypatch):
    claims = {"asha": {"uid": "o-asha", "garage": G, "role": "owner", "name": "Asha"},
              "raju": {"uid": "m-raju", "garage": G, "role": "mechanic", "name": "Raju"}}
    monkeypatch.setattr(auth, "verify_id_token", lambda t: claims[t])
    assert client.get("/api/owner/diagnostics/storage", headers={"Authorization": "Bearer raju"}).status_code == 403
    ok = client.get("/api/owner/diagnostics/storage", headers={"Authorization": "Bearer asha"}).json()
    assert ok["ok"] and [s["step"] for s in ok["steps"]] == ["bucket", "write", "read", "sign", "delete"]
    _signing_fails(monkeypatch)
    bad = client.get("/api/owner/diagnostics/storage", headers={"Authorization": "Bearer asha"}).json()
    sign = next(s for s in bad["steps"] if s["step"] == "sign")
    assert not bad["ok"] and not sign["ok"] and "Token Creator" in sign["hint"] and "signBlob" in sign["detail"]
    assert bad["steps"][-1]["step"] == "delete" and bad["steps"][-1]["ok"]  # the test file is still cleaned up


def test_a_storage_failure_gives_a_clear_message_not_a_500(client, monkeypatch):
    def missing(path, data, content_type):
        raise RuntimeError("404 The specified bucket does not exist.")
    monkeypatch.setattr(storage, "upload", missing)
    r = client.post("/api/jobs/J-1042/photos?request_id=p11", content=b"\xff\xd8jpeg",
                    headers={"Authorization": "Bearer raju", "Content-Type": "image/jpeg"})
    assert r.status_code == 409 and "Check photo storage" in r.json()["detail"]


def test_storage_check_says_when_the_bucket_name_is_wrong(client, monkeypatch):
    monkeypatch.setattr(auth, "verify_id_token", lambda t: {"uid": "o-asha", "garage": G, "role": "owner", "name": "Asha"})

    def missing(path, data, content_type):
        raise RuntimeError("404 POST …/b/wrong-bucket/o: The specified bucket does not exist.")
    monkeypatch.setattr(storage, "upload", missing)
    out = client.get("/api/owner/diagnostics/storage", headers={"Authorization": "Bearer asha"}).json()
    write = next(s for s in out["steps"] if s["step"] == "write")
    assert not write["ok"] and "No bucket named" in write["hint"]
