"""Executor: carries out a ChosenPlan.

  move_officers -> pick officers in from_zone, instruct them, publish OfficerStatus.
                   Officers without a phone are simulated: on_the_way, then arrived
                   after the travel time.
  gate          -> DeviceCommand on br/device/gate-<n>: closed -> stop, open -> up (go).
                   Closing a gate first needs an operator's approval (see below).
  announce      -> Announcement on br/announce in English, Tamil and Hindi (A06)
  hold_inflow   -> instruction to the officers at that entry

Human approval (APPROVE_GATES, default "close"):
  A gate action that needs approval is not carried out. Instead an approval request
  goes out on br/approval:
      {"t", "approval_id", "plan_id", "action": {...}, "why", "expires_in_s"}
  The dashboard (or Telegram) answers on br/approve:
      {"t", "approval_id", "approved": true/false, "by": "..."}
  No answer within APPROVAL_TIMEOUT_S (default 120) = not approved: the gate stays
  as it is. A newer plan cancels older pending approvals.
  APPROVE_GATES = "none" | "close" (only closing needs approval) | "all".

Telegram (A05) plugs in through `notify`; until then instructions are printed.
Announcements are sent last so gates and officers aren't delayed by translation.
"""
import json, os, re, threading, uuid
from pathlib import Path
from typing import Callable, Optional

from common.contracts import Action, Announcement, ChosenPlan, DeviceCommand, OfficerStatus, Venue
from common.timeutil import now_iso

OFFICERS_FILE = Path(__file__).parent / "officers.json"
TRAVEL_S = float(os.environ.get("OFFICER_TRAVEL_S", 240))   # simulated walk time (spec: 4 min)
APPROVE_GATES = os.environ.get("APPROVE_GATES", "close")
APPROVAL_TIMEOUT_S = float(os.environ.get("APPROVAL_TIMEOUT_S", 120))


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
                 notify: Optional[Callable[[dict, str], None]] = None, travel_s: float = TRAVEL_S,
                 translate: Optional[Callable[[str], dict]] = None,
                 approve: str = APPROVE_GATES, approval_timeout_s: float = APPROVAL_TIMEOUT_S):
        self.venue = venue
        self.officers = officers
        self.publish = publish
        self.notify = notify or (lambda o, text: print(f"  -> {o['name']}: {text}"))
        self.travel_s = travel_s
        self.translate = translate or (lambda en: {"en": en})
        self.approve = approve
        self.approval_timeout_s = approval_timeout_s
        self.gates = {l.id: l.state for l in venue.links}
        self.names = {z.id: z.name for z in venue.zones}
        self.pending: dict[str, dict] = {}            # approval_id -> {action, plan_id, timer}
        self.lock = threading.Lock()

    # ---------- helpers ----------
    def _say(self, text: str):
        self.publish("br/status", {"t": now_iso(), "source": "executor", "text": text})

    def _status(self, o: dict, status: str, task: Optional[str] = None):
        o["status"] = status
        self.publish("br/officer", OfficerStatus(
            t=now_iso(), officer_id=o["officer_id"], name=o["name"], zone=o["zone"], status=status,
            task=task, simulated=not o.get("telegram_chat_id")))

    def _arrive(self, o: dict, zone: str, task: str):
        with self.officers.lock:
            o["zone"] = zone
        self._status(o, "arrived", task)

    # ---------- gates and approvals ----------
    def needs_approval(self, a: Action) -> bool:
        return self.approve == "all" or (self.approve == "close" and a.state == "closed")

    def _do_gate(self, a: Action):
        self.gates[a.link] = a.state
        node = gate_node(a.link)
        self.publish(f"br/device/{node}", DeviceCommand(
            to=node, cmd="arrow", value="stop" if a.state == "closed" else "up"))

    def _request(self, a: Action, plan_id: str, why: str):
        aid = f"{plan_id}-{a.link}-{uuid.uuid4().hex[:6]}"
        timer = threading.Timer(self.approval_timeout_s, self._expire, (aid,))
        timer.daemon = True
        with self.lock:
            self.pending[aid] = {"action": a, "plan_id": plan_id, "timer": timer}
        timer.start()
        self.publish("br/approval", {"t": now_iso(), "approval_id": aid, "plan_id": plan_id,
                                     "action": a.model_dump(exclude_none=True), "why": why,
                                     "expires_in_s": int(self.approval_timeout_s)})
        self._say(f"Waiting for operator approval: {a.state} gate {a.link}")

    def _expire(self, aid: str, reason: str = "no answer in time"):
        with self.lock:
            p = self.pending.pop(aid, None)
        if p:
            p["timer"].cancel()
            a = p["action"]
            self._say(f"Approval to {a.state} gate {a.link} withdrawn ({reason}); gate not changed")

    def decide(self, approval_id: str, approved: bool, by: str = "operator") -> bool:
        """An operator's answer from br/approve. Returns False if the request is unknown or expired."""
        with self.lock:
            p = self.pending.pop(approval_id, None)
        if not p:
            return False
        p["timer"].cancel()
        a = p["action"]
        if approved:
            self._do_gate(a)
            self._say(f"{by} approved: gate {a.link} {a.state}")
        else:
            self._say(f"{by} rejected closing gate {a.link}; gate not changed")
        return True

    # ---------- the plan ----------
    def execute(self, cp: ChosenPlan):
        why = cp.plan.why
        with self.lock:                                # a newer plan replaces older requests
            old = list(self.pending)
        for aid in old:
            self._expire(aid, f"replaced by plan {cp.plan.plan_id}")

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
                if self.needs_approval(a):
                    self._request(a, cp.plan.plan_id, why)
                else:
                    self._do_gate(a)
            elif a.type == "hold_inflow":
                text = f"Pause entry at {a.entry} for {a.minutes} minutes. Reason: {why}"
                for o in self.officers.in_zone(a.zone):
                    self.notify(o, text)

        for a in cp.plan.actions:                      # last: translation takes a few seconds
            if a.type == "announce":
                self.publish("br/announce", Announcement(
                    t=now_iso(), zone=a.zone, plan_id=cp.plan.plan_id, texts=self.translate(a.text)))
