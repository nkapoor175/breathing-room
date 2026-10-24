"""Planner: plan validation, the rule-based plan, choosing, and a full replan with
a fake LLM and a fake /score. Uses the demo venue (zones A-D)."""
import asyncio
from pathlib import Path

import pytest

from act.planner import baseline_plan, build_context, choose, replan, validate_plan
from act.watchdog import Watchdog, WatchdogVerdict
from common.contracts import (Forecast, Plan, PlanCandidates, ScoreResult, Venue, ZoneForecast,
                              ZoneState)

ROOT = Path(__file__).resolve().parents[1]
VENUE = Venue.model_validate_json((ROOT / "data" / "demo-venue.json").read_text(encoding="utf-8"))
OFFICERS = {"A": 4, "B": 2, "C": 3, "D": 3}
DENS = {"A": 2.5, "B": 4.6, "C": 0.8, "D": 1.5}


@pytest.fixture
def ctx():
    dog = Watchdog(lambda c: WatchdogVerdict(replan=False, urgency="low", summary=""))
    for z, d in DENS.items():
        dog.on_zone_state(ZoneState(t="2026-10-28T18:40:00+05:30", zone=z, count=int(d * 100),
                                    density_ppm2=d, source="sim"))
    dog.forecast = Forecast(t="2026-10-28T18:40:30+05:30", zones=[
        ZoneForecast(zone="B", p50_density=5.8, p90_density=7.1, p_danger=0.62, minutes_to_danger=9),
        ZoneForecast(zone="A", p50_density=2.6, p90_density=3.1, p_danger=0.02)])
    gates = {l.id: l.state for l in VENUE.links}
    return build_context(VENUE, dog, OFFICERS, gates, "Zone B reaches danger in 9 minutes.")


def plan(*actions, pid="P1"):
    return Plan.model_validate({"plan_id": pid, "strategy": "test", "actions": list(actions), "why": "test"})


# ---------- validate_plan ----------
def test_valid_plan_passes_unchanged(ctx):
    p = plan({"type": "move_officers", "count": 2, "from_zone": "C", "to_zone": "B"},
             {"type": "hold_inflow", "entry": "Gate 2", "zone": "B", "minutes": 10},
             {"type": "announce", "zone": "B", "langs": ["en", "ta"], "text": "Please move left."})
    fixed, notes = validate_plan(p, ctx)
    assert fixed == p and notes == []


@pytest.mark.parametrize("action, reason", [
    ({"type": "move_officers", "count": 2, "from_zone": "Z", "to_zone": "B"}, "unknown zone"),
    ({"type": "move_officers", "count": 2, "from_zone": "B", "to_zone": "B"}, "makes no sense"),
    ({"type": "gate", "link": "G9", "state": "closed"}, "unknown link"),
    ({"type": "announce", "zone": "C", "text": "Move left."}, "no loudspeaker"),
    ({"type": "hold_inflow", "entry": "Back door", "zone": "A", "minutes": 5}, "unknown entry"),
])
def test_made_up_or_unsafe_actions_are_dropped(ctx, action, reason):
    fixed, notes = validate_plan(plan(action), ctx)
    assert fixed is None and reason in notes[0]


def test_long_announcement_dropped(ctx):
    text = " ".join(["please"] * 21)
    fixed, notes = validate_plan(plan({"type": "announce", "zone": "B", "text": text}), ctx)
    assert fixed is None and "21 words" in notes[0]


@pytest.mark.parametrize("text", ["Danger at gate 2, move back.", "Run to the exit now.", "This is an emergency."])
def test_panic_words_dropped(ctx, text):
    fixed, notes = validate_plan(plan({"type": "announce", "zone": "B", "text": text}), ctx)
    assert fixed is None and "panic word" in notes[0]


def test_calm_announcement_with_running_like_words_ok(ctx):
    assert validate_plan(plan({"type": "announce", "zone": "B", "text": "Please keep walking slowly to Gate 2."}), ctx)[0]


def test_zone_mismatch():
    from act.planner import zone_mismatch
    assert zone_mismatch(VENUE, ["A", "B"]) == set() and zone_mismatch(VENUE, ["A", "E"]) == {"E"}


def test_too_many_actions_dropped(ctx):
    a = {"type": "announce", "zone": "A", "text": "Move left."}
    assert validate_plan(plan(*[a] * 7), ctx)[0] is None


def test_officer_count_clamped_to_what_exists(ctx):
    fixed, notes = validate_plan(plan({"type": "move_officers", "count": 9, "from_zone": "C", "to_zone": "B"}), ctx)
    assert fixed.actions[0].count == 3 and "only 3" in notes[0]


def test_officers_not_double_counted_across_actions(ctx):
    p = plan({"type": "move_officers", "count": 3, "from_zone": "C", "to_zone": "B"},
             {"type": "move_officers", "count": 1, "from_zone": "C", "to_zone": "A"})
    fixed, notes = validate_plan(p, ctx)
    assert fixed is None and "no officers left in zone C" in notes[0]


def test_hold_inflow_repaired(ctx):
    fixed, notes = validate_plan(plan({"type": "hold_inflow", "entry": "Main entrance", "zone": "A", "minutes": 45}), ctx)
    a = fixed.actions[0]
    assert a.zone == "D" and a.minutes == 20 and len(notes) == 2


def test_announce_gets_all_languages_when_missing(ctx):
    fixed, _ = validate_plan(plan({"type": "announce", "zone": "B", "text": "Move left."}), ctx)
    assert fixed.actions[0].langs == ["en", "ta", "hi"]


