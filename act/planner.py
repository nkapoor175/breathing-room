"""Planner (A03): turns a Watchdog trigger into a ChosenPlan.

One replan:
  1. context: venue, zone states, forecast, recent reports, officers per zone,
     gate states, plan in progress, watchdog summary
  2. Nemotron 3 Ultra proposes 3 plans (PlanCandidates)
  3. validate_plan repairs small problems and drops unsafe or made-up plans
  4. baseline_plan adds a simple rule-based plan, so a plan always exists
  5. every candidate + "do nothing" is scored in parallel by Imagine's /score
  6. choose: lowest max_p_danger, then fewer officers moved, then fewer actions

The LLM proposes, the simulation decides.
"""
import asyncio, json, os, re, time
from collections import deque
from pathlib import Path
from typing import Awaitable, Callable, Optional

import httpx

from common.contracts import ChosenPlan, Plan, PlanCandidates, ScoreResult, Venue
from common.timeutil import now_iso

ROOT = Path(__file__).resolve().parents[1]
IMAGINE = os.environ.get("IMAGINE_API_URL", "http://localhost:8002")
VENUE_ID = os.environ.get("VENUE_ID", "vit-main-ground")
PLANNER_MODEL = os.environ.get("PLANNER_MODEL", "ultra")   # "super" = faster backup (spec 11.5)

MAX_ACTIONS = 6
MAX_HOLD_MIN = 20
BACKUP_THRESHOLD = 0.3
LLM_TIMEOUT_S = 40          # leaves time for scoring inside the 60 s target
ALL_LANGS = ["en", "ta", "hi"]
MAX_ANNOUNCE_WORDS = 20
# Words that can cause panic or a rush if heard over a loudspeaker (planner prompt rule).
PANIC_WORDS = re.compile(r"\b(danger\w*|stampede|crush\w*|panic|emergency|run|running|hurry|"
                         r"fire|bomb|die|dying|dead|death|evacuate)\b", re.IGNORECASE)


# ---------- inputs ----------
def load_venue(log: Callable[[str], None] = print) -> Venue:
    """Imagine API first, then Ananya's venue file, then our demo placeholder.
    Says where the venue came from, loudly if it is the placeholder."""
    try:
        r = httpx.get(f"{IMAGINE}/venue/{VENUE_ID}", timeout=5)
        r.raise_for_status()
        log(f"venue: {VENUE_ID} from Imagine API {IMAGINE}")
        return Venue.model_validate(r.json())
    except Exception as e:
        log(f"venue: Imagine API has no venue {VENUE_ID!r} ({type(e).__name__}); trying local files")
    for p in (ROOT / "imagine" / "venues" / f"{VENUE_ID}.json", ROOT / "data" / "demo-venue.json"):
        if p.exists():
            if p.parent.name == "data":
                log(f"venue: WARNING using the placeholder {p.relative_to(ROOT)}. If Imagine is running "
                    f"with a different venue, plans and scores will refer to different zones. "
                    f"Check VENUE_ID in .env.")
            else:
                log(f"venue: {VENUE_ID} from {p.relative_to(ROOT)}")
            return Venue.model_validate_json(p.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"no venue {VENUE_ID}: Imagine API down and no local venue file")


def zone_mismatch(venue: Venue, zone_ids) -> set[str]:
    """Zone ids (e.g. from a forecast) that the venue doesn't have. Non-empty means
    Act and Imagine are using different venues."""
    return set(zone_ids) - {z.id for z in venue.zones}


def build_context(venue: Venue, dog, officers_per_zone: dict[str, int],
                  gate_states: dict[str, str], summary: str) -> dict:
    """Everything the planner (LLM and code) sees. `dog` is the live Watchdog."""
    p = dog.active_plan
    return {
        "venue": {
            "zones": [{"id": z.id, "name": z.name, "area_m2": z.area_m2} for z in venue.zones],
            "links": [{"id": l.id, "from": l.from_zone, "to": l.to_zone, "width_m": l.width_m,
                       "kind": l.kind, "state": gate_states.get(l.id, l.state)} for l in venue.links],
            "entries": [e.model_dump() for e in venue.entries],
            "pa_zones": venue.pa_zones,
        },
        "zone_states": [s.model_dump() for _, s in sorted(dog.states.items())],
        "forecast": [z.model_dump() for z in dog.forecast.zones] if dog.forecast else [],
        "recent_reports": [r.model_dump(exclude={"node"}) for _, r in dog.reports],
        "officers_per_zone": dict(officers_per_zone),
        "plan_in_progress": p.plan.model_dump() if p else None,
        "watchdog_summary": summary,
    }


# ---------- checking plans ----------
def _routes_out(zones: set[str], links: list[dict], state: dict[str, str]) -> set[str]:
    """Zones that can still reach "outside" through open links (either direction)."""
    reach, todo = {"outside"}, deque(["outside"])
    while todo:
        here = todo.popleft()
        for l in links:
            if state[l["id"]] != "open":
                continue
            for a, b in ((l["from"], l["to"]), (l["to"], l["from"])):
                if a == here and b not in reach:
                    reach.add(b)
                    todo.append(b)
    return reach & zones


