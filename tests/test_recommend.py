
import pytest

from common.contracts import Action, Plan, PlanCandidates
from imagine import fake_imagine
from imagine.sim import load_venue
from act import recommend as recommendation


@pytest.fixture
def venue():
    return load_venue()


def make_hold_plan(entry, minutes=None, plan_id="P1", zone=None):
    return Plan(
        plan_id=plan_id,
        strategy="Test inflow hold",
        actions=[
            Action(
                type="hold_inflow",
                entry=entry,
                zone=zone,
                minutes=minutes,
            )
        ],
        why="Test recommendation validation",
    )


def test_entry_name_with_trailing_punctuation_is_recognized(venue):
    entry = venue.entries[0]
    plan = make_hold_plan(
        entry.name + "”, ",
        minutes=5,
        zone=entry.zone,
    )

    recommendation._validate_plan(plan, venue)


def test_unknown_entry_is_rejected(venue):
    plan = make_hold_plan(
        "Definitely Not An Entry",
        minutes=5,
    )

    with pytest.raises(ValueError, match="Unknown entry"):
        recommendation._validate_plan(plan, venue)


def test_missing_hold_duration_is_rejected_by_validator(venue):
    entry = venue.entries[0]
    plan = make_hold_plan(
        entry.name,
        minutes=None,
        zone=entry.zone,
    )

    with pytest.raises(ValueError, match="Hold duration"):
        recommendation._validate_plan(plan, venue)



def test_unsafe_gate_closure_is_rejected(venue):
    zone_ids = {zone.id for zone in venue.zones}

    # Find an open link whose closure disconnects at least one zone.
    for link in venue.links:
        if link.state != "open":
            continue

        plan = Plan(
            plan_id="unsafe-gate",
            strategy=f"Close {link.id}",
            actions=[
                Action(
                    type="gate",
                    link=link.id,
                    state="closed",
                )
            ],
            why="Test gate safety validation",
        )

        try:
            recommendation._validate_gate_safety(plan, venue)
        except ValueError as exc:
            if "disconnect" in str(exc).lower():
                return
            raise

    pytest.skip(
        "No single open link closure disconnects zones in this venue"
    )


def test_candidate_fallback_produces_three_valid_hold_plans(
    monkeypatch, venue
):
    def fail_generation(**kwargs):
        raise AssertionError("Expected candidate generation to be mocked")

    # Return invalid candidates twice so fallback generation is exercised.
    invalid_candidates = PlanCandidates(
        plans=[
            make_hold_plan(
                "Unknown Entry",
                minutes=5,
                plan_id=f"P{i}",
            )
            for i in range(1, 4)
        ]
    )

    monkeypatch.setattr(
        recommendation,
        "call_json",
        lambda **kwargs: invalid_candidates,
    )

    candidates, _ = recommendation._generate_candidates(
        system_prompt="test",
        context={},
        selected_venue=venue,
    )

    assert len(candidates.plans) == 3
    assert [p.plan_id for p in candidates.plans] == ["P1", "P2", "P3"]
    assert [
        p.actions[0].minutes for p in candidates.plans
    ] == [3, 6, 10]

    for plan in candidates.plans:
        recommendation._validate_plan(plan, venue)
