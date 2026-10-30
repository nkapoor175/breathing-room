"""Fake Sense publisher (stub for Shirali's S03 - she owns and may replace it).

Publishes a ZoneState per zone every 2 s. One zone fills from 2 to 6 people/m2 over
FAKE_FILL_S seconds (default 10 min), then loops; the other zones stay calm. The
filling zone is FAKE_CLIMB_ZONE, or by default the venue's dead end (no way outside,
fewest connections), e.g. a stage front: where real crushes build up. Zone ids and real areas come from
the venue the simulator uses (Imagine API, else the local venue file), so counts
and densities make sense for that venue.

Run:  python -m sense.fake_sense
"""
import os, random, time

from common.bus import make_client, publish
from common.contracts import ZoneState
from common.timeutil import now_iso

FILL_S = float(os.environ.get("FAKE_FILL_S", 600))
BASE = [2.0, 1.2, 0.8, 1.5, 1.0]  # people/m2 for the calm zones


def dead_end(venue) -> str:
    """Zone with no direct way outside and the fewest connections."""
    ids = [z.id for z in venue.zones]
    links = [(l.from_zone, l.to_zone) for l in venue.links]
    outside = {a for a, b in links if b not in ids} | {b for a, b in links if a not in ids}
    degree = {z: sum(z in l for l in links) for z in ids}
    inner = [z for z in ids if z not in outside] or ids
    return min(inner, key=lambda z: degree[z])


def main():
    from act.planner import load_venue
    venue = load_venue()
    areas = {z.id: z.area_m2 for z in venue.zones}
    CLIMB = os.environ.get("FAKE_CLIMB_ZONE") or dead_end(venue)
    base = {z: BASE[i % len(BASE)] for i, z in enumerate(areas)}
    print(f"fake_sense: areas {areas}; zone {CLIMB} fills 2 -> 6 people/m2 over {FILL_S:.0f} s")
    mq = make_client("sense-fake")
    mq.loop_start()
    t0 = time.time()
    while True:
        frac = ((time.time() - t0) % FILL_S) / FILL_S
        for z, area in areas.items():
            rho = 2 + 4 * frac if z == CLIMB else base[z]
            rho = max(0.0, rho + random.gauss(0, 0.1))
            speed = max(0.05, 1.2 * (1 - rho / 5.4)) if rho < 5.4 else 0.05
            publish(mq, "br/zone_state", ZoneState(
                t=now_iso(), zone=z, count=int(rho * area), density_ppm2=round(rho, 2),
                speed_mps=round(speed, 2), direction_deg=85.0, source="sim"))
        time.sleep(2)


if __name__ == "__main__":
    main()
