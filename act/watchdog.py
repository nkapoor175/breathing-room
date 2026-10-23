"""Watchdog (A02): decides when the Planner should replan.

Reads Forecast (br/forecast), Report (br/report), ZoneState (br/zone_state) and
ChosenPlan (br/plan). Fires a Trigger when one of the spec's rules becomes true:

  1. a zone NEWLY reaches p_danger >= 0.3 with minutes_to_danger <= 15
  2. a severity >= 4 report arrives for a zone at or above caution density
  3. a plan is active but a later forecast's worst p_danger is > 0.2 above what
     the plan promised (once per plan)

Free-text reports that trip no rule go to Nemotron 3.5 Lightning, which decides
whether they still warrant a replan. Lightning also writes the 1-2 sentence
situation summary. At most one trigger per 60 s; a trigger that lands inside the
cooldown waits for it to end. A severity-5 report skips the cooldown.

The Watchdog class is pure logic (time and the LLM are passed in) so it can be
tested without MQTT or Token Factory.

Run:  python -m act.watchdog
"""
import datetime, json, queue, time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, Optional

from pydantic import BaseModel

from common.contracts import ChosenPlan, Forecast, Report, ZoneState
from common.timeutil import now_iso

THRESHOLDS = json.loads((Path(__file__).resolve().parents[1] / "common" / "thresholds.json").read_text())
CAUTION = THRESHOLDS["caution"]

P_DANGER_RULE = 0.3       # rule 1
HORIZON_MIN = 15          # rule 1
PROMISE_SLACK = 0.2       # rule 3
COOLDOWN_S = 60
REPORT_WINDOW_S = 600     # reports kept for context: last 10 minutes


class WatchdogVerdict(BaseModel):
    replan: bool
    urgency: Literal["low", "high"]
    summary: str


@dataclass
class Trigger:
    t: str
    reasons: list[str]
    urgency: Literal["low", "high"]
    summary: str


Ask = Callable[[dict], WatchdogVerdict]   # context -> Lightning's verdict


