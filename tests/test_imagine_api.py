
from imagine.fake_imagine import apply_plan_to_venue
from common.contracts import Plan
from imagine.sim import simulate

def test_gate_plan_closes_gate_on_copy_only():
    from imagine.fake_imagine import venue

    original_state = next(
        link.state for link in venue.links if link.id == "G3"
    )

    plan = Plan(
        plan_id="close-g3",
        strategy="Close gate G3",
        actions=[
            {
                "type": "gate",
                "link": "G3",
                "state": "closed",
            }
        ],
        why="Test closing gate G3",
    )

    planned_venue = apply_plan_to_venue(plan)

    planned_g3 = next(
        link for link in planned_venue.links if link.id == "G3"
    )
    original_g3 = next(
        link for link in venue.links if link.id == "G3"
    )

    assert planned_g3.state == "closed"
    assert original_g3.state == original_state


def test_gate_plan_rejects_unknown_link():
    import pytest
    from imagine.fake_imagine import apply_plan_to_venue

    plan = Plan(
        plan_id="invalid-gate",
        strategy="Close unknown gate",
        actions=[
            {
                "type": "gate",
                "link": "G999",
                "state": "closed",
            }
        ],
        why="Test invalid gate",
    )

    with pytest.raises(ValueError, match="Unknown gate link"):
        apply_plan_to_venue(plan)



def test_score_passes_hold_inflow_to_simulator(monkeypatch):
    from fastapi.testclient import TestClient
    from imagine import fake_imagine
    from imagine.sim import simulate

    captured = {}

    def fake_make_forecast(**kwargs):
        captured.update(kwargs)
        return simulate(
            kwargs.get("active_venue") or fake_imagine.venue,
            kwargs.get("initial_counts") or {
                "A": 0, "B": 0, "C": 0, "D": 0
            },
            {"A": 0, "B": 0, "C": 0, "D": 0},
            fake_imagine.assumptions,
            seed=42,
            hold_inflow_min=kwargs.get("hold_inflow_min"),
        )

    monkeypatch.setattr(
        fake_imagine,
        "make_forecast",
        fake_make_forecast,
    )

    plan = {
        "plan_id": "hold-main-entry",
        "strategy": "Temporarily hold the main entrance",
        "actions": [
            {
                "type": "hold_inflow",
                "entry": "Main Entrance",
                "minutes": 5,
            }
        ],
        "why": "Temporarily meter entry to reduce incoming crowd pressure.",
    }

    with TestClient(fake_imagine.app) as client:
        response = client.post("/score", json={"plan": plan})

    assert response.status_code == 200
    assert captured["hold_inflow_min"] == {"A": 5}
