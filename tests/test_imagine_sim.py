
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



def test_closed_gate_stops_internal_movement():
    venue = load_venue()
    assumptions = load_assumptions()

    # Find the link between the entrance and corridor.
    link = next(link for link in venue.links if link.id == "G2")
    link.state = "closed"

    forecast = simulate(
        venue,
        initial_counts={"A": 100, "B": 0, "C": 0, "D": 0},
        arrival_rates_per_min={"A": 0, "B": 0, "C": 0, "D": 0},
        assumptions=assumptions,
        seed=42,
    )

    zone_b = next(zone for zone in forecast.zones if zone.zone == "B")
    assert zone_b.p50_density == 0


def test_empty_venue_stays_empty_without_arrivals():
    venue = load_venue()

    forecast = simulate(
        venue,
        initial_counts={"A": 0, "B": 0, "C": 0, "D": 0},
        arrival_rates_per_min={"A": 0, "B": 0, "C": 0, "D": 0},
        seed=42,
    )

    for zone in forecast.zones:
        assert zone.p50_density == 0
        assert zone.p90_density == 0
        assert zone.p_danger == 0



def test_open_exit_reduces_crowd_count():
    venue = load_venue()
    assumptions = load_assumptions()

    # Start with people in zone D, which connects to the outside
    # through exit G5.
    forecast = simulate(
        venue,
        initial_counts={"A": 0, "B": 0, "C": 0, "D": 80},
        arrival_rates_per_min={"A": 0, "B": 0, "C": 0, "D": 0},
        assumptions=assumptions,
        seed=42,
    )

    zone_d = next(zone for zone in forecast.zones if zone.zone == "D")

    # With an open exit and no arrivals, the final median density
    # should be below the starting density of 80 / 100 = 0.8.
    assert zone_d.p50_density < 0.8



def test_density_never_exceeds_physical_maximum():
    venue = load_venue()
    assumptions = load_assumptions()

    forecast = simulate(
        venue,
        initial_counts={"A": 100, "B": 0, "C": 0, "D": 0},
        arrival_rates_per_min={"A": 500, "B": 500, "C": 500, "D": 500},
        assumptions=assumptions,
        seed=42,
    )

    physical_max = assumptions["rho_physical_max"]

    for zone in forecast.zones:
        assert zone.p90_density <= physical_max
