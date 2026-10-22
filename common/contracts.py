from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field, ConfigDict

# ---------- Venue twin (written by Imagine) ----------
class Zone(BaseModel):
    id: str                      # "A", "B", ...
    name: str                    # "Stage front"
    area_m2: float               # real walkable area in square metres
    polygon_px: list[list[float]]  # polygon on the CAMERA image, for Sense
    polygon_map: list[list[float]] # polygon on the site-plan image, for the dashboard
    capacity_note: Optional[str] = None

class Link(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str                      # "G2"
    from_zone: str = Field(alias="from")   # zone id
    to_zone: str = Field(alias="to")       # zone id or "outside"
    width_m: float
    kind: Literal["gate", "opening", "corridor"] = "opening"
    state: Literal["open", "closed"] = "open"

class Entry(BaseModel):
    zone: str                    # zone people arrive into
    name: str                    # "Main entrance"

class Venue(BaseModel):
    venue_id: str
    name: str
    zones: list[Zone]
    links: list[Link]
    entries: list[Entry]
    pa_zones: list[str]          # zones with loudspeakers
    officers_total: int

# ---------- Sense ----------
class ZoneState(BaseModel):
    t: str
    zone: str
    count: int
    density_ppm2: float          # people per square metre
    speed_mps: Optional[float] = None
    direction_deg: Optional[float] = None   # 0 = right/east on the image, counter-clockwise
    turbulence: Optional[float] = None      # stretch goal; null until implemented
    source: str                  # "cam-1", "sim" (Judge Mode)

class Report(BaseModel):
    t: str
    source: Literal["volunteer_button", "telegram", "call_note", "operator"]
    node: Optional[str] = None   # "vol-2" for buttons, chat id for Telegram
    zone: Optional[str] = None
    text: str
    severity: int = Field(ge=1, le=5)  # 5 = someone fell / cannot breathe

# ---------- Imagine ----------
class ZoneForecast(BaseModel):
    zone: str
    p50_density: float
    p90_density: float
    p_danger: float              # share of runs reaching danger density
    minutes_to_danger: Optional[float] = None  # median first-crossing time; null if <5% of runs cross

class Forecast(BaseModel):
    t: str
    horizon_min: int = 15
    runs: int = 1000
    zones: list[ZoneForecast]

# ---------- Act ----------
class Action(BaseModel):
    type: Literal["move_officers", "gate", "announce", "hold_inflow"]
    count: Optional[int] = None       # move_officers
    from_zone: Optional[str] = None   # move_officers
    to_zone: Optional[str] = None     # move_officers
    link: Optional[str] = None        # gate: link id like "G3"
    state: Optional[Literal["open", "closed"]] = None  # gate
    zone: Optional[str] = None        # announce / hold_inflow
    langs: Optional[list[Literal["en", "ta", "hi"]]] = None  # announce
    text: Optional[str] = None        # announce (English master text)
    minutes: Optional[int] = None     # hold_inflow duration
    entry: Optional[str] = None       # hold_inflow: which entry to pause

class Plan(BaseModel):
    plan_id: str
    strategy: str                     # short label, e.g. "meter inflow at gate 1"
    actions: list[Action]
    why: str                          # one sentence a police officer understands

class PlanCandidates(BaseModel):
    plans: list[Plan]

class ScoreResult(BaseModel):
    plan_id: str
    max_p_danger: float               # worst zone's danger probability with this plan
    min_minutes_to_danger: Optional[float]
    zones: list[ZoneForecast]

class ChosenPlan(BaseModel):
    t: str
    plan: Plan
    score: ScoreResult
    baseline_max_p_danger: float      # what happens if we do nothing
    candidates_considered: int

class DeviceCommand(BaseModel):
    to: str                           # "gate-3"
    cmd: Literal["arrow", "blink"]
    value: Literal["left", "right", "up", "stop", "clear"]

class OfficerStatus(BaseModel):
    t: str
    officer_id: str
    name: str
    zone: str
    status: Literal["idle", "assigned", "on_the_way", "arrived"]
    task: Optional[str] = None
    simulated: bool = False           # True for officers without a real phone in the demo

class Announcement(BaseModel):
    t: str
    zone: str
    plan_id: str
    texts: dict[str, str]             # {"en": ..., "ta": ..., "hi": ...}

class CostEvent(BaseModel):
    t: str
    role: Literal["ultra", "lightning", "vl", "super"]
    purpose: str                      # "plan", "watchdog", "report_extract", "venue_twin" ...
    prompt_tokens: int
    completion_tokens: int
    usd: float
    latency_s: float
