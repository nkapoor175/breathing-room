
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
import tempfile

from fastapi import FastAPI, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from common.gate_safety import validate_gate_safety
from pydantic import ValidationError
import base64
import os
from io import BytesIO

from PIL import Image, UnidentifiedImageError

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

MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}


def validate_uploaded_image(contents: bytes) -> tuple[str, str]:
    """Validate an uploaded image and return (data URL, image format)."""
    if not contents:
        raise ValueError("The uploaded image is empty.")

    if len(contents) > MAX_IMAGE_BYTES:
        raise ValueError("Image must be 10 MB or smaller.")

    try:
        with Image.open(BytesIO(contents)) as image:
            image_format = image.format
            image.verify()

        if image_format not in ALLOWED_IMAGE_FORMATS:
            raise ValueError("Upload a JPEG, PNG, or WEBP image.")

        with Image.open(BytesIO(contents)) as image:
            image = image.convert("RGB")
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            encoded = base64.b64encode(buffer.getvalue()).decode("ascii")

    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("The uploaded file is not a valid image.") from exc

    return f"data:image/png;base64,{encoded}", image_format

logger = logging.getLogger(__name__)
IMAGINE_DIR = Path(__file__).resolve().parent
ACTIVE_VENUE_PATH = IMAGINE_DIR / "active_venue.json"

# Explicit demo assumption: average arrivals per minute into each zone.
# Only zones connected to an open outside-to-zone link can receive arrivals.
DEMO_ARRIVAL_RATE_PER_MIN = 12.0

DEMO_VENUE_PATH = IMAGINE_DIR / "venue.json"

venue: Venue = (
    load_venue(ACTIVE_VENUE_PATH)
    if ACTIVE_VENUE_PATH.exists()
    else load_venue(DEMO_VENUE_PATH)
)
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
    rates = arrival_rates if arrival_rates is not None else {
        entry.zone: (
            DEMO_ARRIVAL_RATE_PER_MIN
            if entry.zone == selected_venue.entries[0].zone
            else 0.0
        )
        for entry in selected_venue.entries
    }

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


def apply_plan_to_venue(
    plan: Plan,
    active_venue: Venue | None = None,
) -> Venue:
    """Apply supported gate actions to a copy of the selected venue."""
    selected_venue = active_venue or venue
    planned_venue = Venue.model_validate(
        selected_venue.model_dump(by_alias=True)
    )
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



def validate_generated_venue(generated_venue: Venue) -> None:
    """Reject venue twins with invalid geometry or zone references."""
    zones = generated_venue.zones
    zone_ids = [zone.id for zone in zones]
    known_zone_ids = set(zone_ids)

    if not zones:
        raise ValueError("Generated venue must contain at least one zone.")

    if len(zone_ids) != len(known_zone_ids):
        raise ValueError("Generated venue contains duplicate zone IDs.")

    for zone in zones:
        if zone.area_m2 <= 0:
            raise ValueError(
                f"Zone {zone.id} must have a positive area."
            )

        for polygon_name in ("polygon_px", "polygon_map"):
            polygon = getattr(zone, polygon_name)
            if len(polygon) < 3:
                raise ValueError(
                    f"Zone {zone.id} {polygon_name} must contain at least 3 points."
                )

            if any(
                len(point) != 2
                or not all(
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    for value in point
                )
                for point in polygon
            ):
                raise ValueError(
                    f"Zone {zone.id} {polygon_name} must contain 2D numeric points."
                )

    link_ids = [link.id for link in generated_venue.links]
    if len(link_ids) != len(set(link_ids)):
        raise ValueError("Generated venue contains duplicate link IDs.")

    for link in generated_venue.links:
        if link.width_m <= 0:
            raise ValueError(
                f"Link {link.id} must have a positive width."
            )

        if link.from_zone != "outside" and link.from_zone not in known_zone_ids:
            raise ValueError(
                f"Generated link {link.id} has an unknown source zone."
            )

        if link.to_zone != "outside" and link.to_zone not in known_zone_ids:
            raise ValueError(
                f"Generated link {link.id} has an unknown destination zone."
            )

    for entry in generated_venue.entries:
        if entry.zone not in known_zone_ids:
            raise ValueError(
                f"Generated entry {entry.name} references an unknown zone."
            )

    if not set(generated_venue.pa_zones).issubset(known_zone_ids):
        raise ValueError(
            "Generated PA zones must refer to known zones."
        )


def save_active_venue(updated_venue: Venue) -> None:
    """Validate and atomically save the active venue."""
    validate_generated_venue(updated_venue)

    # Ensure every venue-related collection remains consistent.
    known_zone_ids = {zone.id for zone in updated_venue.zones}

    # Serialize using the shared contract's field names.
    venue_json = updated_venue.model_dump_json(by_alias=True, indent=2)

    # Write to a temporary file first, then replace the active file.
    ACTIVE_VENUE_PATH.parent.mkdir(parents=True, exist_ok=True)

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=ACTIVE_VENUE_PATH.parent,
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_file.write(venue_json)
            temp_path = Path(temp_file.name)

        temp_path.replace(ACTIVE_VENUE_PATH)

    except OSError as exc:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500,
            detail="Could not save the active venue.",
        ) from exc

    # Activate the new venue and discard stale crowd counts.
    global venue
    with state_lock:
        venue = updated_venue
        stale_zone_ids = set(latest_states) - known_zone_ids
        for zone_id in stale_zone_ids:
            latest_states.pop(zone_id, None)


