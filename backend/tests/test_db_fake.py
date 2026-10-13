import pytest

from app.db import AlreadyExists, ArrayUnion, FieldFilter, Increment


def test_set_get_update_increment(fake_db):
    ref = fake_db.collection("garages/g1/inventory").document("p1")
    ref.set({"qty": 2, "name": "clutch plate"})
    ref.update({"qty": Increment(-1), "tags": ArrayUnion(["x"])})
    assert ref.get().to_dict() == {"qty": 1, "name": "clutch plate", "tags": ["x"]}
    ref.set({"price": 650}, merge=True)
    assert ref.get().to_dict()["price"] == 650


def test_create_twice_fails(fake_db):
    ref = fake_db.document("garages/g1/requests/r1")
    ref.create({"a": 1})
    with pytest.raises(AlreadyExists):
        ref.create({"a": 2})


def test_stream_only_direct_children_and_filters(fake_db):
    jobs = fake_db.collection("garages/g1/jobs")
    jobs.document("j1").set({"stage": "intake", "n": 2})
    jobs.document("j2").set({"stage": "done", "n": 1})
    jobs.document("j1").collection("stages").document("s1").set({"name": "intake"})
    fake_db.collection("garages/g2/jobs").document("j9").set({"stage": "intake"})
    assert [d.id for d in jobs.stream()] == ["j1", "j2"]
    open_jobs = jobs.where(filter=FieldFilter("stage", "!=", "done")).stream()
    assert [d.id for d in open_jobs] == ["j1"]
    assert [d.id for d in jobs.order_by("n").limit(1).stream()] == ["j2"]


def test_update_dotted_path(fake_db):
    ref = fake_db.document("a/b")
    ref.set({"m": {"x": 1}})
    ref.update({"m.y": 2})
    assert ref.get().to_dict() == {"m": {"x": 1, "y": 2}}
