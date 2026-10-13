"""Small helpers shared by tests."""

from datetime import datetime, timedelta, timezone

from app.services import core


class Clock:
    """Controllable clock for core.now(). Starts at 10:00 IST on the demo day."""

    def __init__(self, monkeypatch, start="2026-10-14T10:00:00+05:30"):
        self.t = datetime.fromisoformat(start)
        monkeypatch.setattr(core, "now", lambda: self.t.astimezone(timezone.utc).isoformat(timespec="seconds"))

    def at(self, hhmm: str):
        h, m = map(int, hhmm.split(":"))
        self.t = self.t.replace(hour=h, minute=m)

    def advance(self, minutes: int):
        self.t += timedelta(minutes=minutes)


def mechanic(g="shree-auto"):
    return core.actor(g, "m-raju", "mechanic", "Raju")


def owner(g="shree-auto"):
    return core.actor(g, "o-asha", "owner", "Asha")
