
"""Monte Carlo crowd simulator for Breathing Room.

Simplified planning model; not a validated real-world crowd-safety model.
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
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)

    required = (
        "dt_s", "horizon_min", "runs", "v_free_mps", "rho_jam",
        "rho_physical_max", "arrival_multiplier_sigma", "danger_density",
        "caution_density",
    )
    missing = [key for key in required if key not in cfg]
    if missing:
        raise ValueError(f"Missing simulation assumptions: {', '.join(missing)}")
    if cfg["dt_s"] <= 0 or cfg["horizon_min"] <= 0:
        raise ValueError("dt_s and horizon_min must be positive")
    if cfg["runs"] < 1:
        raise ValueError("runs must be at least 1")
    if cfg["rho_jam"] <= 0:
        raise ValueError("rho_jam must be positive")
    if cfg["rho_physical_max"] < cfg["danger_density"]:
        raise ValueError("rho_physical_max must be at least danger_density")
    if cfg["arrival_multiplier_sigma"] < 0:
        raise ValueError("arrival_multiplier_sigma cannot be negative")
    return cfg


def load_venue(path: str | Path = DEFAULT_VENUE) -> Venue:
    with open(path, encoding="utf-8") as f:
        venue = Venue.model_validate(json.load(f))

    if not venue.zones:
        raise ValueError("Venue must contain at least one zone")

    zone_ids = {z.id for z in venue.zones}
    for z in venue.zones:
        if z.area_m2 <= 0:
            raise ValueError(f"Zone {z.id} must have positive area")

    link_ids = set()
    for link in venue.links:
        if link.id in link_ids:
            raise ValueError(f"Duplicate link id: {link.id}")
        link_ids.add(link.id)
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
    """Simulate Monte Carlo futures from explicit counts and arrival rates.

    Arrival rates are mean people/minute by entry zone. Links are directed.
    Outside-to-zone links are potential entry routes; zone-to-outside links
    are exits. Arrivals are Poisson-distributed with a run-level multiplier.
    """
    cfg = assumptions if assumptions is not None else load_assumptions()
    rng = np.random.default_rng(seed)

    zone_ids = [z.id for z in venue.zones]
    zone_index = {zone_id: i for i, zone_id in enumerate(zone_ids)}
    n_zones = len(zone_ids)
    known_zones = set(zone_ids)

    if set(initial_counts) - known_zones:
        raise ValueError(f"Unknown zones in initial_counts: {sorted(set(initial_counts) - known_zones)}")
    if set(arrival_rates_per_min) - known_zones:
        raise ValueError(f"Unknown zones in arrival rates: {sorted(set(arrival_rates_per_min) - known_zones)}")
    if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in initial_counts.values()):
        raise ValueError("Initial counts must be non-negative integers")
    if any(not np.isfinite(v) or v < 0 for v in arrival_rates_per_min.values()):
        raise ValueError("Arrival rates must be finite and non-negative")

    areas = np.array([z.area_m2 for z in venue.zones], dtype=float)
    initial = np.array([initial_counts.get(z, 0) for z in zone_ids], dtype=float)

    dt_s = float(cfg["dt_s"])
    horizon_min = float(cfg["horizon_min"])
    steps_float = horizon_min * 60 / dt_s
    steps = int(round(steps_float))
    if steps < 1 or not np.isclose(steps, steps_float):
        raise ValueError("horizon_min must be an exact multiple of dt_s")
    runs = int(cfg["runs"])
    rho_jam = float(cfg["rho_jam"])
    rho_max = float(cfg["rho_physical_max"])
    v_free = float(cfg["v_free_mps"])
    danger = float(cfg["danger_density"])
    sigma = float(cfg["arrival_multiplier_sigma"])

    max_counts = rho_max * areas
    if np.any(initial > max_counts):
        raise ValueError("Initial counts exceed a zone's physical density cap")

    # Classify directed links. Every flow is computed from the same
    # beginning-of-step occupancy snapshot.
    internal = []
    exit_links = []
    for link in venue.links:
        if link.state == "closed":
            continue
        if link.from_zone in zone_index and link.to_zone in zone_index:
            internal.append(link)
        elif link.from_zone in zone_index and link.to_zone == "outside":
            exit_links.append(link)

    # Entries are driven by the supplied arrival rates, but an outside-to-zone
    # link must exist and be open for that entry zone to receive arrivals.
    open_entry_zones = {
        link.to_zone for link in venue.links
        if link.state == "open"
        and link.from_zone == "outside"
        and link.to_zone in zone_index
    }
    arrival_items = [
        (zone_index[z], float(rate))
        for z, rate in arrival_rates_per_min.items()
        if rate > 0 and z in open_entry_zones
    ]

    if sigma > 0:
        multipliers = rng.lognormal(
            mean=-(sigma**2) / 2, sigma=sigma, size=runs
        )
    else:
        multipliers = np.ones(runs)

    counts = np.repeat(initial[None, :], runs, axis=0)
    density_history = np.empty((runs, steps + 1, n_zones), dtype=np.float32)
    density_history[:, 0, :] = counts / areas

    for step in range(steps):
        # All demands and supplies use the same snapshot.
        density = counts / areas
        speed = v_free * np.maximum(0.0, 1.0 - density / rho_jam)
        delta = np.zeros_like(counts)

        # Desired internal link flows (people per step).
        desired = []
        for link in internal:
            src = zone_index[link.from_zone]
            dst = zone_index[link.to_zone]
            rate = density[:, src] * speed[:, src] * link.width_m
            desired.append(np.minimum(counts[:, src], np.maximum(0.0, rate * dt_s)))

        # Desired exits use the same width/speed flow approximation.
        for link in exit_links:
            src = zone_index[link.from_zone]
            rate = density[:, src] * speed[:, src] * link.width_m
            desired.append(np.minimum(counts[:, src], np.maximum(0.0, rate * dt_s)))

        # Limit each source's combined outgoing flow to its snapshot count.
        all_links = internal + exit_links
        if desired:
            desired_array = np.stack(desired, axis=1)
            outgoing = np.zeros_like(counts)
            for j, link in enumerate(all_links):
                outgoing[:, zone_index[link.from_zone]] += desired_array[:, j]

            source_scale = np.ones_like(counts)
            mask = outgoing > counts
            source_scale[mask] = counts[mask] / outgoing[mask]
            for j, link in enumerate(all_links):
                src = zone_index[link.from_zone]
                desired_array[:, j] *= source_scale[:, src]

            # Limit incoming flow into each destination by its snapshot room.
            incoming = np.zeros_like(counts)
            for j, link in enumerate(internal):
                incoming[:, zone_index[link.to_zone]] += desired_array[:, j]

            room = np.maximum(0.0, max_counts[None, :] - counts)
            destination_scale = np.ones_like(counts)
            too_much = incoming > room
            destination_scale[too_much] = room[too_much] / incoming[too_much]
            for j, link in enumerate(internal):
                dst = zone_index[link.to_zone]
                flow = desired_array[:, j] * destination_scale[:, dst]
                src = zone_index[link.from_zone]
                delta[:, src] -= flow
                delta[:, dst] += flow

            # Exits remove people from the source zone.
            for j, link in enumerate(exit_links, start=len(internal)):
                src = zone_index[link.from_zone]
                delta[:, src] -= desired_array[:, j]

        # Apply movement once, after every link has been calculated.
        counts += delta

        # Poisson arrivals with a fixed run-level multiplier. Excess arrivals
        # are not silently discarded: they are admitted only up to available
        # physical room. (A future version can track the outside queue.)
        for zone_idx, rate_per_min in arrival_items:
            arrivals = rng.poisson(rate_per_min * dt_s / 60.0 * multipliers)
            room = np.maximum(0.0, max_counts[zone_idx] - counts[:, zone_idx])
            counts[:, zone_idx] += np.minimum(arrivals, room)

        counts = np.maximum(counts, 0.0)
        density_history[:, step + 1, :] = counts / areas

    crossed = density_history >= danger
    danger_runs = crossed.any(axis=1)
    p_danger = danger_runs.mean(axis=0)
    step_times_min = np.arange(steps + 1) * dt_s / 60.0

    forecasts = []
    for i, zone_id in enumerate(zone_ids):
        zone_history = density_history[:, :, i]
        p50 = float(np.median(zone_history[:, -1]))
        p90 = float(np.percentile(zone_history[:, -1], 90))
        crossing_runs = np.flatnonzero(danger_runs[:, i])
        minutes_to_danger = None

        if len(crossing_runs) >= 0.05 * runs:
            first_times = [
                step_times_min[np.flatnonzero(crossed[r, :, i])[0]]
                for r in crossing_runs
            ]
            minutes_to_danger = float(np.median(first_times))

        forecasts.append(
            ZoneForecast(
                zone=zone_id,
                p50_density=round(p50, 3),
                p90_density=round(p90, 3),
                p_danger=round(float(p_danger[i]), 4),
                minutes_to_danger=(
                    round(minutes_to_danger, 2)
                    if minutes_to_danger is not None else None
                ),
            )
        )

    return Forecast(
        t=now_iso(),
        horizon_min=int(horizon_min),
        runs=runs,
        zones=forecasts,
    )
