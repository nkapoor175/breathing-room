"""Report fusion (A04): free-text messages -> structured Report on br/report.

Call notes typed into the dashboard arrive raw on br/report_raw; Telegram messages
come straight from telegram_bot.py (A05) through ReportFusion.fuse(). A Nemotron
model reads each message (English, Tamil or Hindi) and extracts the zone, a
severity 1-5 and a short English summary. Button presses arrive already
structured from the serial bridge and skip this step.

A report is never dropped: if the model call fails, the report is still published
with a keyword-based severity and the original text.

Model: Nemotron 3 Super with reasoning off. In a 6-message en/ta/hi test (Oct 23)
it got every zone and severity right in ~2 s; Lightning misread one Tamil zone.
REPORT_MODEL=lightning switches back.

Run:  python -m act.reports
"""
import json, os, queue, re
from pathlib import Path
from typing import Callable, Optional

from pydantic import BaseModel, Field

from common.contracts import Report
from common.timeutil import now_iso

REPORT_MODEL = os.environ.get("REPORT_MODEL", "super")
SOURCES = {"telegram", "call_note", "operator"}


class Extracted(BaseModel):
    zone: Optional[str] = None
    severity: int = Field(ge=1, le=5)
    text: str


Ask = Callable[[str, list[dict]], Extracted]   # (message, zones) -> extraction

# Used only when the model call fails. Unknown -> 3 so a human still looks at it.
KEYWORDS = [
    (5, r"fell|fallen|faint|unconscious|can'?t breathe|cannot breathe|not breathing|crush|collaps|"
        r"गिर|बेहोश|सांस|விழு|மயக்க|மூச்சு"),
    (4, r"push|shov|climb|barricade|barrier|stampede|धक्का|चढ़|தள்ளு|ஏறு"),
]


def keyword_severity(text: str) -> int:
    t = text.lower()
    for sev, pattern in KEYWORDS:
        if re.search(pattern, t):
            return sev
    return 3


class ReportFusion:
    def __init__(self, zones: list[dict], ask: Ask, log: Callable[[str], None] = print):
        self.zones = [{"id": z["id"], "name": z["name"]} for z in zones]
        self.ids = {z["id"] for z in self.zones}
        self.ask = ask
        self.log = log

    def _zone_by_name(self, text: str) -> Optional[str]:
        t = text.lower()
        hits = [z["id"] for z in self.zones if z["name"].lower() in t]
        return hits[0] if len(hits) == 1 else None

    def fuse(self, text: str, source: str, node: Optional[str] = None,
             zone_hint: Optional[str] = None, t: Optional[str] = None) -> Report:
        source = source if source in SOURCES else "operator"
        try:
            e = self.ask(text, self.zones)
            zone = e.zone if e.zone in self.ids else None
            if e.zone and zone is None:
                self.log(f"reports: model named unknown zone {e.zone!r}, ignoring it")
            severity, summary = e.severity, e.text.strip() or text
        except Exception as ex:                      # never drop a report
            self.log(f"reports: model call failed ({type(ex).__name__}: {ex}); using keywords")
            zone, severity, summary = self._zone_by_name(text), keyword_severity(text), text[:200]
        if zone_hint in self.ids:                    # a zone the operator picked wins
            zone = zone_hint
        return Report(t=t or now_iso(), source=source, node=node, zone=zone, text=summary, severity=severity)


def nemotron_ask(on_cost, role: str = REPORT_MODEL) -> Ask:
    from common.llm import NO_THINK, call_json
    system = (Path(__file__).parent / "prompts" / "report_extract.md").read_text(encoding="utf-8")

    def ask(message: str, zones: list[dict]) -> Extracted:
        user = json.dumps({"message": message, "zones": zones}, ensure_ascii=False)
        return call_json(role, "report_extract", system, user, Extracted, on_cost=on_cost, extra_body=NO_THINK)
    return ask


def main():
    from act.planner import load_venue
    from common.bus import make_client, publish

    venue = load_venue()
    inbox: queue.Queue = queue.Queue()
    mq = make_client("act-reports")
    mq.on_connect = lambda c, u, f, rc, p: c.subscribe("br/report_raw")
    mq.on_message = lambda c, u, m: inbox.put(m.payload)
    mq.loop_start()
    fusion = ReportFusion([z.model_dump() for z in venue.zones],
                          nemotron_ask(lambda cost: publish(mq, "br/cost", cost)))
    print(f"reports: listening on br/report_raw, model {REPORT_MODEL}, venue {venue.venue_id}")
    while True:
        payload = inbox.get()
        try:
            raw = json.loads(payload)
            if not str(raw.get("text", "")).strip():
                continue
            r = fusion.fuse(raw["text"], raw.get("source", "call_note"), raw.get("node"), raw.get("zone"))
        except Exception as e:                       # bad raw message
            print(f"reports: skipped bad raw message ({type(e).__name__}: {e})")
            continue
        publish(mq, "br/report", r)
        print(f"{r.t} report zone={r.zone} severity={r.severity}: {r.text}")


if __name__ == "__main__":
    main()
