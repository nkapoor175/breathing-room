"""Report fusion with a fake model: zone checks, operator hint, never dropping a report."""
import pytest

from act.reports import Extracted, ReportFusion, keyword_severity

ZONES = [{"id": "A", "name": "Stage front"}, {"id": "B", "name": "Gate 2 approach"},
         {"id": "C", "name": "Overflow ground"}, {"id": "D", "name": "Main entrance plaza"}]


def fusion(zone="B", severity=4, text="People pushing near Gate 2", fail=False):
    def ask(message, zones):
        if fail:
            raise RuntimeError("token factory down")
        return Extracted(zone=zone, severity=severity, text=text)
    return ReportFusion(ZONES, ask, log=lambda m: None)


def test_extraction_becomes_report():
    r = fusion().fuse("கேட் 2 அருகே தள்ளுகிறார்கள்", "telegram", node="12345")
    assert (r.zone, r.severity, r.text, r.source, r.node) == ("B", 4, "People pushing near Gate 2", "telegram", "12345")


def test_made_up_zone_is_dropped():
    assert fusion(zone="Z").fuse("pushing", "call_note").zone is None


def test_operator_zone_hint_wins():
    assert fusion(zone="A").fuse("pushing", "call_note", zone_hint="B").zone == "B"


def test_unknown_hint_ignored():
    assert fusion(zone="A").fuse("pushing", "call_note", zone_hint="Q").zone == "A"


def test_unknown_source_becomes_operator():
    assert fusion().fuse("pushing", "radio").source == "operator"


def test_model_failure_still_publishes_with_keywords():
    r = fusion(fail=True).fuse("Someone fell near the Stage front!", "call_note")
    assert r.severity == 5 and r.zone == "A" and r.text.startswith("Someone fell")


@pytest.mark.parametrize("text, sev", [
    ("a man is not breathing", 5),
    ("मुख्य द्वार पर एक आदमी बेहोश हो गया", 5),
    ("ஒருவர் கீழே விழுந்தார்", 5),
    ("people climbing the barricade", 4),
    ("लोग धक्का दे रहे हैं", 4),
    ("very crowded here", 3),
])
def test_keyword_fallback(text, sev):
    assert keyword_severity(text) == sev
