"""Check Sense output before wiring it in: listens to br/zone_state for 20 s and
reports whether the messages match the contract and the simulator's venue.

Run (while the Sense code is running):  python scripts/check_sense.py
"""
import json, sys, time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import common  # noqa: F401  (loads .env)
from pydantic import ValidationError

from common.bus import make_client
from common.contracts import ZoneState

SECONDS = 20


def main():
    from act.planner import load_venue
    venue = load_venue(log=lambda s: None, wait_s=3)
    zones = {z.id: z for z in venue.zones}
    print(f"venue {venue.venue_id}: zones {sorted(zones)}; listening to br/zone_state for {SECONDS} s…")

    good, bad, times = defaultdict(list), [], defaultdict(list)
    c = make_client("check-sense")
    c.on_connect = lambda cl, u, f, rc, p: cl.subscribe("br/zone_state")

    def on_msg(cl, u, m):
        try:
            s = ZoneState.model_validate_json(m.payload)
        except ValidationError as e:
            bad.append(f"doesn't match the ZoneState contract: {e.errors()[0]['loc']} {e.errors()[0]['msg']} "
                       f"in {m.payload[:120]!r}")
            return
        good[s.zone].append(s)
        times[s.zone].append(time.time())

    c.on_message = on_msg
    c.loop_start()
    time.sleep(SECONDS)
    c.loop_stop()

    problems = list(dict.fromkeys(bad))[:5]
    if not good and not bad:
        problems.append("no messages at all on br/zone_state: is Sense running, with MQTT_* set in .env?")
    for z, msgs in good.items():
        if z not in zones:
            problems.append(f"zone {z!r} isn't in the venue (zones are {sorted(zones)})")
            continue
        last = msgs[-1]
        if last.source == "sim":
            problems.append(f"zone {z}: source is 'sim'. That's the fake feed; is fake_sense still running?")
        expected = last.count / zones[z].area_m2
        if abs(expected - last.density_ppm2) > max(0.5, 0.2 * expected):
            problems.append(f"zone {z}: density {last.density_ppm2} doesn't match count {last.count} / "
                            f"area {zones[z].area_m2} m2 = {expected:.2f}")
        if len(times[z]) >= 3:
            gap = (times[z][-1] - times[z][0]) / (len(times[z]) - 1)
            if gap > 5:
                problems.append(f"zone {z}: one message every {gap:.0f} s (expected ~2 s)")
    missing = sorted(set(zones) - set(good))
    if good and missing:
        problems.append(f"no messages for zones {missing}")

    for z, msgs in sorted(good.items()):
        s = msgs[-1]
        print(f"  zone {z}: {len(msgs)} msgs, last count={s.count} density={s.density_ppm2} "
              f"speed={s.speed_mps} source={s.source}")
    if problems:
        print("\nPROBLEMS:")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print("\nOK: Sense output matches the contract and the venue. Run the demo with --real-sense.")


if __name__ == "__main__":
    main()
