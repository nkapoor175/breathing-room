"""Fake Sense publisher (stub for Shirali's S03 - she owns and may replace it).

Publishes a ZoneState per zone every 2 s. Zone B fills from 2 to 6 people/m2 over
10 minutes, then loops. Zone ids/areas match the draft demo venue (A-D).

Run:  python -m sense.fake_sense
"""
import random, time

from common.bus import make_client, publish
from common.contracts import ZoneState
from common.timeutil import now_iso

AREAS = {"A": 400.0, "B": 150.0, "C": 900.0, "D": 300.0}   # m2, placeholder until the venue file exists
BASE = {"A": 2.5, "C": 0.8, "D": 1.5}
FILL_S = 600


def main():
    mq = make_client("sense-fake")
    mq.loop_start()
    t0 = time.time()
    while True:
        frac = ((time.time() - t0) % FILL_S) / FILL_S
        for z, area in AREAS.items():
            rho = 2 + 4 * frac if z == "B" else BASE[z]
            rho = max(0.0, rho + random.gauss(0, 0.1))
            speed = max(0.05, 1.2 * (1 - rho / 5.4)) if rho < 5.4 else 0.05
            publish(mq, "br/zone_state", ZoneState(
                t=now_iso(), zone=z, count=int(rho * area), density_ppm2=round(rho, 2),
                speed_mps=round(speed, 2), direction_deg=85.0, source="sim"))
        time.sleep(2)


if __name__ == "__main__":
    main()
