"""Fake Act publisher (A01): a fake ChosenPlan every 60 s, plus the status, cost,
announcement and officer messages around it, so Ananya and the dashboard can build
against real shapes before the planner exists.

Run:  python -m act.fake_act            (Ctrl+C to stop)
      python -m act.fake_act --every 10 (faster, for testing)
"""
import argparse, itertools, random, time

from common.bus import make_client, publish
from common.contracts import (Action, Announcement, ChosenPlan, CostEvent, OfficerStatus,
                              Plan, ScoreResult, ZoneForecast)
from common.timeutil import now_iso

PLANS = [
    Plan(plan_id="P2", strategy="reinforce gate 2 and meter inflow", actions=[
        Action(type="move_officers", count=6, from_zone="C", to_zone="B"),
        Action(type="gate", link="G3", state="closed"),
        Action(type="hold_inflow", entry="Main entrance", zone="A", minutes=10),
        Action(type="announce", zone="A", langs=["ta", "en"],
               text="Please move calmly to your left, towards Gate 1."),
    ], why="Gate 2 approach reaches danger in 9 minutes; this keeps every zone safe in 92% of simulated futures."),
    Plan(plan_id="P1", strategy="reroute to overflow ground", actions=[
        Action(type="gate", link="G4", state="open"),
        Action(type="announce", zone="B", langs=["en", "hi", "ta"],
               text="Please walk slowly to the overflow ground on your right."),
    ], why="Zone B is filling fast; opening G4 lets people spread into the overflow ground."),
]

ANNOUNCE_TEXTS = {
    "en": "Please move calmly to your left, towards Gate 1.",
    "ta": "தயவுசெய்து அமைதியாக இடதுபுறம், கேட் 1 நோக்கி நகரவும்.",
    "hi": "कृपया शांति से बाईं ओर, गेट 1 की तरफ़ चलें।",
}


def one_cycle(mq, plan: Plan):
    publish(mq, "br/status", {"t": now_iso(), "text": "Watchdog: zone B heading for danger, replanning"})
    time.sleep(1)
    publish(mq, "br/status", {"t": now_iso(), "text": "Planning: testing 4 plans in 1,000 futures…"})
    publish(mq, "br/cost", CostEvent(t=now_iso(), role="lightning", purpose="watchdog",
                                     prompt_tokens=1800, completion_tokens=90, usd=0.000130, latency_s=0.8))
    publish(mq, "br/cost", CostEvent(t=now_iso(), role="ultra", purpose="plan",
                                     prompt_tokens=10200, completion_tokens=2900, usd=0.0189, latency_s=21.4))
    time.sleep(2)
    p = round(random.uniform(0.04, 0.12), 2)
    chosen = ChosenPlan(
        t=now_iso(), plan=plan,
        score=ScoreResult(plan_id=plan.plan_id, max_p_danger=p, min_minutes_to_danger=None,
                          zones=[ZoneForecast(zone="B", p50_density=4.1, p90_density=4.8, p_danger=p)]),
        baseline_max_p_danger=round(random.uniform(0.55, 0.7), 2), candidates_considered=4)
    publish(mq, "br/plan", chosen)
    publish(mq, "br/status", {"t": now_iso(), "text": f"Chosen plan {plan.plan_id}: {plan.strategy}"})

    for a in plan.actions:
        if a.type == "gate":
            n = a.link.lstrip("G")
            publish(mq, f"br/device/gate-{n}",
                    {"to": f"gate-{n}", "cmd": "arrow", "value": "stop" if a.state == "closed" else "left"})
        elif a.type == "announce":
            publish(mq, "br/announce", Announcement(t=now_iso(), zone=a.zone, plan_id=plan.plan_id,
                                                    texts={k: ANNOUNCE_TEXTS[k] for k in ["en", "ta", "hi"]}))
            publish(mq, "br/cost", CostEvent(t=now_iso(), role="lightning", purpose="announce",
                                             prompt_tokens=400, completion_tokens=150, usd=0.00006, latency_s=1.1))
        elif a.type == "move_officers":
            for i in range(a.count):
                publish(mq, "br/officer", OfficerStatus(
                    t=now_iso(), officer_id=f"O{i + 1}", name=f"Officer {i + 1}", zone=a.from_zone,
                    status="assigned", task=f"Move to zone {a.to_zone}", simulated=i > 0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--every", type=float, default=60, help="seconds between fake plans")
    args = ap.parse_args()
    mq = make_client("act-fake")
    mq.loop_start()
    for plan in itertools.cycle(PLANS):
        one_cycle(mq, plan)
        print(now_iso(), "published fake plan", plan.plan_id)
        time.sleep(args.every)


if __name__ == "__main__":
    main()