def _ts(iso: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(iso)


class Watchdog:
    def __init__(self, ask: Ask, log: Callable[[str], None] = print):
        self.ask = ask
        self.log = log
        self.forecast: Optional[Forecast] = None
        self.states: dict[str, ZoneState] = {}
        self.reports: deque[tuple[float, Report]] = deque()
        self.active_plan: Optional[ChosenPlan] = None
        self.at_risk: set[str] = set()             # zones currently meeting rule 1
        self.plans_flagged: set[str] = set()        # plans rule 3 already fired for
        self.pending: list[str] = []                # reasons waiting for the cooldown
        self.pending_urgent = False
        self.pending_summary: Optional[WatchdogVerdict] = None
        self.last_fire: Optional[float] = None

    # ---------- inputs ----------
    def on_zone_state(self, s: ZoneState):
        self.states[s.zone] = s

    def on_plan(self, p: ChosenPlan):
        self.active_plan = p

    def on_forecast(self, f: Forecast, now: float) -> Optional[Trigger]:
        self.forecast = f
        reasons = []

        # Rule 1: only zones that are newly at risk, so a steady danger fires once.
        risky = {z.zone: z for z in f.zones
                 if z.p_danger >= P_DANGER_RULE
                 and z.minutes_to_danger is not None and z.minutes_to_danger <= HORIZON_MIN}
        for zid in sorted(set(risky) - self.at_risk):
            z = risky[zid]
            reasons.append(f"zone {zid}: {z.p_danger:.0%} chance of danger in about "
                           f"{z.minutes_to_danger:.0f} min")
        self.at_risk = set(risky)

        # Rule 3: the active plan isn't delivering (checked on forecasts made after it).
        p = self.active_plan
        if p and p.plan.plan_id + p.t not in self.plans_flagged and _ts(f.t) > _ts(p.t) and f.zones:
            worst = max(f.zones, key=lambda z: z.p_danger)
            if worst.p_danger > p.score.max_p_danger + PROMISE_SLACK:
                self.plans_flagged.add(p.plan.plan_id + p.t)
                reasons.append(f"plan {p.plan.plan_id} promised {p.score.max_p_danger:.0%} danger, "
                               f"forecast now {worst.p_danger:.0%} in zone {worst.zone}")

        return self._add(reasons, urgent=False, now=now)

    def on_report(self, r: Report, now: float) -> Optional[Trigger]:
        self.reports.append((now, r))
        self._trim(now)
        urgent = r.severity == 5

        # Rule 2: serious report from a zone that is already crowded.
        s = self.states.get(r.zone) if r.zone else None
        if r.severity >= 4 and s and s.density_ppm2 >= CAUTION:
            return self._add([f"report in zone {r.zone} (severity {r.severity}): {r.text} "
                              f"at {s.density_ppm2:.1f} people/m2"], urgent, now)

        # Free text that tripped no rule: let Lightning judge it. Button presses are
        # fixed phrases, so they only count through rule 2.
        if r.source != "volunteer_button":
            v = self._ask()
            if v and v.replan:
                self.pending_summary = v
                return self._add([f"report: {r.text}"], urgent or v.urgency == "high", now)
        return None

    def tick(self, now: float) -> Optional[Trigger]:
        """Call about once a second: releases a trigger once the cooldown ends."""
        if not self.pending:
            return None
        cooled = self.last_fire is None or now - self.last_fire >= COOLDOWN_S
        if not (cooled or self.pending_urgent):
            return None
        return self._fire(now)

    # ---------- internals ----------
    def _add(self, reasons: list[str], urgent: bool, now: float) -> Optional[Trigger]:
        if not reasons:
            return None
        self.pending += reasons
        self.pending_urgent |= urgent
        return self.tick(now)

    def _fire(self, now: float) -> Trigger:
        reasons, urgent = self.pending, self.pending_urgent
        v = self.pending_summary or self._ask(reasons)
        self.pending, self.pending_urgent, self.pending_summary = [], False, None
        self.last_fire = now
        soon = any(z.minutes_to_danger is not None and z.minutes_to_danger <= 5
                   for z in (self.forecast.zones if self.forecast else []) if z.zone in self.at_risk)
        urgency = "high" if urgent or soon or (v and v.urgency == "high") else "low"
        summary = v.summary if v else "; ".join(reasons)
        return Trigger(t=now_iso(), reasons=reasons, urgency=urgency, summary=summary)

    def _ask(self, rule_triggers: Optional[list[str]] = None) -> Optional[WatchdogVerdict]:
        try:
            return self.ask(self.context(rule_triggers))
        except Exception as e:                      # never let the LLM stop the watchdog
            self.log(f"watchdog: Lightning call failed, using rule text ({type(e).__name__}: {e})")
            return None

    def _trim(self, now: float):
        while self.reports and now - self.reports[0][0] > REPORT_WINDOW_S:
            self.reports.popleft()

    def context(self, rule_triggers: Optional[list[str]] = None) -> dict:
        """What Lightning sees: forecast, densities, recent reports, active plan."""
        p = self.active_plan
        return {
            "forecast": [z.model_dump() for z in self.forecast.zones] if self.forecast else [],
            "densities_ppm2": {z: s.density_ppm2 for z, s in sorted(self.states.items())},
            "recent_reports": [r.model_dump(exclude={"node"}) for _, r in self.reports],
            "active_plan": {"strategy": p.plan.strategy, "why": p.plan.why} if p else None,
            "rules_fired": rule_triggers or [],
        }


# ---------- live process ----------
def lightning_ask(on_cost) -> Ask:
    from common.llm import call_json
    system = (Path(__file__).parent / "prompts" / "watchdog.md").read_text(encoding="utf-8")

    def ask(ctx: dict) -> WatchdogVerdict:
        return call_json("lightning", "watchdog", system, json.dumps(ctx), WatchdogVerdict, on_cost=on_cost)
    return ask


def main(on_trigger: Optional[Callable[[Trigger], None]] = None):
    from common.bus import make_client, publish

    inbox: queue.Queue = queue.Queue()
    mq = make_client("act-watchdog")
    mq.on_connect = lambda c, u, f, rc, p: [c.subscribe(t) for t in
                                            ("br/forecast", "br/report", "br/zone_state", "br/plan")]
    mq.on_message = lambda c, u, m: inbox.put((m.topic, m.payload))
    mq.loop_start()

    dog = Watchdog(lightning_ask(lambda cost: publish(mq, "br/cost", cost)))
    print("watchdog running; waiting for forecasts and reports")
    while True:
        trig = None
        try:
            topic, payload = inbox.get(timeout=1)
            now = time.monotonic()
            if topic == "br/forecast":
                trig = dog.on_forecast(Forecast.model_validate_json(payload), now)
            elif topic == "br/report":
                trig = dog.on_report(Report.model_validate_json(payload), now)
            elif topic == "br/zone_state":
                dog.on_zone_state(ZoneState.model_validate_json(payload))
            elif topic == "br/plan":
                dog.on_plan(ChosenPlan.model_validate_json(payload))
        except queue.Empty:
            pass
        except Exception as e:                      # bad message from another slice
            print(f"watchdog: skipped bad message ({type(e).__name__}: {e})")
        trig = trig or dog.tick(time.monotonic())
        if trig:
            print(f"{trig.t} REPLAN ({trig.urgency}): {trig.reasons}\n  summary: {trig.summary}")
            publish(mq, "br/status", {"t": trig.t, "source": "watchdog", "text": trig.summary,
                                      "urgency": trig.urgency, "reasons": trig.reasons})
            if on_trigger:
                on_trigger(trig)                    # the Planner plugs in here (A03)


if __name__ == "__main__":
    main()
