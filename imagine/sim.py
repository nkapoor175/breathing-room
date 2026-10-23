
"""Monte Carlo crowd simulator for Breathing Room.

This is a simplified planning model, not a validated real-world crowd-safety model.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from common.contracts import Forecast, Venue, ZoneForecast
from common.timeutil import now_iso


IMAGINE_DIR = Path(__file__).resolve().parent
DEFAULT_ASSUMPTIONS = IMAGINE_DIR / "assumptions.json"
DEFAULT_VENUE = IMAGINE_DIR / "venue.json"


def load_assumptions(path: str | Path = DEFAULT_ASSUMPTIONS) -> dict[str, Any]:
    """Load and validate the basic simulation settings."""
    with open(path, encoding="utf-8") as f:
        assumptions = json.load(f)

    required = (
        "dt_s", "horizon_min", "runs", "v_free_mps", "rho_jam",
        "rho_physical_max", "arrival_multiplier_sigma", "danger_density",
        "caution_density",
    )
    missing = [key for key in required if key not in assumptions]
    if missing:
        raise ValueError(f"Missing simulation assumptions: {', '.join(missing)}")

    if assumptions["dt_s"] <= 0 or assumptions["horizon_min"] <= 0:
        raise ValueError("dt_s and horizon_min must be positive")
    if assumptions["runs"] < 1:
        raise ValueError("runs must be at least 1")
    if assumptions["rho_jam"] <= 0:
        raise ValueError("rho_jam must be positive")
    if assumptions["rho_physical_max"] < assumptions["danger_density"]:
        raise ValueError("rho_physical_max must be at least danger_density")

    return assumptions


def load_venue(path: str | Path = DEFAULT_VENUE) -> Venue:
    """Load the venue and validate it against the team's frozen contract."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    venue = Venue.model_validate(data)

    if not venue.zones:
        raise ValueError("Venue must contain at least one zone")

    zone_ids = {zone.id for zone in venue.zones}
    for zone in venue.zones:
        if zone.area_m2 <= 0:
            raise ValueError(f"Zone {zone.id} must have positive area")

    for link in venue.links:
        if link.from_zone != "outside" and link.from_zone not in zone_ids:
            raise ValueError(f"Link {link.id} has unknown source zone {link.from_zone}")
        if link.to_zone != "outside" and link.to_zone not in zone_ids:
            raise ValueError(f"Link {link.id} has unknown target zone {link.to_zone}")
        if link.width_m <= 0:
            raise ValueError(f"Link {link.id} must have positive width")

    for entry in venue.entries:
        if entry.zone not in zone_ids:
            raise ValueError(f"Entry refers to unknown zone {entry.zone}")

    return venue


