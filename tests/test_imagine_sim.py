
import pytest

from imagine.sim import load_assumptions, load_venue, simulate


def test_venue_and_assumptions_load():
    venue = load_venue()
    assumptions = load_assumptions()

    assert len(venue.zones) == 4
    assert assumptions["horizon_min"] == 15
    assert assumptions["runs"] == 1000


def test_forecast_matches_contract():
    venue = load_venue()
    assumptions = load_assumptions()

    forecast = simulate(
        venue,
        initial_counts={"A": 40, "B": 100, "C": 250, "D": 10},
        arrival_rates_per_min={"A": 20},
        assumptions=assumptions,
        seed=7,
    )

    assert forecast.runs == 1000
    assert forecast.horizon_min == 15
    assert {z.zone for z in forecast.zones} == {"A", "B", "C", "D"}

    for zone in forecast.zones:
        assert 0 <= zone.p_danger <= 1
        assert zone.p50_density >= 0
        assert zone.p90_density >= zone.p50_density


def test_simulation_is_reproducible_with_same_seed():
    venue = load_venue()
    assumptions = load_assumptions()
    args = {
        "initial_counts": {"A": 40, "B": 100, "C": 250, "D": 10},
        "arrival_rates_per_min": {"A": 20},
        "assumptions": assumptions,
    }

    first = simulate(venue, **args, seed=123)
    second = simulate(venue, **args, seed=123)

    assert [z.model_dump() for z in first.zones] == [
        z.model_dump() for z in second.zones
    ]


def test_unknown_zone_is_rejected():
    venue = load_venue()

    with pytest.raises(ValueError, match="Unknown zones"):
        simulate(
            venue,
            initial_counts={"UNKNOWN": 10},
            arrival_rates_per_min={},
        )
