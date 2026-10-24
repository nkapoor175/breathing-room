"""Turnout estimator (A07): how many people are really likely to come?

Before an event, compare likely turnout with the crowd size the organizer declared.
  1. 3 Tavily searches about the event, limited to a date window and a country
  2. Nemotron 3 Super (reasoning off) extracts every crowd number with its exact
     quote, url and kind (expected / reported / declared / past_event)
  3. every quote is checked in code: it must appear in the text of the result it
     claims to come from, or it is dropped. A made-up number can't reach the card.
  4. low/high from the checked expected + reported numbers; ratio = high / declared.
     If there are no numbers for this event itself, the organizer's recent events
     ("past_event") are used instead, and the card says so. Above 1.5 the dashboard
     shows a warning, and the ratio can be Nightmare Mode's arrival multiplier.

--before-event only uses news published before the event date: the honest way to ask
"would this have warned us?" about a past event. Without it the window runs up to
today (for upcoming events).

Each basic search costs 1 Tavily credit (1,000 free a month); results are cached in
act/.cache/tavily/ so re-running a demo costs nothing.

Run:  python -m act.turnout --event "TVK Vijay rally" --city Karur --date 2025-09-27 \
          --declared 10000 --before-event --publish
"""
import argparse, datetime, hashlib, json, os, re
from pathlib import Path
from typing import Callable, Literal, Optional

from pydantic import BaseModel

from common.timeutil import now_iso

# Super, not Lightning (spec): on Oct 25 Lightning turned vague words ("thousands of people",
# "tens of thousands") into made-up exact numbers; Super invented none.
TURNOUT_MODEL = os.environ.get("TURNOUT_MODEL", "super")
CACHE_DIR = Path(__file__).parent / ".cache" / "tavily"
WARN_RATIO = 1.5
WINDOW_DAYS = 30           # news from up to 30 days before the event
# Tavily's "news" topic leans on US/UK outlets; general search limited to the country
# finds Indian regional coverage (tested Oct 25). TURNOUT_COUNTRY="" searches worldwide.
COUNTRY = os.environ.get("TURNOUT_COUNTRY", "india")


class SourceEstimate(BaseModel):
    url: str
    quote: str
    estimate: int
    kind: Literal["expected", "reported", "declared", "past_event"]


class Extraction(BaseModel):
    sources: list[SourceEstimate]
    note: str


class Source(SourceEstimate):
    published: Optional[str] = None


class TurnoutEstimate(BaseModel):
    t: str
    event: str
    city: str
    date: str
    declared: int
    low: Optional[int]
    high: Optional[int]
    ratio: Optional[float]          # high / declared
    based_on: Literal["this_event", "past_events", "none"]
    warning: bool
    message: str
    sources: list[Source]           # checked sources only
    dropped: int                    # sources the model gave that failed the quote check
    note: str
    window: dict                    # {"start_date", "end_date"}
    mode: Literal["before_event", "up_to_today"]
    searches: int


Search = Callable[[str, dict], list[dict]]     # (query, params) -> Tavily results
Extract = Callable[[dict], Extraction]


def queries(event: str, city: str, date: datetime.date) -> list[str]:
    """The spec's three searches, except the second leaves out the date: with it, the
    search missed the coverage of the organizer's earlier events (tested Oct 25)."""
    return [f"{event} {city} expected crowd",
            f"{event} crowd lakh people",
            f"{event} attendance"]


def window(date: datetime.date, before_event: bool, today: Optional[datetime.date] = None) -> dict:
    today = today or datetime.date.today()
    start = date - datetime.timedelta(days=WINDOW_DAYS)
    end = date - datetime.timedelta(days=1) if before_event else min(today, date + datetime.timedelta(days=3))
    return {"start_date": start.isoformat(), "end_date": max(start, end).isoformat()}


def _norm(s: str) -> str:
    s = s.lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip()


