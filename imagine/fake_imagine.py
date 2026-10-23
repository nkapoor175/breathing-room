
"""Simulator-backed Imagine API for Breathing Room.

Uses the demo venue and Monte Carlo simulator.
Crowd counts are updated from br/zone_state messages.
Arrival rates are explicit demo assumptions, not measured estimates.

Run: uvicorn imagine.fake_imagine:app --port 8002
"""

import asyncio
import json
import logging
import threading
from contextlib import asynccontextmanager
from copy import deepcopy
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from common.bus import make_client, publish
from common.contracts import (
    Action,
    Forecast,
    Plan,
    ScoreResult,
    Venue,
    ZoneState,
    ZoneForecast,
)
from common.timeutil import now_iso
from imagine.sim import load_assumptions, load_venue, simulate

logger = logging.getLogger(__name__)
IMAGINE_DIR = Path(__file__).resolve().parent

# Explicit demo assumption: average arrivals per minute into each zone.
# Only zones connected to an open outside-to-zone link can receive arrivals.
DEMO_ARRIVAL_RATES_PER_MIN = {"A": 12.0, "B": 0.0, "C": 0.0, "D": 0.0}

venue: Venue = load_venue()
assumptions = load_assumptions()

latest: Forecast | None = None
latest_states: dict[str, ZoneState] = {}
state_lock = threading.Lock()
mq = None


def on_mqtt(client, userdata, msg):
    """Keep the latest valid crowd state for each known zone."""
    if msg.topic != "br/zone_state":
        return

    try:
        state = ZoneState.model_validate_json(msg.payload)
    except (ValidationError, ValueError):
        logger.warning("Ignoring invalid ZoneState message")
        return

    known_zones = {z.id for z in venue.zones}
    if state.zone not in known_zones:
        logger.warning("Ignoring state for unknown zone %s", state.zone)
        return

    with state_lock:
        latest_states[state.zone] = state


def current_initial_counts() -> dict[str, int]:
    """Return current counts, using zero for zones with no received state."""
    with state_lock:
        states = dict(latest_states)

    return {
        zone.id: states[zone.id].count if zone.id in states else 0
        for zone in venue.zones
    }



def make_forecast(
    active_venue: Venue | None = None,
    initial_counts: dict[str, int] | None = None,
    arrival_rates: dict[str, float] | None = None,
    *,
    seed: int = 42,
    hold_inflow_min: dict[str, int] | None = None,
    announce_zones: list[str] | None = None,
) -> Forecast:

    """Generate a real forecast from the Monte Carlo simulator."""
    selected_venue = active_venue or venue
    counts = initial_counts if initial_counts is not None else current_initial_counts()
    rates = arrival_rates if arrival_rates is not None else DEMO_ARRIVAL_RATES_PER_MIN

    return simulate(
        selected_venue,
        counts,
        rates,
        assumptions,
        seed=seed,
        hold_inflow_min=hold_inflow_min,
        announce_zones=announce_zones,
    )


def score_forecast(plan_id: str, forecast: Forecast) -> ScoreResult:
    """Convert a forecast to the shared score contract."""
    max_danger = max((z.p_danger for z in forecast.zones), default=0.0)
    danger_times = [
        z.minutes_to_danger
        for z in forecast.zones
        if z.minutes_to_danger is not None
    ]

    return ScoreResult(
        plan_id=plan_id,
        max_p_danger=max_danger,
        min_minutes_to_danger=min(danger_times) if danger_times else None,
        zones=forecast.zones,
    )


def apply_plan_to_venue(plan: Plan) -> Venue:
    """Apply supported gate actions to a copy of the venue."""
    planned_venue = Venue.model_validate(venue.model_dump(by_alias=True))

    known_links = {link.id for link in planned_venue.links}
    for action in plan.actions:
        if action.type != "gate":
            continue

        if not action.link or action.link not in known_links:
            raise ValueError(f"Unknown gate link: {action.link}")
        if action.state not in ("open", "closed"):
            raise ValueError(f"Gate action for {action.link} must specify open or closed")

        link = next(link for link in planned_venue.links if link.id == action.link)
        link.state = action.state

    return planned_venue


def get_hold_durations(plan: Plan) -> dict[str, int]:
    """Map hold_inflow actions to their destination zones."""
    durations: dict[str, int] = {}

    entries = {entry.name: entry.zone for entry in venue.entries}

    for action in plan.actions:
        if action.type != "hold_inflow":
            continue

        if not action.entry or action.entry not in entries:
            raise ValueError(
                f"Unknown entry for hold_inflow action: {action.entry}"
            )

        if action.minutes is None or action.minutes < 0:
            raise ValueError(
                "hold_inflow action must specify non-negative minutes"
            )

        zone_id = entries[action.entry]
        durations[zone_id] = max(
            durations.get(zone_id, 0),
            action.minutes,
        )

    return durations


def get_announcement_zones(plan: Plan) -> list[str]:
    """Return the unique zones targeted by announce actions."""
    known_zones = {zone.id for zone in venue.zones}    
    zones = set()

    for action in plan.actions:
        if action.type != "announce":
            continue

        # Announcement actions target PA zones.
        if not action.zone:
            raise ValueError("announce action must specify a zone")

        if action.zone not in known_zones:
            raise ValueError(
                f"Unknown zone for announce action: {action.zone}"
            )

        zones.add(action.zone)

    return sorted(zones)


async def forecast_loop():
    global latest

    while True:
        try:
            forecast = make_forecast()
            latest = forecast

            if mq is not None:
                publish(mq, "br/forecast", forecast)
        except Exception:
            logger.exception("Could not generate or publish Imagine forecast")

        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mq

    mq = make_client("imagine-api")
    mq.on_message = on_mqtt
    mq.on_connect = lambda client, userdata, flags, reason_code, properties: (
        client.subscribe("br/zone_state")
    )
    mq.loop_start()

    task = asyncio.create_task(forecast_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        mq.loop_stop()
        mq.disconnect()
        mq = None


app = FastAPI(title="Breathing Room Imagine API", lifespan=lifespan)


@app.get("/venue/{venue_id}")
def get_venue(venue_id: str):
    if venue_id != venue.venue_id:
        raise HTTPException(status_code=404, detail="Venue not found")
    return venue


@app.get("/forecast/latest")
def forecast_latest():
    global latest

    if latest is None:
        latest = make_forecast()
    return latest


@app.post("/score/baseline")
def score_baseline(body: dict):
    counts = current_initial_counts()
    forecast = make_forecast(
        initial_counts=counts,
        seed=42,
    )
    return score_forecast("baseline", forecast)



@app.post("/score")
def score(body: dict):
    try:
        plan_data = body.get("plan", body)
        plan = Plan.model_validate(plan_data)
        planned_venue = apply_plan_to_venue(plan)
        hold_durations = get_hold_durations(plan)
        announce_zones = get_announcement_zones(plan)

        forecast = make_forecast(
            active_venue=planned_venue,
            initial_counts=current_initial_counts(),
            seed=42,
            hold_inflow_min=hold_durations,
            announce_zones=announce_zones,
        )
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return score_forecast(plan.plan_id, forecast)