def simulate(
    venue: Venue,
    initial_counts: dict[str, int],
    arrival_rates_per_min: dict[str, float],
    assumptions: dict[str, Any] | None = None,
    *,
    seed: int = 42,
) -> Forecast:
    """Simulate crowd futures and summarize density risk per zone.

    Args:
        venue: Validated venue.
        initial_counts: Current people count for each zone.
        arrival_rates_per_min: Mean incoming people/minute for each entry zone.
        assumptions: Settings loaded from assumptions.json.
        seed: Random seed. Reusing it enables common random numbers in comparisons.

    Simplifying assumptions:
        - Each link is a directed connection.
        - Zone density is people / walkable area.
        - Speed decreases linearly to zero at rho_jam.
        - Link capacity is approximated from width and speed.
        - Arrivals are Poisson-distributed with a run-level multiplier.
    """
    cfg = assumptions or load_assumptions()
    rng = np.random.default_rng(seed)

    zone_ids = [z.id for z in venue.zones]
    zone_index = {zone_id: i for i, zone_id in enumerate(zone_ids)}
    n_zones = len(zone_ids)

    unknown_counts = set(initial_counts) - set(zone_ids)
    unknown_arrivals = set(arrival_rates_per_min) - set(zone_ids)
    if unknown_counts:
        raise ValueError(f"Unknown zones in initial_counts: {sorted(unknown_counts)}")
    if unknown_arrivals:
        raise ValueError(f"Unknown zones in arrival rates: {sorted(unknown_arrivals)}")
    if any(not isinstance(v, int) or v < 0 for v in initial_counts.values()):
        raise ValueError("Initial counts must be non-negative integers")
    if any(not np.isfinite(v) or v < 0 for v in arrival_rates_per_min.values()):
        raise ValueError("Arrival rates must be finite and non-negative")

    areas = np.array([z.area_m2 for z in venue.zones], dtype=float)
    initial = np.array([initial_counts.get(z, 0) for z in zone_ids], dtype=float)

    dt_s = float(cfg["dt_s"])
    steps = int(round(float(cfg["horizon_min"]) * 60 / dt_s))
    runs = int(cfg["runs"])
    rho_jam = float(cfg["rho_jam"])
    rho_max = float(cfg["rho_physical_max"])
    v_free = float(cfg["v_free_mps"])
    danger = float(cfg["danger_density"])
    sigma = float(cfg["arrival_multiplier_sigma"])

    if steps < 1:
        raise ValueError("Horizon must contain at least one simulation step")

    # Keep only links between zones for internal movement. Entry and exit
    # links are represented through arrival rates and exits from outside links.
    internal_links = [
        link for link in venue.links
        if link.from_zone in zone_index and link.to_zone in zone_index
    ]
    from_idx = np.array([zone_index[l.from_zone] for l in internal_links], dtype=int)
    to_idx = np.array([zone_index[l.to_zone] for l in internal_links], dtype=int)
    widths = np.array([l.width_m for l in internal_links], dtype=float)
    open_mask = np.array([l.state == "open" for l in internal_links], dtype=bool)

    # Entry arrival multipliers are fixed per run for correlated uncertainty.
    arrival_zones = np.array(
        [zone_index[z] for z in arrival_rates_per_min], dtype=int
    )
    arrival_means = np.array(
        [arrival_rates_per_min[z] for z in arrival_rates_per_min], dtype=float
    )
    if sigma > 0:
        multipliers = rng.lognormal(
            mean=-(sigma**2) / 2, sigma=sigma, size=runs
        )
    else:
        multipliers = np.ones(runs)

    # Use a consistent random arrival schedule for all runs.
    counts = np.repeat(initial[None, :], runs, axis=0)
    density_history = np.empty((runs, steps + 1, n_zones), dtype=np.float32)
    density_history[:, 0, :] = counts / areas

    for step in range(steps):
        density = counts / areas
        speed = v_free * np.maximum(0.0, 1.0 - density / rho_jam)

        # Demand from each source zone, bounded by available people.
        if len(internal_links):
            demand_rate = (
                density[:, from_idx]
                * speed[:, from_idx]
                * widths[None, :]
                * open_mask[None, :]
            )
            desired = np.minimum(
                counts[:, from_idx],
                np.maximum(0.0, demand_rate * dt_s),
            )

            # Approximate downstream supply: don't send more people than
            # the receiving zone can accommodate under the physical cap.
            receiving_room = np.maximum(
                0.0,
                (rho_max * areas[to_idx][None, :] - counts[:, to_idx]),
            )
            desired = np.minimum(desired, receiving_room)

            # Prevent a source from sending more people across its links
            # than it currently contains.
            total_out = np.zeros_like(counts)
            np.add.at(
                total_out,
                (np.arange(runs)[:, None], np.broadcast_to(from_idx, (runs, len(from_idx)))),
                desired,
            )
            scale = np.ones_like(counts)
            over = total_out > counts
            scale[over] = counts[over] / total_out[over]
            desired *= scale[:, from_idx]

            delta = np.zeros_like(counts)
            for j in range(len(internal_links)):
                flow = desired[:, j]
                delta[:, from_idx[j]] -= flow
                delta[:, to_idx[j]] += flow
            counts += delta

        # Incoming people arrive at the configured entry zones.
        if len(arrival_zones):
            means_per_step = arrival_means * dt_s / 60.0
            arrivals = rng.poisson(
                means_per_step[None, :] * multipliers[:, None]
            )
            for j, zone_idx in enumerate(arrival_zones):
                counts[:, zone_idx] += arrivals[:, j]

        # Zone occupancy is never negative; physical density is capped.
        counts = np.maximum(counts, 0.0)
        counts = np.minimum(counts, rho_max * areas[None, :])
        density_history[:, step + 1, :] = counts / areas

    # Danger is an event over the full horizon, not just at the final step.
    crossed = density_history >= danger
    danger_runs = crossed.any(axis=1)
    p_danger = danger_runs.mean(axis=0)

    # First crossing time for runs that crossed danger.
    step_times_min = np.arange(steps + 1) * dt_s / 60.0
    forecasts: list[ZoneForecast] = []
    for i, zone_id in enumerate(zone_ids):
        zone_history = density_history[:, :, i]
        p50_density = float(np.median(zone_history[:, -1]))
        p90_density = float(np.percentile(zone_history[:, -1], 90))

        crossing_runs = np.flatnonzero(danger_runs[:, i])
        minutes_to_danger = None
        if len(crossing_runs) >= 0.05 * runs:
            first_times = []
            for run_idx in crossing_runs:
                first_idx = np.flatnonzero(crossed[run_idx, :, i])[0]
                first_times.append(step_times_min[first_idx])
            minutes_to_danger = float(np.median(first_times))

        forecasts.append(
            ZoneForecast(
                zone=zone_id,
                p50_density=round(p50_density, 3),
                p90_density=round(p90_density, 3),
                p_danger=round(float(p_danger[i]), 4),
                minutes_to_danger=(
                    round(minutes_to_danger, 2)
                    if minutes_to_danger is not None else None
                ),
            )
        )

    return Forecast(
        t=now_iso(),
        horizon_min=int(cfg["horizon_min"]),
        runs=runs,
        zones=forecasts,
    )