UNITS = {"lakh": 100_000, "lakhs": 100_000, "crore": 10_000_000, "crores": 10_000_000,
         "million": 1_000_000, "thousand": 1_000}
NUMBER = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(lakhs?|crores?|million|thousand)?", re.IGNORECASE)


def numbers_in(quote: str) -> set[int]:
    """Every number a quote states: "27,000" -> 27000, "1.5 lakh" -> 150000."""
    out = set()
    for digits, unit in NUMBER.findall(quote):
        try:
            n = float(digits.replace(",", ""))
        except ValueError:
            continue
        out.add(round(n * UNITS.get(unit.lower(), 1)) if unit else round(n))
    return out


def check_source(s: SourceEstimate, texts: dict[str, str]) -> bool:
    """The quote must be in that url's text, and the estimate must be a number the
    quote actually states (so "tens of thousands" can't become 30,000)."""
    text = texts.get(s.url)
    return bool(text and s.estimate > 0 and _norm(s.quote) in _norm(text) and s.estimate in numbers_in(s.quote))


def search_params(win: dict, country: str = COUNTRY) -> dict:
    p = {"search_depth": "basic", "max_results": 5, **win}
    return {**p, "topic": "general", "country": country} if country else {**p, "topic": "news"}


def estimate(event: str, city: str, date: datetime.date, declared: int, search: Search, extract: Extract,
             before_event: bool = False, today: Optional[datetime.date] = None, country: str = COUNTRY,
             organizer: Optional[str] = None, log: Callable[[str], None] = print) -> TurnoutEstimate:
    win = window(date, before_event, today)
    params = search_params(win, country)
    results, seen = [], set()
    qs = queries(event, city, date)
    for q in qs:
        for r in search(q, params):
            if r.get("url") and r["url"] not in seen:
                seen.add(r["url"])
                results.append({"url": r["url"], "published": r.get("published_date"), "text": r.get("content", "")})
    log(f"turnout: {len(results)} unique results from {len(qs)} searches ({win['start_date']} to {win['end_date']})")

    if results:
        ex = extract({"event": event, "organizer": organizer or event, "city": city, "date": date.isoformat(),
                      "declared_by_organizer": declared, "results": results})
    else:
        ex = Extraction(sources=[], note="No news found in this date window.")
    texts = {r["url"]: r["text"] for r in results}
    published = {r["url"]: r["published"] for r in results}
    good = []
    for s in ex.sources:
        if not check_source(s, texts):
            log(f"turnout: dropped [{s.kind}] {s.estimate:,}: quote not in the article or number not in it: {s.quote!r}")
            continue
        # The model mixes up this event and the organizer's earlier ones, so code decides:
        # a number is about THIS event only if its article mentions the event's city.
        if s.kind in ("expected", "reported") and city.lower() not in texts[s.url].lower():
            log(f"turnout: [{s.kind}] {s.estimate:,} is from an article that never mentions {city}: "
                f"counted as past_event")
            s = s.model_copy(update={"kind": "past_event"})
        good.append(Source(**s.model_dump(), published=published.get(s.url)))
    dropped = len(ex.sources) - len(good)
    if before_event:
        # Nothing about this event can be "reported on the day" before it happens: such a
        # number leaked in from a later page (search results don't always carry a date).
        late = [s for s in good if s.kind == "reported"]
        if late:
            log(f"turnout: before-event mode, ignoring {len(late)} 'reported' number(s) from after the event")
            good = [s for s in good if s.kind != "reported"]
            dropped += len(late)

    # This event's own estimates first; the organizer's recent events only if there are none.
    crowd = [s.estimate for s in good if s.kind in ("expected", "reported")]
    based_on = "this_event" if crowd else "none"
    if not crowd:
        crowd = [s.estimate for s in good if s.kind == "past_event"]
        based_on = "past_events" if crowd else "none"
    low, high = (min(crowd), max(crowd)) if crowd else (None, None)
    ratio = round(high / declared, 2) if high and declared > 0 else None
    warning = bool(ratio and ratio > WARN_RATIO)
    what = "the organizer's recent events drew" if based_on == "past_events" else "news estimates"
    if ratio is None:
        message = "No usable crowd estimate found in the news. Use the declared size with caution."
    elif warning:
        message = (f"Likely turnout up to {ratio:g}× the declared crowd: {what} up to {high:,} "
                   f"vs {declared:,} declared. See the simulation at this size.")
    else:
        message = f"In line with the declared {declared:,}: {what} {low:,}–{high:,}."
    return TurnoutEstimate(t=now_iso(), event=event, city=city, date=date.isoformat(), declared=declared,
                           low=low, high=high, ratio=ratio, based_on=based_on, warning=warning,
                           message=message, sources=good,
                           dropped=dropped, note=ex.note, window=win,
                           mode="before_event" if before_event else "up_to_today", searches=len(qs))


