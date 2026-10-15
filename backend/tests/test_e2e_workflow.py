"""The demo job from diagrams/job-workflow.png, end to end, through the agent's tools,
the customer link REST API and the owner API. Gemini is not involved: we call the tools
the Live agent would call for each spoken line."""

from datetime import datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import auth, gemini, seed, tools
from app.main import app
from app.services import core, inventory, jobs, quotes
from tests.helpers import Clock

G = "shree-auto"
IST = datetime.fromisoformat("2026-10-14T00:00:00+05:30").tzinfo


def test_demo_job_end_to_end(fake_db, monkeypatch):
    seed.seed(fake_db)
    clock = Clock(monkeypatch)
    people = {"owner": {"uid": "o-asha", "garage": G, "role": "owner", "name": "Asha"},
              "mech": {"uid": "m-raju", "garage": G, "role": "mechanic", "name": "Raju"}}
    monkeypatch.setattr(auth, "verify_id_token", lambda t: people[t])
    api = TestClient(app)
    owner_h = {"Authorization": "Bearer owner"}
    state = {"garage_id": G, "garage_name": "Shree Auto", "uid": "m-raju", "name": "Raju", "role": "mechanic"}
    n = iter(range(1, 100))

    def say(tool, *args):
        """One tool call from the Live agent, with a fresh Gemini function_call_id."""
        out = tool(*args, SimpleNamespace(state=state, function_call_id=f"fc-{next(n)}"))
        assert "error" not in out, out
        return out

    def messages(kind):
        return [d.to_dict() for d in core.garage(G).collection("messages").stream() if d.to_dict()["kind"] == kind]

    # 1. Intake: "New bike, Splendor Plus, MH12 AB 1234, owner Ramesh, clutch slipping, service."
    clock.at("10:02")
    out = say(tools.create_job, "MH12 AB 1234", "Splendor Plus", "Ramesh", "+919800000101", "clutch slipping, service")
    assert out["job_id"] == "J-1042"
    history = say(tools.get_vehicle_history, "MH12 AB 1234")
    assert history["visits"][0]["months_ago"] == 8 and history["summary"].startswith("Last visit 8 months ago")
    job = jobs.job_ref(G, "J-1042").get().to_dict()
    assert (job["plate"], job["owner"], job["stage"], job["quote_limit"]) == ("MH12AB1234", "Ramesh", "intake", 500)
    [link_msg] = messages("status_link")
    assert link_msg["channel"] == "whatsapp" and link_msg["text"].startswith("[Marathi] Hi Ramesh, your Splendor Plus")
    token = link_msg["text"].rsplit("/j/", 1)[1]

    # 2. Stage update: "Started service." (washing comes later, after the repair: C10)
    clock.at("10:20")
    assert say(tools.update_stage, "service", "")["previous_minutes"] == 18
    page = api.get(f"/api/j/{token}").json()
    assert [t["label"] for t in page["timeline"]] == ["Checked in", "In service"]
    assert page["timeline"][0]["minutes"] == 18

    # 3. Stock check: "Do we have a clutch plate for Splendor? Price?" -> "Two in stock, ₹650, labour ₹300."
    clock.at("10:52")
    best = say(tools.check_stock, "clutch plate", "Splendor")["matches"][0]
    assert (best["part_id"], best["qty"], best["price"], best["labour"]) == ("clutch-splendor", 2, 650, 300)
    assert len(messages("status_link")) == 1  # stock checks stay internal

    # 4. Quote: "Show Ramesh the worn plate." ₹950 > ₹500 limit -> sent in Marathi, pending.
    clock.at("10:58")
    photo = api.post("/api/jobs/J-1042/photos?request_id=ph1", content=b"jpeg-bytes",
                     headers={"Authorization": "Bearer mech", "Content-Type": "image/jpeg"}).json()
    text_model = gemini.generate  # conftest stub: translation shows up as "[Marathi] ..."
    monkeypatch.setattr(gemini, "generate", lambda model, prompt, image=None, mime_type="":
                        "friction surface glazed" if image is not None else text_model(model, prompt))
    assert say(tools.describe_photo, "")["caption"] == "friction surface glazed"  # quote agent
    q = say(tools.draft_quote, ["clutch plate"], "clutch plate worn", "")       # quote agent
    assert (q["quote_id"], q["total"], q["needs_approval"]) == ("Q-77", 950, True)
    assert say(tools.send_quote, "Q-77")["status"] == "pending"                # comms agent
    quote = quotes.quote_ref(G, "Q-77").get().to_dict()
    assert (quote["total"], quote["lang"], quote["status"]) == (950, "mr", "pending")
    assert quote["photo"] == photo["path"] and quote["photo_caption"] == "friction surface glazed"
    assert api.get(f"/api/j/{token}").json()["quotes"][0]["photo_url"].startswith("memory://photos/shree-auto/J-1042/")
    [quote_msg] = messages("quote")
    assert quote_msg["text"].startswith("[Marathi] Hi Ramesh") and "Total: ₹950" in quote_msg["text"]
    assert "Photo: friction surface glazed" in quote_msg["text"]
    assert len(api.get("/api/owner/dashboard", headers=owner_h).json()["pending_approvals"]) == 1

    # 5. Approval: Ramesh taps Approve (one tap, no login); the mechanic hears it.
    clock.at("11:07")
    assert api.post(f"/api/j/{token}/quotes/Q-77/approve").json()["status"] == "approved"
    quote = quotes.quote_ref(G, "Q-77").get().to_dict()
    assert quote["status"] == "approved" and quote["by"] == "customer"
    [heard] = messages("quote_approved")
    assert heard["channel"] == "headset" and heard["text"] == "Ramesh approved. Go ahead."

    # 6. Parts + close: "Used one clutch plate set." / "Job done."
    clock.at("11:40")
    used = say(tools.log_part_used, "clutch plate", 1, "")
    assert used["qty_left"] == 1 and used["low_stock"] is True
    assert [p["part_id"] for p in say(tools.low_stock_report)["low_stock"]] == ["clutch-splendor"]  # inventory agent
    ask = say(tools.ask_owner_to_reorder, "clutch-splendor")
    assert ask["text"] == "Clutch plate set down to 1. Reorder 5 from Sai Spares?"
    assert messages("reorder_ask")[0]["channel"] == "owner_app"
    # 7. "Moving it to washing." after the repair, then "Job done."
    clock.at("11:45")
    assert say(tools.update_stage, "washing", "")["previous_minutes"] == 85
    assert [t["label"] for t in api.get(f"/api/j/{token}").json()["timeline"]] == ["Checked in", "In service", "Washing"]
    clock.at("11:58")
    closed = say(tools.close_job, "")
    assert closed["bill"] == 950
    part = inventory.part_ref(G, "clutch-splendor").get().to_dict()
    assert (part["qty"], part["low_stock"]) == (1, True)
    job = jobs.job_ref(G, "J-1042").get().to_dict()
    assert (job["stage"], job["bill"]) == ("done", 950)
    page = api.get(f"/api/j/{token}").json()
    assert page["stage_label"] == "Ready for pickup" and page["bill"] == 950 and page["labour"] == 300
    assert page["parts"] == [{"name": "Clutch plate set", "qty": 1, "price": 650, "total": 650}]
    assert "Final bill: ₹950" in messages("final_bill")[0]["text"]

    # Owner: dashboard tiles and the audit trail (who did what, when).
    dash = api.get("/api/owner/dashboard", headers=owner_h).json()
    assert dash["pending_approvals"] == [] and dash["revenue_today"] == 950
    assert dash["low_stock"] == [{"part_id": "clutch-splendor", "name": "Clutch plate set", "qty": 1}]
    trail = [(datetime.fromisoformat(a["at"]).astimezone(IST).strftime("%H:%M"), a["action"], a["by_name"])
             for a in reversed(api.get("/api/owner/audit", headers=owner_h).json())]
    assert sorted(trail) == [
        ("10:02", "create_job", "Raju"),
        ("10:02", "get_vehicle_history", "Raju"),
        ("10:20", "update_stage", "Raju"),
        ("10:52", "check_stock", "Raju"),
        ("10:58", "add_photo", "Raju"),
        ("10:58", "describe_photo", "Raju"),
        ("10:58", "draft_quote", "Raju"),
        ("10:58", "send_quote", "Raju"),
        ("11:07", "quote_approved", "Ramesh"),
        ("11:40", "ask_reorder", "Raju"),
        ("11:40", "log_part_used", "Raju"),
        ("11:45", "update_stage", "Raju"),
        ("11:58", "close_job", "Raju"),
    ]
