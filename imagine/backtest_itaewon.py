
"""Simulated reconstruction of the Itaewon crowd disaster.

This is a simplified scenario study, not a validated historical prediction.
"""
from __future__ import annotations

import json
from pathlib import Path

from common.contracts import Entry, Link, Venue, Zone
from imagine.sim import load_assumptions, simulate

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "docs"

# Approximate alley dimensions from the project brief:
# 45 m x 3.6 m ~= 162 m².
# These are scenario assumptions, not a surveyed site plan.
ALLEY_AREA_M2 = 45.0 * 3.6

ALERT_DANGER_PROBABILITY = 0.30
ALERT_MINUTES_TO_DANGER = 15.0

def make_itaewon_venue() -> Venue:
    """Build a simplified three-zone alley reconstruction."""
    zones = [
        Zone(
            id="A",
            name="Alley approach",
            area_m2=ALLEY_AREA_M2,
            polygon_px=[],
            polygon_map=[],
            capacity_note="Approximate reconstruction; not surveyed.",
        ),
        Zone(
            id="B",
            name="Narrow alley",
            area_m2=ALLEY_AREA_M2,
            polygon_px=[],
            polygon_map=[],
            capacity_note="Approximate reconstruction; not surveyed.",
        ),
        Zone(
            id="C",
            name="Alley exit",
            area_m2=ALLEY_AREA_M2,
            polygon_px=[],
            polygon_map=[],
            capacity_note="Approximate reconstruction; not surveyed.",
        ),
    ]

    links = [
        Link(
            id="L1",
            **{"from": "outside", "to": "A"},
            width_m=3.6,
            kind="gate",
            state="open",
        ),
        Link(
            id="L2",
            **{"from": "A", "to": "B"},
            width_m=3.6,
            kind="corridor",
            state="open",
        ),
        Link(
            id="L3",
            **{"from": "B", "to": "C"},
            width_m=3.6,
            kind="corridor",
            state="open",
        ),
        Link(
            id="L4",
            **{"from": "C", "to": "outside"},
            width_m=3.6,
            kind="gate",
            state="open",
        ),
    ]

    return Venue(
        venue_id="itaewon-sim-reconstruction",
        name="Itaewon Simulated Reconstruction",
        zones=zones,
        links=links,
        entries=[Entry(zone="A", name="Alley approach entry")],
        pa_zones=["A", "B", "C"],
        officers_total=0,
    )


def run_scenario(exit_closed: bool) -> dict:
    """Run one evening scenario; results are simulated, not historical facts."""
    venue = make_itaewon_venue()

    if exit_closed:
        for link in venue.links:
            if link.id == "L4":
                link.state = "closed"

    assumptions = load_assumptions()
    start_minute = 17 * 60
    end_minute = 23 * 60
    horizon_min = int(assumptions["horizon_min"])

    starting_counts = {"A": 100, "B": 150, "C": 100}
    counts = starting_counts.copy()
    arrival_rate = 20.0
    timeline = []
    first_alert_minute = None
    step_number = 0

    areas = {zone.id: zone.area_m2 for zone in venue.zones}

    for minute in range(start_minute, end_minute, horizon_min):
        forecast = simulate(
            venue,
            initial_counts=counts,
            arrival_rates_per_min={"A": arrival_rate},
            assumptions=assumptions,
            seed=42 + step_number,
        )

        worst_zone = max(
            forecast.zones,
            key=lambda zone: zone.p_danger,
        )

        alert = (
            worst_zone.p_danger >= ALERT_DANGER_PROBABILITY
            and worst_zone.minutes_to_danger is not None
            and worst_zone.minutes_to_danger < ALERT_MINUTES_TO_DANGER
        )

        if alert and first_alert_minute is None:
            first_alert_minute = minute

        timeline.append({
            "time": f"{minute // 60:02d}:{minute % 60:02d}",
            "worst_zone": worst_zone.zone,
            "p_danger": worst_zone.p_danger,
            "minutes_to_danger": worst_zone.minutes_to_danger,
            "alert": alert,
            "zone_forecasts": [
                zone.model_dump() for zone in forecast.zones
            ],
        })

        counts = {
            zone.zone: max(
                0,
                round(zone.p50_density * areas[zone.zone]),
            )
            for zone in forecast.zones
        }
        step_number += 1

    return {
        "exit_closed": exit_closed,
        "starting_counts": starting_counts,
        "arrival_rate_per_min": arrival_rate,
        "first_simulated_alert_time": (
            f"{first_alert_minute // 60:02d}:{first_alert_minute % 60:02d}"
            if first_alert_minute is not None else None
        ),
        "timeline": timeline,
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    result = {
        "label": "simulated reconstruction",
        "historical_reference_times": {
            "first_emergency_call": "18:34",
            "approximate_crush_time": "22:15",
        },
        "scenarios": [
            run_scenario(exit_closed=False),
            run_scenario(exit_closed=True),
        ],
        "note": (
            "Both scenarios are simplified simulations, not validated "
            "historical predictions. Closing the exit is a diagnostic "
            "assumption, not a claim about actual historical gate status."
        ),
    }

    output_path = OUTPUT_DIR / "itaewon_backtest.json"
    output_path.write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )

    for scenario in result["scenarios"]:
        label = "exit closed" if scenario["exit_closed"] else "exit open"
        print(
            f"{label}: first simulated alert = "
            f"{scenario['first_simulated_alert_time']}"
        )

    print(f"Saved comparison to: {output_path}")


if __name__ == "__main__":
    main()
