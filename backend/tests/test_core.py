import pytest

from app.services import core


def owner(g="g1"):
    return core.actor(g, "u1", "owner", "Asha")


def test_tenant_check_blocks_other_garage(fake_db):
    with pytest.raises(core.Forbidden):
        core.run(owner("g2"), "g1", "r1", "x", lambda: ({}, []))


def test_repeat_request_id_is_noop_and_audited_once(fake_db):
    calls = []

    def work():
        calls.append(1)
        return {"n": len(calls)}, []

    assert core.run(owner(), "g1", "r1", "thing", work) == {"n": 1}
    assert core.run(owner(), "g1", "r1", "thing", work) == {"n": 1}
    assert len(calls) == 1
    audit = list(core.garage("g1").collection("audit_log").stream())
    assert len(audit) == 1
    assert audit[0].to_dict()["by_name"] == "Asha"


def test_failed_work_can_be_retried(fake_db):
    def boom():
        raise core.Invalid("no")

    with pytest.raises(core.Invalid):
        core.run(owner(), "g1", "r1", "x", boom)
    assert core.run(owner(), "g1", "r1", "x", lambda: ({"ok": True}, [])) == {"ok": True}


def test_request_id_required(fake_db):
    with pytest.raises(core.Invalid):
        core.run(owner(), "g1", "", "x", lambda: ({}, []))