def test_closing_last_way_out_is_dropped(ctx):
    # B's routes out: G2 to outside, and G3 to A (A -> D -> outside). Closing both traps B.
    p = plan({"type": "gate", "link": "G2", "state": "closed"}, {"type": "gate", "link": "G3", "state": "closed"})
    fixed, notes = validate_plan(p, ctx)
    assert fixed is None and "'B'" in notes[0]


def test_closing_one_of_two_ways_out_is_fine(ctx):
    assert validate_plan(plan({"type": "gate", "link": "G2", "state": "closed"}), ctx)[0] is not None


def test_closing_route_of_empty_zone_is_fine(ctx):
    ctx["zone_states"] = [s | {"count": 0} if s["zone"] == "B" else s for s in ctx["zone_states"]]
    p = plan({"type": "gate", "link": "G2", "state": "closed"}, {"type": "gate", "link": "G3", "state": "closed"})
    assert validate_plan(p, ctx)[0] is not None


# ---------- baseline_plan ----------
def test_baseline_targets_most_at_risk_zone(ctx):
    p = baseline_plan(ctx)
    move, hold, say = p.actions
    assert (move.type, move.from_zone, move.to_zone, move.count) == ("move_officers", "C", "B", 1)
    assert (hold.type, hold.entry, hold.minutes) == ("hold_inflow", "Gate 2", 10)
    assert say.type == "announce" and say.zone == "B" and "Stage front" in say.text
    assert len(say.text.split()) <= 20
    assert validate_plan(p, ctx)[0] is not None


def test_baseline_without_forecast_uses_densest_zone(ctx):
    ctx["forecast"] = []
    assert baseline_plan(ctx).actions[0].to_zone == "B"


# ---------- choose ----------
def sr(pid, p):
    return ScoreResult(plan_id=pid, max_p_danger=p, min_minutes_to_danger=None, zones=[])


def test_choose_lowest_danger_then_fewest_officers_then_fewest_actions():
    big = plan({"type": "move_officers", "count": 6, "from_zone": "C", "to_zone": "B"}, pid="P1")
    small = plan({"type": "move_officers", "count": 2, "from_zone": "C", "to_zone": "B"}, pid="P2")
    smaller = plan({"type": "announce", "zone": "B", "text": "x"}, pid="P3")
    assert choose([big, small], [sr("P1", 0.05), sr("P2", 0.10)])[0].plan_id == "P1"
    assert choose([big, small], [sr("P1", 0.05), sr("P2", 0.05)])[0].plan_id == "P2"
    two = plan({"type": "announce", "zone": "B", "text": "x"}, {"type": "announce", "zone": "A", "text": "y"}, pid="P4")
    assert choose([two, smaller], [sr("P4", 0.05), sr("P3", 0.05)])[0].plan_id == "P3"


# ---------- full replan ----------
def fake_score(by_id, fail=()):
    async def score(plans, ctx):
        return ([None if p.plan_id in fail else sr(p.plan_id, by_id.get(p.plan_id, 0.2)) for p in plans],
                sr("baseline", 0.62))
    return score


GOOD = PlanCandidates(plans=[
    plan({"type": "hold_inflow", "entry": "Gate 2", "zone": "B", "minutes": 10}, pid="P1"),
    plan({"type": "gate", "link": "G4", "state": "open"},
         {"type": "announce", "zone": "A", "text": "Please walk to the overflow ground."}, pid="P2"),
    plan({"type": "move_officers", "count": 3, "from_zone": "C", "to_zone": "B"}, pid="P3"),
])


def test_replan_picks_safest_and_reports_baseline(ctx):
    cp = asyncio.run(replan(ctx, lambda c: GOOD, fake_score({"P2": 0.05, "RB": 0.1}), status=lambda s: None, log=lambda s: None))
    assert cp.plan.plan_id == "P2" and cp.score.max_p_danger == 0.05
    assert cp.baseline_max_p_danger == 0.62 and cp.candidates_considered == 4


def test_replan_drops_invalid_llm_plan(ctx):
    bad = PlanCandidates(plans=GOOD.plans[:2] + [plan({"type": "gate", "link": "G99", "state": "closed"}, pid="P3")])
    logs = []
    cp = asyncio.run(replan(ctx, lambda c: bad, fake_score({}), status=lambda s: None, log=logs.append))
    assert cp.candidates_considered == 3
    assert any("dropped P3" in m for m in logs)


def test_replan_survives_llm_failure_with_rule_based_plan(ctx):
    def boom(c):
        raise RuntimeError("ultra down")
    cp = asyncio.run(replan(ctx, boom, fake_score({}), status=lambda s: None, log=lambda s: None))
    assert cp.plan.plan_id == "RB" and cp.candidates_considered == 1


def test_replan_skips_plans_whose_scoring_failed(ctx):
    cp = asyncio.run(replan(ctx, lambda c: GOOD, fake_score({"P1": 0.01}, fail={"P1"}),
                            status=lambda s: None, log=lambda s: None))
    assert cp.plan.plan_id != "P1" and cp.candidates_considered == 3


def test_replan_asks_for_backup_when_nothing_is_safe(ctx):
    cp = asyncio.run(replan(ctx, lambda c: GOOD, fake_score({k: 0.5 for k in ("P1", "P2", "P3", "RB")}),
                            status=lambda s: None, log=lambda s: None))
    assert "Request backup" in cp.plan.why


def test_replan_status_messages(ctx):
    seen = []
    asyncio.run(replan(ctx, lambda c: GOOD, fake_score({}), status=seen.append, log=lambda s: None))
    assert seen[-1] == "Testing 4 plans in 1,000 futures…"
