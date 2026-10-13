"""The single exit for side effects: customer WhatsApp, owner and mechanic pings.

Simulated for the demo: each message is written to garages/{g}/messages and logged.
The PWA shows them live; the voice gateway speaks mechanic messages into the headset.
Swapping in Meta's WhatsApp Cloud API or Cloud Tasks later only changes this function.
"""

import logging
import uuid

from app import db

log = logging.getLogger(__name__)


def channel_for(to: str) -> str:
    if to.startswith(("c-", "supplier:")):
        return "whatsapp"  # customer or supplier
    if to == "owner":
        return "owner_app"
    return "headset"  # a mechanic uid


def notify(garage_id: str, to: str, text: str, kind: str = "info", **extra) -> str:
    from app.services import core  # local import: core imports this module

    message_id = uuid.uuid4().hex[:12]
    doc = {"to": to, "channel": channel_for(to), "kind": kind, "text": text, "at": core.now(),
           "status": "sent (simulated)", **extra}
    db.client().collection("garages").document(garage_id).collection("messages").document(message_id).set(doc)
    log.info("notify[%s] %s -> %s (%s): %s", garage_id, doc["channel"], to, kind, text)
    return message_id
