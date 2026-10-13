"""Voice session state (kept in Firestore so the gateway stays stateless) and headset messages."""

from app import db
from app.services import core

NEW = "sent (simulated)"


def session_ref(garage_id: str, uid: str):
    return core.garage(garage_id).collection("voice_sessions").document(uid)


def load_session(who: dict) -> dict:
    """Initial ADK session state for this mechanic: who they are, plus the job they were on."""
    g = who["garage_id"]
    saved = session_ref(g, who["uid"]).get().to_dict() or {}
    garage_doc = core.garage(g).get().to_dict() or {}
    return {
        "garage_id": g,
        "garage_name": garage_doc.get("name", ""),
        "uid": who["uid"],
        "name": who["name"],
        "role": who["role"],
        "current_job": saved.get("current_job", ""),
    }


def claim_session(who: dict, conn: str) -> None:
    """This connection is now the mechanic's live one; an older connection sees it and closes itself."""
    session_ref(who["garage_id"], who["uid"]).set({"conn": conn, "conn_at": core.now()}, merge=True)


def is_current(who: dict, conn: str) -> bool:
    saved = session_ref(who["garage_id"], who["uid"]).get().to_dict() or {}
    return saved.get("conn", conn) == conn


def save_session(who: dict, current_job: str) -> None:
    session_ref(who["garage_id"], who["uid"]).set({"current_job": current_job, "at": core.now()}, merge=True)


def take_headset_messages(who: dict) -> list[dict]:
    """Messages for this mechanic not yet spoken. Marks them delivered."""
    msgs = core.garage(who["garage_id"]).collection("messages")
    query = msgs.where(filter=db.FieldFilter("to", "==", who["uid"])).where(filter=db.FieldFilter("status", "==", NEW))
    out = []
    for snap in query.stream():
        msgs.document(snap.id).update({"status": "delivered", "delivered_at": core.now()})
        out.append(snap.to_dict() | {"id": snap.id})
    return sorted(out, key=lambda m: m["at"])