# ---------- live pieces ----------
def tavily_search(api_key: str, log: Callable[[str], None] = print) -> Search:
    from tavily import TavilyClient
    client = TavilyClient(api_key)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def search(query: str, params: dict) -> list[dict]:
        key = hashlib.sha256(json.dumps([query, params], sort_keys=True).encode()).hexdigest()[:20]
        f = CACHE_DIR / f"{key}.json"
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
        r = client.search(query, **params)
        f.write_text(json.dumps(r["results"], ensure_ascii=False), encoding="utf-8")
        log(f"turnout: Tavily search (1 credit): {query!r}")
        return r["results"]
    return search


def nemotron_extract(on_cost, role: str = TURNOUT_MODEL) -> Extract:
    from common.llm import NO_THINK, call_json
    system = (Path(__file__).parent / "prompts" / "turnout.md").read_text(encoding="utf-8")

    def extract(payload: dict) -> Extraction:
        return call_json(role, "turnout", system, json.dumps(payload, ensure_ascii=False), Extraction,
                         on_cost=on_cost, extra_body=NO_THINK)
    return extract


def main():
    ap = argparse.ArgumentParser(description="Estimate likely turnout from the news with Tavily.")
    ap.add_argument("--event", required=True)
    ap.add_argument("--city", required=True)
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--declared", type=int, required=True, help="crowd size the organizer declared")
    ap.add_argument("--organizer", help="who runs it (party, leader, company); finds their earlier events")
    ap.add_argument("--before-event", action="store_true", help="only news published before the event")
    ap.add_argument("--country", default=COUNTRY, help='limit search to a country ("" = worldwide news)')
    ap.add_argument("--publish", action="store_true", help="publish on br/turnout for the dashboard")
    args = ap.parse_args()

    costs = []
    est = estimate(args.event, args.city, datetime.date.fromisoformat(args.date), args.declared,
                   tavily_search(os.environ["TAVILY_API_KEY"]), nemotron_extract(costs.append),
                   before_event=args.before_event, country=args.country, organizer=args.organizer)
    print(json.dumps(est.model_dump(), ensure_ascii=False, indent=1))
    if costs:
        print(f"LLM: {costs[-1]['latency_s']} s, ${sum(c['usd'] for c in costs):.5f}")
    if args.publish:
        from common.bus import make_client, publish
        mq = make_client("act-turnout")
        mq.loop_start()
        # retained: a one-off pre-event card must survive a backend that starts later
        sent = [publish(mq, "br/turnout", est, retain=True)] + [publish(mq, "br/cost", c) for c in costs]
        for info in sent:                 # wait until it has really left before disconnecting
            info.wait_for_publish(timeout=10)
        ok = all(info.is_published() for info in sent)
        mq.loop_stop()
        mq.disconnect()
        print("published on br/turnout" if ok else "WARNING: could not publish on br/turnout (MQTT)")


if __name__ == "__main__":
    main()
