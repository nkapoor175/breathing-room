
from imagine.fake_imagine import apply_plan_to_venue
from common.contracts import Plan


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
