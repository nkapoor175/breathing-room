
from imagine.fake_imagine import apply_plan_to_venue, validate_generated_venue
from common.contracts import Plan
from imagine.sim import simulate

def test_gate_plan_closes_gate_on_copy_only():
    from imagine.fake_imagine import venue

    original_state = next(
        link.state for link in venue.links if link.id == "G3"
    )

    plan = Plan(
        plan_id="close-g3",
        strategy="Close gate G3",
        actions=[
            {
                "type": "gate",
                "link": "G3",
                "state": "closed",
            }
        ],
        why="Test closing gate G3",
    )

    planned_venue = apply_plan_to_venue(plan)

    planned_g3 = next(
        link for link in planned_venue.links if link.id == "G3"
    )
    original_g3 = next(
        link for link in venue.links if link.id == "G3"
    )

    assert planned_g3.state == "closed"
    assert original_g3.state == original_state


def test_gate_plan_rejects_unknown_link():
    import pytest
    from imagine.fake_imagine import apply_plan_to_venue

    plan = Plan(
        plan_id="invalid-gate",
        strategy="Close unknown gate",
        actions=[
            {
                "type": "gate",
                "link": "G999",
                "state": "closed",
            }
        ],
        why="Test invalid gate",
    )

    with pytest.raises(ValueError, match="Unknown gate link"):
        apply_plan_to_venue(plan)



def test_score_passes_hold_inflow_to_simulator(monkeypatch):
    from fastapi.testclient import TestClient
    from imagine import fake_imagine
    from imagine.sim import simulate

    captured = {}

    def fake_make_forecast(**kwargs):
        captured.update(kwargs)
        return simulate(
            kwargs.get("active_venue") or fake_imagine.venue,
            kwargs.get("initial_counts") or {
                "A": 0, "B": 0, "C": 0, "D": 0
            },
            {"A": 0, "B": 0, "C": 0, "D": 0},
            fake_imagine.assumptions,
            seed=42,
            hold_inflow_min=kwargs.get("hold_inflow_min"),
        )

    monkeypatch.setattr(
        fake_imagine,
        "make_forecast",
        fake_make_forecast,
    )

    plan = {
        "plan_id": "hold-main-entry",
        "strategy": "Temporarily hold the main entrance",
        "actions": [
            {
                "type": "hold_inflow",
                "entry": "Main Entrance",
                "minutes": 5,
            }
        ],
        "why": "Temporarily meter entry to reduce incoming crowd pressure.",
    }

    with TestClient(fake_imagine.app) as client:
        response = client.post("/score", json={"plan": plan})

    assert response.status_code == 200
    assert captured["hold_inflow_min"] == {"A": 5}


def test_score_passes_announcement_zone_to_simulator(monkeypatch):
    from fastapi.testclient import TestClient
    from imagine import fake_imagine
    from imagine.sim import simulate

    captured = {}

    def fake_make_forecast(**kwargs):
        captured.update(kwargs)
        return simulate(
            kwargs.get("active_venue") or fake_imagine.venue,
            kwargs.get("initial_counts") or {
                "A": 0, "B": 0, "C": 0, "D": 0
            },
            {"A": 0, "B": 0, "C": 0, "D": 0},
            fake_imagine.assumptions,
            seed=42,
            hold_inflow_min=kwargs.get("hold_inflow_min"),
            announce_zones=kwargs.get("announce_zones"),
        )

    monkeypatch.setattr(
        fake_imagine, "make_forecast", fake_make_forecast
    )

    plan = {
        "plan_id": "announce-main-entrance",
        "strategy": "Announce at the main entrance",
        "actions": [
            {
                "type": "announce",
                "zone": "A",
                "langs": ["en"],
                "text": "Please keep moving and avoid crowding.",
            }
        ],
        "why": "Reduce crowd pressure at the main entrance.",
    }

    with TestClient(fake_imagine.app) as client:
        response = client.post("/score", json={"plan": plan})

    assert response.status_code == 200
    assert captured["announce_zones"] == ["A"]


