"""Executor (A03 skeleton): carries out a ChosenPlan.

  move_officers -> pick officers in from_zone, instruct them, publish OfficerStatus.
                   Officers without a phone are simulated: on_the_way, then arrived
                   after the travel time.
  gate          -> DeviceCommand on br/device/gate-<n>: closed -> stop, open -> up (go)
  announce      -> Announcement on br/announce (English now; Tamil/Hindi in A06)
  hold_inflow   -> instruction to the officers at that entry

Telegram (A05) plugs in through `notify`; until then instructions are printed.
"""
import json, os, re, threading
from pathlib import Path
from typing import Callable, Optional

from common.contracts import Announcement, ChosenPlan, DeviceCommand, OfficerStatus, Venue
from common.timeutil import now_iso

OFFICERS_FILE = Path(__file__).parent / "officers.json"
TRAVEL_S = float(os.environ.get("OFFICER_TRAVEL_S", 240))   # simulated walk time (spec: 4 min)


class Officers:
    """Who the officers are, where they are and whether they're busy."""

    def __init__(self, path: Path = OFFICERS_FILE):
        self.list = json.loads(path.read_text(encoding="utf-8"))
        for o in self.list:
            o.setdefault("status", "idle")
        self.lock = threading.Lock()

    def per_zone(self) -> dict[str, int]:
        with self.lock:
            out: dict[str, int] = {}
            for o in self.list:
                out[o["zone"]] = out.get(o["zone"], 0) + 1
            return out

    def pick(self, zone: str, n: int) -> list[dict]:
        """Up to n officers in zone, idle ones first."""
        with self.lock:
            here = [o for o in self.list if o["zone"] == zone]
            here.sort(key=lambda o: o["status"] != "idle")
            return here[:n]

    def in_zone(self, zone: str) -> list[dict]:
        with self.lock:
            return [o for o in self.list if o["zone"] == zone]


def gate_node(link_id: str) -> str:
    """Link "G3" -> device "gate-3"."""
    m = re.search(r"\d+", link_id)
    return f"gate-{m.group()}" if m else f"gate-{link_id.lower()}"


class Executor:
    def __init__(self, venue: Venue, officers: Officers, publish: Callable[[str, object], None],
                 notify: Optional[Callable[[dict, str], None]] = None, travel_s: float = TRAVEL_S):
        self.venue = venue
        self.officers = officers
        self.publish = publish
        self.notify = notify or (lambda o, text: print(f"  -> {o['name']}: {text}"))
        self.travel_s = travel_s
        self.gates = {l.id: l.state for l in venue.links}
        self.names = {z.id: z.name for z in venue.zones}

    def _status(self, o: dict, status: str, task: Optional[str] = None):
        o["status"] = status
        self.publish("br/officer", OfficerStatus(
            t=now_iso(), officer_id=o["officer_id"], name=o["name"], zone=o["zone"], status=status,
            task=task, simulated=not o.get("telegram_chat_id")))

    def _arrive(self, o: dict, zone: str, task: str):
        with self.officers.lock:
            o["zone"] = zone
        self._status(o, "arrived", task)

    def execute(self, cp: ChosenPlan):
        why = cp.plan.why
        for a in cp.plan.actions:
            if a.type == "move_officers":
                task = f"Move to {self.names.get(a.to_zone, a.to_zone)} (zone {a.to_zone}) now."
                for o in self.officers.pick(a.from_zone, a.count or 0):
                    self.notify(o, f"{task} Reason: {why}")
                    self._status(o, "assigned", task)
                    if not o.get("telegram_chat_id"):           # simulated officer walks on its own
                        threading.Timer(2, self._status, (o, "on_the_way", task)).start()
                        threading.Timer(self.travel_s, self._arrive, (o, a.to_zone, task)).start()
            elif a.type == "gate":
                self.gates[a.link] = a.state
                node = gate_node(a.link)
                self.publish(f"br/device/{node}", DeviceCommand(
                    to=node, cmd="arrow", value="stop" if a.state == "closed" else "up"))
            elif a.type == "announce":
                self.publish("br/announce", Announcement(
                    t=now_iso(), zone=a.zone, plan_id=cp.plan.plan_id, texts={"en": a.text}))
            elif a.type == "hold_inflow":
                text = f"Pause entry at {a.entry} for {a.minutes} minutes. Reason: {why}"
                for o in self.officers.in_zone(a.zone):
                    self.notify(o, text)
