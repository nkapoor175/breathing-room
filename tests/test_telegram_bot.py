"""Telegram bot core (no Telegram needed): sign-up, buttons, reports, restart."""
from pathlib import Path

import pytest

from act.executor import Executor, Officers
from act.telegram_bot import OfficerBot, Registry, status_buttons
from common.contracts import ChosenPlan, Plan, Report, ScoreResult, Venue

ROOT = Path(__file__).resolve().parents[1]
VENUE = Venue.model_validate_json((ROOT / "data" / "demo-venue.json").read_text(encoding="utf-8"))
PHONE_A, PHONE_B = 1111, 2222


def report(zone, sev=4, text="People pushing near Gate 2"):
    return Report(t="2026-10-25T18:00:00+05:30", source="telegram", zone=zone, text=text, severity=sev)


@pytest.fixture
def world(tmp_path):
    sent, told = [], []
    officers = Officers()
    ex = Executor(VENUE, officers, lambda t, m: sent.append((t, m)), travel_s=60, approve="none",
                  notify=lambda o, text, ask_status=False: told.append((o["officer_id"], text, ask_status)))
    fused = {"zone": "B"}
    bot = OfficerBot(VENUE, officers, ex, lambda t, m: sent.append((t, m)),
                     lambda text, chat_id: report(fused["zone"]), Registry(tmp_path / "reg.json"), log=lambda s: None)
    return bot, ex, officers, sent, told, fused, tmp_path


def officer_msgs(sent):
    return [(m.officer_id, m.status, m.zone) for t, m in sent if t == "br/officer"]


def test_officer_signup_takes_over_simulated_officer(world):
    bot, ex, officers, sent, *_ = world
    reply = bot.register(PHONE_A, "Ravi", "officer", "C")
    assert "officer in Overflow ground (zone C)" in reply
    o = officers.by_chat(PHONE_A)
    assert o["officer_id"] == "O7" and o["name"] == "Ravi"
    assert officer_msgs(sent) == [("O7", "idle", "C")]
    assert officers.per_zone()["C"] == 3                         # no extra officer invented


def test_second_phone_in_zone_gets_next_officer_and_extra_phones_add_officers(world):
    bot, _, officers, *_ = world
    bot.register(PHONE_A, "Ravi", "officer", "B")
    bot.register(PHONE_B, "Meena", "officer", "B")
    bot.register(3333, "Arun", "officer", "B")                  # zone B has only 2 officers
    assert [officers.by_chat(c)["officer_id"] for c in (PHONE_A, PHONE_B, 3333)] == ["O5", "O6", "O13"]
    assert officers.per_zone()["B"] == 3


def test_reregistering_releases_old_officer(world):
    bot, _, officers, *_ = world
    bot.register(PHONE_A, "Ravi", "officer", "C")
    bot.register(PHONE_A, "Ravi", "officer", "A")
    assert officers.by_id("O7")["telegram_chat_id"] is None and officers.by_id("O7")["name"] == "Officer 7"
    assert officers.by_chat(PHONE_A)["zone"] == "A"


def test_bad_signup_rejected(world):
    bot, *_ = world
    assert "/start" in bot.register(PHONE_A, "Ravi", "officer", "Z")
    assert "/start" in bot.register(PHONE_A, "Ravi", "chief", "A")


def test_plan_reaches_phone_with_buttons_and_presses_update_status(world):
    bot, ex, officers, sent, told, *_ = world
    bot.register(PHONE_A, "Ravi", "officer", "C")
    p = Plan.model_validate({"plan_id": "P1", "strategy": "s", "why": "Zone B in 9 min.",
                             "actions": [{"type": "move_officers", "count": 1, "from_zone": "C", "to_zone": "B"}]})
    ex.execute(ChosenPlan(t="2026-10-25T18:00:00+05:30", plan=p, baseline_max_p_danger=0.6, candidates_considered=4,
                          score=ScoreResult(plan_id="P1", max_p_danger=0.1, min_minutes_to_danger=None, zones=[])))
    assert told == [("O7", "Move to Gate 2 approach (zone B) now. Reason: Zone B in 9 min.", True)]
    ok, _ = bot.pressed(PHONE_A, "O7", "on_the_way")
    assert ok
    ok, reply = bot.pressed(PHONE_A, "O7", "arrived")
    assert ok and "Gate 2 approach (zone B)" in reply
    assert officer_msgs(sent)[-2:] == [("O7", "on_the_way", "C"), ("O7", "arrived", "B")]
    assert officers.per_zone()["B"] == 3
    assert bot.registry.get(PHONE_A)["zone"] == "B"          # restart and reports use the new zone


def test_someone_elses_buttons_refused(world):
    bot, *_ = world
    bot.register(PHONE_A, "Ravi", "officer", "C")
    ok, reply = bot.pressed(PHONE_B, "O7", "arrived")
    assert not ok and "isn't yours" in reply


def test_volunteer_text_becomes_report(world):
    bot, _, _, sent, *_ = world
    bot.register(PHONE_B, "Meena", "volunteer", "A")
    reply = bot.report_text(PHONE_B, "கேட் 2 அருகே தள்ளுகிறார்கள்")
    (r,) = [m for t, m in sent if t == "br/report"]
    assert r.zone == "B" and r.severity == 4 and "severity 4/5" in reply


def test_report_without_zone_uses_senders_zone(world):
    bot, _, _, sent, _, fused, _ = world
    fused["zone"] = None
    bot.register(PHONE_B, "Meena", "volunteer", "A")
    bot.report_text(PHONE_B, "very crowded here")
    (r,) = [m for t, m in sent if t == "br/report"]
    assert r.zone == "A"


def test_unregistered_text_asks_for_start(world):
    bot, _, _, sent, *_ = world
    assert "/start" in bot.report_text(PHONE_A, "hello")
    assert not [m for t, m in sent if t == "br/report"]


def test_signups_survive_restart(world):
    bot, ex, _, sent, _, _, tmp_path = world
    bot.register(PHONE_A, "Ravi", "officer", "D")
    officers2 = Officers()
    OfficerBot(VENUE, officers2, ex, lambda t, m: None, lambda text, c: report("A"),
               Registry(tmp_path / "reg.json"), log=lambda s: None)
    assert officers2.by_chat(PHONE_A)["officer_id"] == "O10"
    assert "officer Ravi in Main entrance plaza" in OfficerBot(
        VENUE, Officers(), ex, lambda t, m: None, lambda text, c: report("A"),
        Registry(tmp_path / "reg.json"), log=lambda s: None).whoami(PHONE_A)


def test_status_buttons():
    assert [b.text for b in status_buttons("O7").inline_keyboard[0]] == ["🚶 On my way", "✅ Arrived"]
    assert [b.text for b in status_buttons("O7", after="on_the_way").inline_keyboard[0]] == ["✅ Arrived"]
    assert status_buttons("O7", after="arrived") is None
