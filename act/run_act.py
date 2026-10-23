"""The whole Act loop in one process: Watchdog -> Planner -> Executor.

The Watchdog loop keeps reading messages; each replan runs on a worker thread so
a slow Ultra call never blocks it. The context is snapshotted on the watchdog
loop at trigger time, so the worker never reads data the loop is changing. If a
trigger arrives while a replan is running, one more replan runs right after.

Run:  python -m act.run_act
Env:  PLANNER_MODEL=super   faster backup planner for filming (default ultra)
      OFFICER_TRAVEL_S=30   simulated officer walk time (default 240)
"""
import asyncio, threading

from act import watchdog
from act.executor import Executor, Officers
from act.planner import PLANNER_MODEL, build_context, load_venue, nemotron_propose, replan
from common.bus import publish
from common.timeutil import now_iso


def main():
    venue = load_venue()
    officers = Officers()
    print(f"act: venue {venue.venue_id} ({len(venue.zones)} zones), {len(officers.list)} officers, "
          f"planner model {PLANNER_MODEL}")
    lock = threading.Lock()
    state = {"busy": False, "again": None, "executor": None}

    def run(ctx, mq):
        executor = state["executor"]
        status = lambda text: publish(mq, "br/status", {"t": now_iso(), "source": "planner", "text": text})
        propose = nemotron_propose(lambda c: publish(mq, "br/cost", c))
        while True:
            try:
                cp = asyncio.run(replan(ctx, propose, status=status))
                publish(mq, "br/plan", cp)
                status(f"Chosen plan {cp.plan.plan_id}: {cp.plan.strategy}. Safe in "
                       f"{1 - cp.score.max_p_danger:.0%} of futures (do nothing: "
                       f"{1 - cp.baseline_max_p_danger:.0%})")
                executor.execute(cp)
            except Exception as e:
                print(f"act: replan failed ({type(e).__name__}: {e})")
                status(f"Planning failed: {e}. Officers: use your judgement and request backup.")
            with lock:
                ctx, state["again"] = state["again"], None
                if ctx is None:
                    state["busy"] = False
                    return

    def on_trigger(trig, dog, mq):
        if state["executor"] is None:
            state["executor"] = Executor(venue, officers, lambda topic, m: publish(mq, topic, m))
        ctx = build_context(venue, dog, officers.per_zone(), state["executor"].gates, trig.summary)
        with lock:
            if state["busy"]:
                state["again"] = ctx                  # replan once more when this one ends
                return
            state["busy"] = True
        threading.Thread(target=run, args=(ctx, mq), daemon=True).start()

    watchdog.main(on_trigger, client_id="act-main")


if __name__ == "__main__":
    main()
