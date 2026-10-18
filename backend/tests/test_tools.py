from types import SimpleNamespace

import pytest

from app import seed, tools
from app.services import inventory

G = "shree-auto"


def ctx(call_id, state):
    return SimpleNamespace(state=state, function_call_id=call_id)


@pytest.fixture
def state(fake_db):
    seed.seed(fake_db)
    return {"garage_id": G, "uid": "m-raju", "name": "Raju", "role": "mechanic"}


def test_tools_follow_current_job_and_dedupe(state):
    out = tools.create_job("MH12 AB 1234", "Splendor Plus", "Ramesh", "", "clutch slipping", ctx("c1", state))
    assert out["job_id"] == "J-1042" and state["current_job"] == "J-1042"
    assert tools.update_stage("washing", "", ctx("c2", state))["stage"] == "washing"
    assert tools.log_part_used("clutch plate", 1, "1234", ctx("c3", state))["qty_left"] == 1
    tools.log_part_used("clutch plate", 1, "1234", ctx("c3", state))  # same call id: no-op
    assert inventory.part_ref(G, "clutch-splendor").get().to_dict()["qty"] == 1


def test_errors_are_spoken_not_raised(state):
    assert "error" in tools.update_stage("washing", "", ctx("c1", state))
    assert "error" in tools.log_part_used("unobtainium", 1, "MH99", ctx("c2", state))


def test_garage_comes_from_session_not_model(state):
    other = dict(state, garage_id="ganesh-motors")
    out = tools.check_stock("clutch plate", "Splendor", ctx("c1", other))
    assert out["matches"] == []  # ganesh-motors has no Splendor parts


# ---------------------------------------------------------------- owner agent tools


@pytest.fixture
def owner_state(state):
    return {"garage_id": G, "uid": "o-asha", "name": "Asha", "role": "owner"}


def test_owner_tools_answer_from_real_data(state, owner_state):
    tools.create_job("MH12 AB 1234", "Splendor Plus", "Ramesh", "", "clutch slipping", ctx("c1", state))
    tools.update_stage("washing", "", ctx("c2", state))
    tools.log_part_used("clutch plate", 1, "", ctx("c3", state))  # 2 -> 1, low

    summary = tools.today_summary(ctx("o1", owner_state))
    assert summary["open_jobs"] >= 1 and summary["open_by_stage"]["washing"] >= 1
    assert "revenue_today" in summary and summary["pending_approvals"] == 0

    washing = tools.list_open_jobs("washing", "", ctx("o2", owner_state))
    assert [j["job_id"] for j in washing["jobs"]] == ["J-1042"]
    assert tools.list_open_jobs("", "nobody", ctx("o3", owner_state))["count"] == 0

    job = tools.job_details("1042", ctx("o4", owner_state))
    assert job["customer"] == "Ramesh" and job["parts"][0]["name"] == "Clutch plate set"
    assert "intake" in job["minutes_per_stage"] and job["total_minutes"] == sum(job["minutes_per_stage"].values())

    assert any(p["part_id"] == "clutch-splendor" for p in tools.low_stock(ctx("o5", owner_state))["low_stock"])
    assert tools.pending_approvals(ctx("o6", owner_state))["count"] == 0
    actions = [a["action"] for a in tools.recent_activity(5, ctx("o7", owner_state))["activity"]]
    assert "log_part_used" in actions


def test_owner_answers_reorder_ask_by_voice(state, owner_state):
    inventory.ask_reorder(core_actor(state), G, "ask-1", "clutch-splendor")
    out = tools.answer_reorder("clutch-splendor", "yes", ctx("o1", owner_state))
    assert out["status"] == "ordered" and out["supplier"]
    assert inventory.ask_ref(G, "clutch-splendor").get().to_dict()["status"] == "ordered"
    assert "error" in tools.answer_reorder("clutch-splendor", "maybe", ctx("o2", owner_state))


def test_roles_cannot_use_each_others_tools(state, owner_state):
    assert "error" in tools.today_summary(ctx("m1", state))  # mechanic -> owner tool
    assert "error" in tools.answer_reorder("clutch-splendor", "yes", ctx("m2", state))
    assert "error" in tools.create_job("MH12 XY 1", "Activa", "Ravi", "", "", ctx("o1", owner_state))  # owner -> job tool
    assert "error" in tools.log_part_used("clutch plate", 1, "", ctx("o2", owner_state))
    assert inventory.part_ref(G, "clutch-splendor").get().to_dict()["qty"] == 2


def core_actor(state):
    from app.services import core

    return core.actor(state["garage_id"], state["uid"], state["role"], state["name"])


def test_mechanic_can_list_open_jobs(state):
    """Live, Oct 18: "How many jobs are open right now?" had no mechanic tool, so the agent tried vehicle history."""
    tools.create_job("MH12 AB 1234", "Splendor Plus", "Ramesh", "", "clutch slipping", ctx("c1", state))
    out = tools.list_open_jobs("", "", ctx("m1", state))
    assert out["count"] == 1 and out["jobs"][0]["job_id"] == "J-1042"
