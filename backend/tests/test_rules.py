"""firestore.rules against the Firestore emulator. Skipped unless FIRESTORE_EMULATOR_HOST is set.

Run from the repo root:
    npx firebase-tools emulators:exec --only firestore --project demo-garage \
        "cd backend && uv run pytest tests/test_rules.py"
"""

import base64
import json
import os
import time

import httpx
import pytest

HOST = os.environ.get("FIRESTORE_EMULATOR_HOST")
PROJECT = os.environ.get("GCLOUD_PROJECT", "demo-garage")
pytestmark = pytest.mark.skipif(not HOST, reason="needs the Firestore emulator")
BASE = f"http://{HOST}/v1/projects/{PROJECT}/databases/(default)/documents"


def jwt(**claims):
    """Unsigned ID token; the emulator accepts these."""
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()

    now = int(time.time())
    body = {"iss": f"https://securetoken.google.com/{PROJECT}", "aud": PROJECT, "iat": now, "exp": now + 3600,
            "sub": claims.get("uid", "u"), "user_id": claims.get("uid", "u"),
            "firebase": {"sign_in_provider": "custom"}, **claims}
    return f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64(body)}."


def fields(data):
    return {"fields": {k: {"stringValue": v} for k, v in data.items()}}


@pytest.fixture(scope="module", autouse=True)
def data():
    admin = {"Authorization": "Bearer owner"}  # emulator admin bypasses rules
    httpx.delete(f"http://{HOST}/emulator/v1/projects/{PROJECT}/databases/(default)/documents")
    docs = {
        "garages/g1/jobs/J-1": {"plate": "MH12AB1234"},
        "garages/g1/jobs/J-2": {"plate": "MH12ZZ0001"},
        "garages/g1/jobs/J-1/stages/s1": {"name": "intake"},
        "garages/g1/quotes/Q-1": {"job_id": "J-1"},
        "garages/g1/quotes/Q-2": {"job_id": "J-2"},
        "garages/g1/inventory/p1": {"name": "Clutch plate set"},
        "garages/g1/mechanics/m-raju": {"pin_hash": "x"},
        "garages/g1/audit_log/a1": {"action": "create_job"},
        "garages/g1/requests/r1": {"status": "done"},
        "garages/g2/jobs/J-9": {"plate": "MH15XX9999"},
        "phone_index/+919800000001": {"garage_id": "g1"},
    }
    for path, d in docs.items():
        httpx.patch(f"{BASE}/{path}", json=fields(d), headers=admin).raise_for_status()


def can_read(path, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.get(f"{BASE}/{path}", headers=headers).status_code == 200


OWNER = jwt(uid="o1", garage="g1", role="owner")
MECH = jwt(uid="m1", garage="g1", role="mechanic")
OTHER = jwt(uid="o2", garage="g2", role="owner")
CUSTOMER = jwt(uid="c1", garage="g1", job="J-1", role="customer")


def test_tenant_isolation():
    assert can_read("garages/g1/jobs/J-1", OWNER)
    assert can_read("garages/g1/inventory/p1", MECH)
    assert not can_read("garages/g1/jobs/J-1", OTHER)
    assert can_read("garages/g2/jobs/J-9", OTHER)
    assert not can_read("garages/g1/jobs/J-1")
    assert not can_read("garages/g1/jobs/J-1", jwt(uid="x"))  # signed in, no garage claim


def test_owner_only_and_backend_only():
    assert can_read("garages/g1/audit_log/a1", OWNER)
    assert not can_read("garages/g1/audit_log/a1", MECH)
    assert not can_read("garages/g1/mechanics/m-raju", MECH)
    assert not can_read("garages/g1/requests/r1", OWNER)
    assert not can_read("phone_index/+919800000001", OWNER)


def test_customer_sees_only_their_job():
    assert can_read("garages/g1/jobs/J-1", CUSTOMER)
    assert can_read("garages/g1/jobs/J-1/stages/s1", CUSTOMER)
    assert can_read("garages/g1/quotes/Q-1", CUSTOMER)
    assert not can_read("garages/g1/jobs/J-2", CUSTOMER)
    assert not can_read("garages/g1/quotes/Q-2", CUSTOMER)
    assert not can_read("garages/g1/inventory/p1", CUSTOMER)


def test_clients_cannot_write():
    r = httpx.patch(f"{BASE}/garages/g1/inventory/p1", json=fields({"name": "x"}),
                    headers={"Authorization": f"Bearer {OWNER}"})
    assert r.status_code == 403
