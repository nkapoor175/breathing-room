"""Watchdog rules, cooldown and LLM fallback, with a fake Lightning and a fake clock."""
import pytest

from act.watchdog import COOLDOWN_S, Watchdog, WatchdogVerdict
from common.contracts import ChosenPlan, Forecast, Plan, Report, ScoreResult, ZoneForecast, ZoneState


class FakeLightning:
    def __init__(self, replan=False, urgency="low", fail=False):
        self.replan, self.urgency, self.fail, self.calls = replan, urgency, fail, []

    def __call__(self, ctx):
        self.calls.append(ctx)
        if self.fail:
            raise RuntimeError("token factory down")
        return WatchdogVerdict(replan=self.replan, urgency=self.urgency, summary="LLM summary")


def fc(t_sec, p_b, mtd=None, extra=()):
    mtd = mtd if mtd is not None else round(15 - 12 * p_b, 1)
    zones = [ZoneForecast(zone="B", p50_density=4, p90_density=5, p_danger=p_b, minutes_to_danger=mtd)]
    zones += list(extra)
    return Forecast(t=f"2026-10-28T18:{t_sec // 60:02d}:{t_sec % 60:02d}+05:30", zones=zones)


def state(zone, rho):
    return ZoneState(t="2026-10-28T18:00:00+05:30", zone=zone, count=int(rho * 100),
                     density_ppm2=rho, source="sim")


def report(zone, sev, source="volunteer_button", text="pushing here"):
    return Report(t="2026-10-28T18:00:00+05:30", source=source, zone=zone, text=text, severity=sev)


def plan(t="2026-10-28T18:05:00+05:30", promised=0.08):
    return ChosenPlan(t=t, plan=Plan(plan_id="P2", strategy="meter inflow", actions=[], why="x"),
                      score=ScoreResult(plan_id="P2", max_p_danger=promised, min_minutes_to_danger=None, zones=[]),
                      baseline_max_p_danger=0.6, candidates_considered=4)


def test_rule1_fires_once_while_zone_b_climbs():
    """Spec 'done when': fake forecast climbs 0.1 -> 0.7 every 30 s; fire once, not every cycle."""
    dog = Watchdog(FakeLightning())
    fired = []
    for i in range(11):                               # 0.10, 0.16, ... 0.70
        trig = dog.on_forecast(fc(i * 30, round(0.1 + 0.06 * i, 2)), now=i * 30)
        trig = trig or dog.tick(i * 30)
        if trig:
            fired.append((i, trig))
    assert len(fired) == 1
    i, trig = fired[0]
    assert 0.1 + 0.06 * i >= 0.3 and 0.1 + 0.06 * (i - 1) < 0.3
    assert "zone B" in trig.reasons[0]
    assert trig.summary == "LLM summary"


def test_rule1_needs_minutes_to_danger_within_horizon():
    dog = Watchdog(FakeLightning())
    assert dog.on_forecast(fc(0, 0.5, mtd=20), now=0) is None


def test_rule1_refires_after_zone_recovers_and_cooldown():
    dog = Watchdog(FakeLightning())
    assert dog.on_forecast(fc(0, 0.5), now=0)
    assert dog.on_forecast(fc(30, 0.1), now=30) is None      # recovered
    assert dog.on_forecast(fc(90, 0.5), now=90)              # at risk again, cooldown over


def test_cooldown_defers_then_releases():
    dog = Watchdog(FakeLightning())
    other = ZoneForecast(zone="A", p50_density=4, p90_density=5, p_danger=0.4, minutes_to_danger=10)
    assert dog.on_forecast(fc(0, 0.5), now=0)
    assert dog.on_forecast(fc(30, 0.5, extra=[other]), now=30) is None   # zone A new, but cooling down
    assert dog.tick(59) is None
    trig = dog.tick(COOLDOWN_S)
    assert trig and "zone A" in trig.reasons[0]


def test_rule2_report_in_crowded_zone():
    dog = Watchdog(FakeLightning())
    dog.on_zone_state(state("B", 4.5))
    trig = dog.on_report(report("B", 4), now=0)
    assert trig and "zone B" in trig.reasons[0]


def test_button_in_quiet_zone_does_nothing_and_skips_llm():
    llm = FakeLightning(replan=True)
    dog = Watchdog(llm)
    dog.on_zone_state(state("C", 1.0))
    assert dog.on_report(report("C", 4), now=0) is None
    assert llm.calls == []


def test_free_text_report_goes_to_lightning():
    llm = FakeLightning(replan=True, urgency="high")
    dog = Watchdog(llm)
    dog.on_zone_state(state("B", 2.0))
    trig = dog.on_report(report("B", 3, source="telegram", text="people climbing the barricade at gate 2"), now=0)
    assert trig and trig.urgency == "high"
    assert len(llm.calls) == 1                         # the verdict's summary is reused, no 2nd call
    assert llm.calls[0]["recent_reports"][0]["text"].startswith("people climbing")


def test_free_text_lightning_says_no():
    dog = Watchdog(FakeLightning(replan=False))
    assert dog.on_report(report(None, 1, source="call_note", text="lost child near stage"), now=0) is None


def test_severity5_skips_cooldown():
    dog = Watchdog(FakeLightning())
    dog.on_zone_state(state("B", 5.2))
    assert dog.on_forecast(fc(0, 0.5), now=0)
    trig = dog.on_report(report("B", 5, text="someone fell"), now=10)
    assert trig and trig.urgency == "high"


def test_rule3_plan_not_delivering_fires_once_per_plan():
    dog = Watchdog(FakeLightning())
    dog.at_risk = {"B"}                                 # rule 1 already fired earlier
    dog.on_plan(plan(promised=0.08))
    assert dog.on_forecast(fc(4 * 60, 0.5), now=0) is None           # forecast older than the plan
    trig = dog.on_forecast(fc(6 * 60, 0.5), now=100)                 # 0.5 > 0.08 + 0.2
    assert trig and "plan P2" in trig.reasons[0]
    assert dog.on_forecast(fc(7 * 60, 0.5), now=200) is None         # same plan, no repeat


def test_rule3_quiet_when_plan_on_track():
    dog = Watchdog(FakeLightning())
    dog.at_risk = {"B"}
    dog.on_plan(plan(promised=0.08))
    assert dog.on_forecast(fc(6 * 60, 0.25), now=100) is None


def test_llm_failure_falls_back_to_rule_text():
    dog = Watchdog(FakeLightning(fail=True), log=lambda m: None)
    trig = dog.on_forecast(fc(0, 0.5), now=0)
    assert trig and trig.summary.startswith("zone B")
