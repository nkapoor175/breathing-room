"""The example messages from spec Section 7.3 must parse with the frozen contracts."""
import json

import pytest
from pydantic import ValidationError

from common.contracts import ChosenPlan, DeviceCommand, Forecast, Link, Report, ZoneState


def test_zone_state():
    m = ZoneState.model_validate_json(
        '{"t": "2026-10-28T18:40:02+05:30", "zone": "B", "count": 690, "density_ppm2": 4.6,'
        ' "speed_mps": 0.3, "direction_deg": 85, "turbulence": null, "source": "cam-1"}')
    assert m.density_ppm2 == 4.6 and m.turbulence is None


def test_report_and_severity_bounds():
    r = Report.model_validate_json(
        '{"t": "2026-10-28T18:41:10+05:30", "source": "volunteer_button", "node": "vol-2",'
        ' "zone": "B", "text": "pushing here", "severity": 4}')
    assert r.severity == 4
    with pytest.raises(ValidationError):
        Report(t="x", source="telegram", text="x", severity=6)


def test_forecast():
    f = Forecast.model_validate_json(
        '{"t": "2026-10-28T18:41:30+05:30", "horizon_min": 15, "runs": 1000,'
        ' "zones": [{"zone": "B", "p50_density": 5.8, "p90_density": 7.1, "p_danger": 0.62, "minutes_to_danger": 9}]}')
    assert f.zones[0].minutes_to_danger == 9


def test_chosen_plan():
    c = ChosenPlan.model_validate(json.loads("""
    {"t": "2026-10-28T18:42:05+05:30",
     "plan": {"plan_id": "P2", "strategy": "reinforce gate 2 and meter inflow",
       "actions": [
         {"type": "move_officers", "count": 6, "from_zone": "C", "to_zone": "B"},
         {"type": "gate", "link": "G3", "state": "closed"},
         {"type": "hold_inflow", "entry": "Main entrance", "zone": "A", "minutes": 10},
         {"type": "announce", "zone": "A", "langs": ["ta", "en"], "text": "Please move calmly to your left, towards Gate 1."}],
       "why": "Gate 2 approach reaches danger in 9 minutes; this keeps every zone safe in 92% of simulated futures."},
     "score": {"plan_id": "P2", "max_p_danger": 0.08, "min_minutes_to_danger": null, "zones": []},
     "baseline_max_p_danger": 0.62, "candidates_considered": 4}"""))
    assert len(c.plan.actions) == 4 and c.score.min_minutes_to_danger is None


def test_device_command():
    d = DeviceCommand.model_validate_json('{"to": "gate-3", "cmd": "arrow", "value": "stop"}')
    assert d.value == "stop"


def test_link_alias_round_trip():
    link = Link.model_validate({"id": "G2", "from": "B", "to": "outside", "width_m": 3.0})
    assert link.from_zone == "B"
    assert link.model_dump(by_alias=True)["from"] == "B"
