"""Executor: each action type turns into the right messages."""
import time
from pathlib import Path

from act.executor import Executor, Officers, gate_node
from common.contracts import ChosenPlan, Plan, ScoreResult, Venue

ROOT = Path(__file__).resolve().parents[1]
VENUE = Venue.model_validate_json((ROOT / "data" / "demo-venue.json").read_text(encoding="utf-8"))


def chosen(*actions):
    p = Plan.model_validate({"plan_id": "P1", "strategy": "s", "actions": list(actions), "why": "Zone B in 9 min."})
    return ChosenPlan(t="2026-10-28T18:42:05+05:30", plan=p,
                      score=ScoreResult(plan_id="P1", max_p_danger=0.1, min_minutes_to_danger=None, zones=[]),
                      baseline_max_p_danger=0.6, candidates_considered=4)


def make(travel_s=0.2, approve="none", timeout=60, translate=None):
    sent, told = [], []
    ex = Executor(VENUE, Officers(), lambda topic, m: sent.append((topic, m)),
                  notify=lambda o, text: told.append((o["officer_id"], text)), travel_s=travel_s,
                  translate=translate, approve=approve, approval_timeout_s=timeout)
    return ex, sent, told


def devices(sent):
    return [(t, m.value) for t, m in sent if t.startswith("br/device/")]


def approvals(sent):
    return [m for t, m in sent if t == "br/approval"]


def test_gate_node_names():
    assert gate_node("G3") == "gate-3" and gate_node("G12") == "gate-12"


def test_gate_close_and_open():
    ex, sent, _ = make()
    ex.execute(chosen({"type": "gate", "link": "G3", "state": "closed"}, {"type": "gate", "link": "G4", "state": "open"}))
    assert devices(sent) == [("br/device/gate-3", "stop"), ("br/device/gate-4", "up")]
    assert ex.gates["G3"] == "closed" and ex.gates["G4"] == "open"


def test_move_officers_simulated_walk():
    ex, sent, told = make(travel_s=0.3)
    ex.execute(chosen({"type": "move_officers", "count": 2, "from_zone": "C", "to_zone": "B"}))
    assert [o for o, _ in told] == ["O7", "O8"]
    assert "Gate 2 approach" in told[0][1]
    time.sleep(2.5)                                    # on_the_way after 2 s, arrived after travel
    statuses = [(m.officer_id, m.status, m.zone) for t, m in sent if t == "br/officer"]
    assert ("O7", "assigned", "C") in statuses and ("O7", "arrived", "B") in statuses
    assert ex.officers.per_zone()["B"] == 4 and ex.officers.per_zone()["C"] == 1


def test_announce_and_hold_inflow():
    ex, sent, told = make()
    ex.execute(chosen({"type": "announce", "zone": "B", "langs": ["en"], "text": "Please move left."},
                      {"type": "hold_inflow", "entry": "Gate 2", "zone": "B", "minutes": 10}))
    (topic, ann), = sent
    assert topic == "br/announce" and ann.texts == {"en": "Please move left."}
    assert {o for o, _ in told} == {"O5", "O6"} and "Pause entry at Gate 2" in told[0][1]


# ---------- operator approval for gate closures ----------
CLOSE_G3 = {"type": "gate", "link": "G3", "state": "closed"}


def test_closing_waits_for_approval_opening_does_not():
    ex, sent, _ = make(approve="close")
    ex.execute(chosen(CLOSE_G3, {"type": "gate", "link": "G4", "state": "open"}))
    assert devices(sent) == [("br/device/gate-4", "up")]
    (req,) = approvals(sent)
    assert req["action"] == CLOSE_G3 and req["plan_id"] == "P1" and ex.gates["G3"] == "open"


def test_approve_closes_gate():
    ex, sent, _ = make(approve="close")
    ex.execute(chosen(CLOSE_G3))
    aid = approvals(sent)[0]["approval_id"]
    assert ex.decide(aid, True, by="Navika")
    assert devices(sent) == [("br/device/gate-3", "stop")] and ex.gates["G3"] == "closed"
    assert not ex.decide(aid, True)                       # can't approve twice


def test_reject_leaves_gate():
    ex, sent, _ = make(approve="close")
    ex.execute(chosen(CLOSE_G3))
    assert ex.decide(approvals(sent)[0]["approval_id"], False)
    assert devices(sent) == [] and ex.gates["G3"] == "open"


def test_no_answer_means_no_change():
    ex, sent, _ = make(approve="close", timeout=0.2)
    ex.execute(chosen(CLOSE_G3))
    aid = approvals(sent)[0]["approval_id"]
    time.sleep(0.5)
    assert not ex.decide(aid, True)
    assert devices(sent) == [] and any("withdrawn" in m["text"] for t, m in sent if t == "br/status")


def test_newer_plan_cancels_old_request():
    ex, sent, _ = make(approve="close")
    ex.execute(chosen(CLOSE_G3))
    old = approvals(sent)[0]["approval_id"]
    ex.execute(chosen({"type": "gate", "link": "G2", "state": "closed"}))
    assert not ex.decide(old, True) and devices(sent) == []
    assert len(ex.pending) == 1


def test_announcement_is_translated():
    ex, sent, _ = make(translate=lambda en: {"en": en, "ta": "TA", "hi": "HI"})
    ex.execute(chosen({"type": "announce", "zone": "B", "langs": ["en"], "text": "Please move left."}))
    (ann,) = [m for t, m in sent if t == "br/announce"]
    assert ann.texts == {"en": "Please move left.", "ta": "TA", "hi": "HI"}