def get_hold_durations(
    plan: Plan,
    active_venue: Venue | None = None,
) -> dict[str, int]:
    """Map hold_inflow actions to zones in the selected venue."""
    selected_venue = active_venue or venue
    durations: dict[str, int] = {}

    entries = {
        entry.name.strip().casefold(): entry.zone
        for entry in selected_venue.entries
    }

    for action in plan.actions:
        if action.type != "hold_inflow":
            continue

        if not action.entry:
            raise ValueError("hold_inflow actions must specify an entry")

        entry_key = action.entry.strip().casefold()
        if entry_key not in entries:
            raise ValueError(f"Unknown entry: {action.entry!r}")

        zone_id = entries[entry_key]

        if action.zone is not None and action.zone != zone_id:
            raise ValueError(
                f"Entry {action.entry!r} belongs to zone {zone_id!r}, "
                f"not {action.zone!r}."
            )

        if (
            action.minutes is None
            or isinstance(action.minutes, bool)
            or not isinstance(action.minutes, int)
            or action.minutes < 0
        ):
            raise ValueError("Hold durations must be non-negative integers")

        durations[zone_id] = action.minutes

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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Content-Type"],
)
from act.recommend import router as recommendation_router

app.include_router(recommendation_router)

@app.get("/venue/{venue_id}")
def get_venue(venue_id: str):
    # Also answer to the team-wide VENUE_ID from .env (spec: vit-main-ground), so the
    # Act planner gets this venue instead of falling back to its own placeholder.
    if venue_id not in (venue.venue_id, os.environ.get("VENUE_ID")):
        raise HTTPException(status_code=404, detail="Venue not found")
    return venue


@app.put("/venue/{venue_id}", response_model=Venue)
def update_venue(venue_id: str, updated_venue: Venue):
    """Validate, save, and activate an edited venue."""
    if venue_id != venue.venue_id:
        raise HTTPException(status_code=404, detail="Venue not found")

    try:
        save_active_venue(updated_venue)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

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
        validate_gate_safety(plan, venue)
        planned_venue = apply_plan_to_venue(plan)
        hold_durations = get_hold_durations(plan, active_venue=planned_venue)
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


@app.post("/twin/from-photo", response_model=Venue)
async def twin_from_photo(file: UploadFile = File(...)):
    """Generate a venue twin from an uploaded site-plan image."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="Upload an image file.",
        )

    contents = await file.read(MAX_IMAGE_BYTES + 1)

    try:
        data_url, image_format = validate_uploaded_image(contents)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await file.close()

    # Check the key before importing the shared helper.
    if not os.environ.get("NEBIUS_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="Venue generation is unavailable until the Nebius API key is configured.",
        )

    # Import lazily so the app can start without the Nebius key.
    from common.llm import call_json

    try:
        generated_venue = call_json(
            role="vl",
            purpose="venue_twin",
            system=(
                "You create venue digital twins from site-plan images. "
                "Return only data matching the supplied Venue schema. "
                "Every zone must have a strictly positive area_m2 value. "
                "Never use zero, a negative number, or a missing value for area_m2. "
                "Estimate plausible positive areas in square metres when exact "
                "measurements are unavailable, and explain uncertainty in "
                "capacity_note. Every link must have a strictly positive width_m. "
                "Do not invent precise real-world measurements from pixels. "
                "Use unique zone IDs, connect links to valid zone IDs or "
                "'outside', and keep polygons within the image bounds. "
                "Every polygon must contain at least three valid coordinate points."
            ),
            user=(
                "Analyze this site plan and create a venue twin. "
                "Use the image dimensions as the coordinate system for both "
                "polygon_px and polygon_map. If exact scale is unavailable, "
                "clearly label area and width estimates as approximate in "
                "capacity_note. Set venue_id to 'uploaded-venue'."
            ),
            schema=Venue,
            images=[data_url],
        )
    except Exception:
        logger.exception("Venue twin generation failed")
        raise HTTPException(
            status_code=502,
            detail="The venue twin could not be generated. Please try again.",
        )

    try:
        validate_generated_venue(generated_venue)
        logger.info("Corrected venue passed validation.")
    except ValueError as first_error:
        # Ask the model to correct invalid venue data once.
        try:
            generated_venue = call_json(
                role="vl",
                purpose="venue_twin_correction",
                system=(
                    "Correct the supplied venue JSON. Every zone must have "
                    "a strictly positive area_m2, every link must have a "
                    "strictly positive width_m, all zone IDs must be unique, "
                    "all links must reference valid zones or 'outside', and "
                    "all polygons must contain at least three points. "
                    "Preserve the venue layout and return valid JSON only."
                ),
                user=(
                    f"The previous venue failed validation: {first_error}. "
                    "Correct this venue data:\n"
                    + generated_venue.model_dump_json(by_alias=True)
                ),
                schema=Venue,
                temperature=0.0,
            )
            validate_generated_venue(generated_venue)
        except Exception as exc:
            logger.error("Venue correction error type: %s", type(exc).__name__)
            logger.exception("Generated venue correction failed")
            raise HTTPException(
                status_code=422,
                detail="The generated venue failed validation. Please try another site plan.",
            ) from exc

    try:
        save_active_venue(generated_venue)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return generated_venue