def validate_plan(plan: Plan, ctx: dict) -> tuple[Optional[Plan], list[str]]:
    """Return (repaired plan, notes) or (None, [reason]) if the plan must be dropped."""
    v = ctx["venue"]
    zones = {z["id"] for z in v["zones"]}
    links = {l["id"]: l for l in v["links"]}
    entries = {e["name"]: e["zone"] for e in v["entries"]}
    pa = set(v["pa_zones"])
    available = dict(ctx["officers_per_zone"])
    state = {lid: l["state"] for lid, l in links.items()}
    notes, fixed = [], []

    if not plan.actions:
        return None, ["plan has no actions"]
    if len(plan.actions) > MAX_ACTIONS:
        return None, [f"{len(plan.actions)} actions (max {MAX_ACTIONS})"]

    for a in plan.actions:
        a = a.model_copy()
        if a.type == "move_officers":
            if a.from_zone not in zones or a.to_zone not in zones:
                return None, [f"move_officers uses unknown zone {a.from_zone}->{a.to_zone}"]
            if a.from_zone == a.to_zone or not a.count or a.count < 1:
                return None, [f"move_officers {a.count} {a.from_zone}->{a.to_zone} makes no sense"]
            have = available.get(a.from_zone, 0)
            if have < 1:
                return None, [f"no officers left in zone {a.from_zone}"]
            if a.count > have:
                notes.append(f"moved officers {a.count}->{have} (only {have} in zone {a.from_zone})")
                a.count = have
            available[a.from_zone] -= a.count
        elif a.type == "gate":
            if a.link not in links or a.state not in ("open", "closed"):
                return None, [f"gate action on unknown link {a.link!r} or bad state {a.state!r}"]
            state[a.link] = a.state
        elif a.type == "announce":
            if a.zone not in zones or not a.text:
                return None, [f"announce in unknown zone {a.zone!r} or with no text"]
            if a.zone not in pa:
                return None, [f"no loudspeaker in zone {a.zone}"]
            if len(a.text.split()) > MAX_ANNOUNCE_WORDS:
                return None, [f"announcement has {len(a.text.split())} words (max {MAX_ANNOUNCE_WORDS})"]
            panic = PANIC_WORDS.search(a.text)
            if panic:
                return None, [f"announcement uses panic word {panic.group()!r}"]
            if not a.langs:
                a.langs = list(ALL_LANGS)
        elif a.type == "hold_inflow":
            if a.entry not in entries:
                return None, [f"hold_inflow at unknown entry {a.entry!r}"]
            if a.zone != entries[a.entry]:
                notes.append(f"hold_inflow zone {a.zone}->{entries[a.entry]} (where {a.entry} leads)")
                a.zone = entries[a.entry]
            if not a.minutes or a.minutes < 1:
                notes.append("hold_inflow minutes missing, set to 10")
                a.minutes = 10
            if a.minutes > MAX_HOLD_MIN:
                notes.append(f"hold_inflow {a.minutes}->{MAX_HOLD_MIN} min")
                a.minutes = MAX_HOLD_MIN
        fixed.append(a)

    # Never cut an occupied zone's last route out. Zones with no reading count as occupied.
    empty = {s["zone"] for s in ctx["zone_states"] if s["count"] == 0}
    occupied = zones - empty
    before = _routes_out(zones, v["links"], {lid: l["state"] for lid, l in links.items()})
    after = _routes_out(zones, v["links"], state)
    trapped = (occupied & before) - after
    if trapped:
        return None, [f"gate changes leave zone(s) {sorted(trapped)} with no way out"]

    return plan.model_copy(update={"actions": fixed}), notes


