"""Backend replay: what a newly connected dashboard gets."""
from backend.replay import Replay


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def topics(snap):
    return [(i["topic"], i["data"].get("id")) for i in snap]


def test_latest_keyed_and_history():
    r = Replay(Clock())
    r.record("br/plan", {"id": "old"})
    r.record("br/plan", {"id": "new"})
    r.record("br/status", {"source": "watchdog", "id": "w1"})
    r.record("br/status", {"source": "planner", "id": "p1"})
    r.record("br/status", {"source": "watchdog", "id": "w2"})
    for i in range(60):
        r.record("br/report", {"id": i})
    snap = r.snapshot()
    assert ("br/plan", "new") in topics(snap) and ("br/plan", "old") not in topics(snap)
    status = [i["data"]["id"] for i in snap if i["topic"] == "br/status"]
    assert status == ["p1", "w2"]                                  # latest per source
    reports = [i["data"]["id"] for i in snap if i["topic"] == "br/report"]
    assert reports == list(range(10, 60))                          # last 50, oldest first
    assert all(i["replay"] is True for i in snap)


def test_officers_and_zones_latest_each():
    r = Replay(Clock())
    r.record("br/officer", {"officer_id": "O7", "status": "assigned"})
    r.record("br/officer", {"officer_id": "O8", "status": "assigned"})
    r.record("br/officer", {"officer_id": "O7", "status": "arrived"})
    r.record("br/zone_state", {"zone": "B", "density_ppm2": 4.1})
    officers = [(i["data"]["officer_id"], i["data"]["status"]) for i in r.snapshot() if i["topic"] == "br/officer"]
    assert officers == [("O8", "assigned"), ("O7", "arrived")]


def test_answered_approval_not_replayed():
    r = Replay(Clock())
    r.record("br/approval", {"approval_id": "a1", "expires_in_s": 120})
    r.record("br/approval", {"approval_id": "a2", "expires_in_s": 120})
    r.record("br/approve", {"approval_id": "a1", "approved": True})
    ids = [i["data"]["approval_id"] for i in r.snapshot() if i["topic"] == "br/approval"]
    assert ids == ["a2"]


def test_expired_approval_not_replayed():
    clock = Clock()
    r = Replay(clock)
    r.record("br/approval", {"approval_id": "a1", "expires_in_s": 120})
    clock.now = 121
    assert not [i for i in r.snapshot() if i["topic"] == "br/approval"]


def test_new_plan_clears_pending_approvals():
    r = Replay(Clock())
    r.record("br/approval", {"approval_id": "a1", "expires_in_s": 120})
    r.record("br/plan", {"id": "P2"})
    assert not [i for i in r.snapshot() if i["topic"] == "br/approval"]


def test_unlisted_topics_and_non_json_ignored():
    r = Replay(Clock())
    r.record("br/device/gate-3", {"value": "stop"})
    r.record("br/report_raw", {"text": "x"})
    r.record("br/plan", "not json")
    assert r.snapshot() == []
