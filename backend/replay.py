"""What the backend remembers so a newly opened (or reloaded) dashboard isn't blank.

MQTT messages aren't stored anywhere: a browser that connects after a message went
out would never see it. Replay keeps the current state per topic and hands it to
each new WebSocket client before live messages.

  latest one:            br/turnout, br/plan, br/forecast, br/announce
  latest per key:        br/status (per source), br/officer (per officer),
                         br/zone_state (per zone)
  last N:                br/report (50), br/cost (200)
  still pending only:    br/approval. Dropped when answered (br/approve), expired,
                         or replaced by a newer br/plan, so an old Approve button
                         can never come back.
"""
import threading, time
from collections import OrderedDict, deque
from typing import Any

LATEST = {"br/turnout", "br/plan", "br/forecast", "br/announce"}
KEYED = {"br/status": "source", "br/officer": "officer_id", "br/zone_state": "zone"}
HISTORY = {"br/report": 50, "br/cost": 200}


class Replay:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.RLock()        # re-entrant: app.py holds it around record + fan-out
        self.latest: dict[str, dict] = {}
        self.keyed: dict[str, OrderedDict] = {t: OrderedDict() for t in KEYED}
        self.history: dict[str, deque] = {t: deque(maxlen=n) for t, n in HISTORY.items()}
        self.approvals: OrderedDict[str, tuple[float, dict]] = OrderedDict()   # id -> (expires_at, item)

    def record(self, topic: str, data: Any):
        """Called for every MQTT message (from paho's thread)."""
        if not isinstance(data, dict):
            return
        item = {"topic": topic, "data": data}
        with self.lock:
            if topic in LATEST:
                self.latest[topic] = item
                if topic == "br/plan":                    # Act cancels older approval requests
                    self.approvals.clear()
            elif topic in KEYED:
                d = self.keyed[topic]
                key = data.get(KEYED[topic])
                d.pop(key, None)
                d[key] = item
            elif topic in HISTORY:
                self.history[topic].append(item)
            elif topic == "br/approval" and data.get("approval_id"):
                ttl = float(data.get("expires_in_s") or 120)
                self.approvals[data["approval_id"]] = (self.clock() + ttl, item)
            elif topic == "br/approve":
                self.approvals.pop(data.get("approval_id"), None)

    def snapshot(self) -> list[dict]:
        """Current state, oldest-ish first, each marked "replay": true. Take it under
        `lock` together with registering the new client, so nothing is missed or doubled."""
        now = self.clock()
        for aid in [a for a, (exp, _) in self.approvals.items() if exp <= now]:
            del self.approvals[aid]
        items = [self.latest[t] for t in ("br/forecast", "br/turnout", "br/plan") if t in self.latest]
        for t in ("br/zone_state", "br/officer", "br/status"):
            items += list(self.keyed[t].values())
        for t in HISTORY:
            items += list(self.history[t])
        if "br/announce" in self.latest:
            items.append(self.latest["br/announce"])
        items += [item for _, item in self.approvals.values()]
        return [{**i, "replay": True} for i in items]