# ---------- the simple plan that is always in the running ----------
def baseline_plan(ctx: dict) -> Plan:
    v = ctx["venue"]
    names = {z["id"]: z["name"] for z in v["zones"]}
    dens = {s["zone"]: s["density_ppm2"] for s in ctx["zone_states"]}
    if ctx["forecast"]:
        worst = max(ctx["forecast"], key=lambda z: (z["p_danger"], -(z["minutes_to_danger"] or 99)))
        target = worst["zone"]
    else:
        target = max(names, key=lambda z: dens.get(z, 0))

    neighbours = {l["to"] if l["from"] == target else l["from"]
                  for l in v["links"] if target in (l["from"], l["to"]) and l["state"] == "open"} - {"outside"}
    actions = []

    donors = [z for z, n in ctx["officers_per_zone"].items() if z != target and n > 0]
    if donors:
        donor = min(donors, key=lambda z: dens.get(z, 0))
        n = max(1, ctx["officers_per_zone"][donor] // 3)
        actions.append({"type": "move_officers", "count": n, "from_zone": donor, "to_zone": target})

    feeding = ([e for e in v["entries"] if e["zone"] == target] or
               [e for e in v["entries"] if e["zone"] in neighbours])
    if feeding:
        e = feeding[0]
        actions.append({"type": "hold_inflow", "entry": e["name"], "zone": e["zone"], "minutes": 10})

    dest = min(neighbours, key=lambda z: dens.get(z, 0)) if neighbours else None
    if dest and target in v["pa_zones"]:
        actions.append({"type": "announce", "zone": target, "langs": list(ALL_LANGS),
                        "text": f"Please walk slowly towards {names[dest]}. Do not push. Keep space for others."})

    why = (f"{names[target]} (zone {target}) is most at risk; slow new arrivals, add officers"
           + (f" and guide people to {names[dest]}." if dest else "."))
    return Plan.model_validate({"plan_id": "RB", "strategy": "rule-based: reinforce, meter, redirect",
                                "actions": actions, "why": why})


# ---------- scoring and choosing ----------
async def score_all(plans: list[Plan], ctx: dict) -> tuple[list[Optional[ScoreResult]], Optional[ScoreResult]]:
    """POST /score for every plan and /score/baseline for "do nothing", all at once."""
    body = {"state": ctx["zone_states"], "officers": ctx["officers_per_zone"]}
    async with httpx.AsyncClient(timeout=20) as http:
        async def one(p: Plan):
            r = await http.post(f"{IMAGINE}/score", json={"plan": p.model_dump(), **body})
            r.raise_for_status()
            return ScoreResult.model_validate(r.json())

        async def base():
            r = await http.post(f"{IMAGINE}/score/baseline", json={"state": body["state"]})
            r.raise_for_status()
            return ScoreResult.model_validate(r.json())

        out = await asyncio.gather(base(), *(one(p) for p in plans), return_exceptions=True)
    clean = [None if isinstance(x, Exception) else x for x in out]
    return clean[1:], clean[0]


def officers_moved(p: Plan) -> int:
    return sum(a.count or 0 for a in p.actions if a.type == "move_officers")


def choose(plans: list[Plan], scores: list[ScoreResult]) -> tuple[Plan, ScoreResult]:
    best = min(range(len(plans)),
               key=lambda i: (scores[i].max_p_danger, officers_moved(plans[i]), len(plans[i].actions)))
    return plans[best], scores[best]


Propose = Callable[[dict], PlanCandidates]
Score = Callable[[list[Plan], dict], Awaitable[tuple[list[Optional[ScoreResult]], Optional[ScoreResult]]]]


async def replan(ctx: dict, propose: Propose, score: Score = score_all,
                 status: Callable[[str], None] = print, log: Callable[[str], None] = print) -> ChosenPlan:
    t0 = time.monotonic()
    status("Planning: asking Nemotron for 3 plans…")
    try:
        cands = (await asyncio.wait_for(asyncio.to_thread(propose, ctx), LLM_TIMEOUT_S)).plans
    except Exception as e:                          # timeout, invalid JSON, network
        log(f"planner: LLM gave no plans ({type(e).__name__}: {e}); using the rule-based plan only")
        cands = []

    plans: list[Plan] = []
    for p in cands + [baseline_plan(ctx)]:
        fixed, notes = validate_plan(p, ctx)
        if fixed is None:
            log(f"planner: dropped {p.plan_id} ({p.strategy}): {notes[0]}")
            continue
        for n in notes:
            log(f"planner: repaired {p.plan_id}: {n}")
        if any(q.plan_id == fixed.plan_id for q in plans):   # keep ids unique for /score
            fixed = fixed.model_copy(update={"plan_id": f"{fixed.plan_id}-{len(plans) + 1}"})
        plans.append(fixed)
    if not plans:
        raise RuntimeError("no valid plan, not even the rule-based one")

    status(f"Testing {len(plans)} plans in 1,000 futures…")
    scores, base = await score(plans, ctx)
    scored = [(p, s) for p, s in zip(plans, scores) if s is not None]
    for p, s in zip(plans, scores):
        if s is None:
            log(f"planner: /score failed for {p.plan_id}, leaving it out")
    if not scored:
        raise RuntimeError("Imagine /score failed for every plan")
    plan, sc = choose([p for p, _ in scored], [s for _, s in scored])

    if sc.max_p_danger > BACKUP_THRESHOLD:
        plan = plan.model_copy(update={"why": plan.why + " Request backup: no available plan keeps every zone safe."})
    baseline_p = base.max_p_danger if base else max((z["p_danger"] for z in ctx["forecast"]), default=0.0)
    log(f"planner: chose {plan.plan_id} ({plan.strategy}) danger {sc.max_p_danger:.0%} vs "
        f"{baseline_p:.0%} doing nothing, {len(scored)} candidates, {time.monotonic() - t0:.1f} s")
    return ChosenPlan(t=now_iso(), plan=plan, score=sc, baseline_max_p_danger=baseline_p,
                      candidates_considered=len(scored))


def nemotron_propose(on_cost, role: str = PLANNER_MODEL) -> Propose:
    from common.llm import call_json
    system = (Path(__file__).parent / "prompts" / "planner.md").read_text(encoding="utf-8")

    def propose(ctx: dict) -> PlanCandidates:
        return call_json(role, "plan", system, json.dumps(ctx), PlanCandidates, on_cost=on_cost)
    return propose