def test_score_rejects_announcement_for_unknown_zone():
    from fastapi.testclient import TestClient
    from imagine import fake_imagine

    plan = {
        "plan_id": "announce-unknown-zone",
        "strategy": "Announce in an unknown zone",
        "actions": [
            {
                "type": "announce",
                "zone": "UNKNOWN",
                "langs": ["en"],
                "text": "Please keep moving.",
            }
        ],
        "why": "Test invalid zone handling.",
    }

    with TestClient(fake_imagine.app) as client:
        response = client.post("/score", json={"plan": plan})

    assert response.status_code == 400
    assert "Unknown zone" in response.json()["detail"]


def test_validate_generated_venue_accepts_demo_venue():
    from imagine.fake_imagine import venue

    validate_generated_venue(venue)


def test_validate_generated_venue_rejects_unknown_link_source():
    from copy import deepcopy
    import pytest
    from imagine.fake_imagine import venue

    invalid_venue = deepcopy(venue)
    invalid_venue.links[0].from_zone = "UNKNOWN"

    with pytest.raises(ValueError, match="unknown source zone"):
        validate_generated_venue(invalid_venue)


def test_validate_generated_venue_rejects_unknown_link_destination():
    from copy import deepcopy
    import pytest
    from imagine.fake_imagine import venue

    invalid_venue = deepcopy(venue)
    invalid_venue.links[0].to_zone = "UNKNOWN"

    with pytest.raises(ValueError, match="unknown destination zone"):
        validate_generated_venue(invalid_venue)


def test_validate_generated_venue_rejects_unknown_entry_zone():
    from copy import deepcopy
    import pytest
    from imagine.fake_imagine import venue

    invalid_venue = deepcopy(venue)
    invalid_venue.entries[0].zone = "UNKNOWN"

    with pytest.raises(ValueError, match="references an unknown zone"):
        validate_generated_venue(invalid_venue)


def test_validate_generated_venue_rejects_unknown_pa_zone():
    from copy import deepcopy
    import pytest
    from imagine.fake_imagine import venue

    invalid_venue = deepcopy(venue)
    invalid_venue.pa_zones.append("UNKNOWN")

    with pytest.raises(ValueError, match="PA zones must refer to known zones"):
        validate_generated_venue(invalid_venue)


def test_validate_generated_venue_rejects_duplicate_zone_ids():
    from copy import deepcopy
    import pytest
    from imagine.fake_imagine import venue, validate_generated_venue

    invalid_venue = deepcopy(venue)
    invalid_venue.zones[1].id = invalid_venue.zones[0].id

    with pytest.raises(ValueError, match="duplicate zone IDs"):
        validate_generated_venue(invalid_venue)


def test_validate_generated_venue_rejects_nonpositive_area():
    from copy import deepcopy
    import pytest
    from imagine.fake_imagine import venue, validate_generated_venue

    invalid_venue = deepcopy(venue)
    invalid_venue.zones[0].area_m2 = 0

    with pytest.raises(ValueError, match="positive area"):
        validate_generated_venue(invalid_venue)


def test_validate_generated_venue_rejects_polygon_with_too_few_points():
    from copy import deepcopy
    import pytest
    from imagine.fake_imagine import venue, validate_generated_venue

    invalid_venue = deepcopy(venue)
    invalid_venue.zones[0].polygon_map = [[0, 0], [10, 10]]

    with pytest.raises(ValueError, match="at least 3 points"):
        validate_generated_venue(invalid_venue)


def test_validate_generated_venue_rejects_nonpositive_link_width():
    from copy import deepcopy
    import pytest
    from imagine.fake_imagine import venue, validate_generated_venue

    invalid_venue = deepcopy(venue)
    invalid_venue.links[1].width_m = 0

    with pytest.raises(ValueError, match="positive width"):
        validate_generated_venue(invalid_venue)
