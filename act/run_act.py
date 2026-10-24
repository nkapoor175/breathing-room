"""The whole Act loop in one process: Watchdog -> Planner -> Executor.

The Watchdog loop keeps reading messages; each replan runs on a worker thread so
a slow Ultra call never blocks it. The context is snapshotted on the watchdog
loop at trigger time, so the worker never reads data the loop is changing. If a
trigger arrives while a replan is running, one more replan runs right after.

The executor has its own MQTT connection: it publishes actions and listens on
br/approve for operators approving or rejecting gate closures.

Run:  python -m act.run_act
Env:  PLANNER_MODEL=super   faster backup planner for filming (default ultra)
      OFFICER_TRAVEL_S=30   simulated officer walk time (default 240)
      APPROVE_GATES=none    skip operator approval for gate closures (default close)
"""
import asyncio, json, threading

from act import telegram_bot, watchdog
from act.announce import Announcer, nemotron_ask as announce_ask
from act.executor import APPROVE_GATES, Executor, Officers
from act.planner import (PLANNER_MODEL, build_context, load_venue, nemotron_propose, replan,
                         zone_mismatch)
from common.bus import make_client, publish
from common.timeutil import now_iso


def main():
    venue = load_venue()
    officers = Officers()
    print(f"act: venue {venue.venue_id} ({len(venue.zones)} zones), {len(officers.list)} officers, "
          f"planner model {PLANNER_MODEL}, gate approval {APPROVE_GATES}")

    ex_mq = make_client("act-executor")
    announcer = Announcer(announce_ask(lambda c: publish(ex_mq, "br/cost", c)))
    executor = Executor(venue, officers, lambda topic, m: publish(ex_mq, topic, m),
                        translate=announcer.texts)

    def on_approve(client, userdata, msg):
        try:
            d = json.loads(msg.payload)
            if not executor.decide(d["approval_id"], bool(d["approved"]), d.get("by") or "operator"):
                print(f"act: approval {d.get('approval_id')} unknown or already expired")
        except Exception as e:
            print(f"act: bad br/approve message ({type(e).__name__}: {e})")

    ex_mq.on_connect = lambda c, u, f, rc, p: c.subscribe("br/approve")
    ex_mq.on_message = on_approve
    ex_mq.loop_start()

    bot = telegram_bot.build(venue, officers, executor, lambda topic, m: publish(ex_mq, topic, m),
                             lambda c: publish(ex_mq, "br/cost", c))
    if bot:
        executor.notify = bot.notify
        bot.start_in_thread()

    lock = threading.Lock()
    state = {"busy": False, "again": None}

    def run(ctx, mq):
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
        if dog.forecast:
            odd = zone_mismatch(venue, [z.zone for z in dog.forecast.zones])
            if odd:
                msg = (f"WARNING: forecast has zones {sorted(odd)} that venue {venue.venue_id} doesn't. "
                       f"Act and Imagine are using different venues; check VENUE_ID.")
                print(f"act: {msg}")
                publish(mq, "br/status", {"t": now_iso(), "source": "planner", "text": msg})
        ctx = build_context(venue, dog, officers.per_zone(), executor.gates, trig.summary)
        with lock:
            if state["busy"]:
                state["again"] = ctx                  # replan once more when this one ends
                return
            state["busy"] = True
        threading.Thread(target=run, args=(ctx, mq), daemon=True).start()

    watchdog.main(on_trigger, client_id="act-main")


if __name__ == "__main__":
    main()
