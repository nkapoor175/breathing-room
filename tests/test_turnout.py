"""Turnout estimator with fake Tavily results and a fake model."""
import datetime

from act.turnout import Extraction, SourceEstimate, check_source, estimate, queries, window

D = datetime.date(2025, 9, 27)
TODAY = datetime.date(2026, 10, 25)
A = "https://news.example/a"
B = "https://news.example/b"
RESULTS = {
    A: "The letter said that the party expects 10,000 people to attend the rally in Karur.",
    B: "Police estimate that close to 27,000 people may gather in Karur, with supporters arriving from nearby districts.",
}


def fake_search(results=RESULTS):
    calls = []

    def search(query, params):
        calls.append((query, params))
        return [{"url": u, "content": t, "published_date": "Fri, 26 Sep 2025"} for u, t in results.items()]
    search.calls = calls
    return search


def src(url, quote, n, kind):
    return SourceEstimate(url=url, quote=quote, estimate=n, kind=kind)


GOOD = Extraction(note="Police expect far more than declared.", sources=[
    src(A, "expects 10,000 people to attend", 10000, "declared"),
    src(B, "close to 27,000 people may gather", 27000, "expected"),
])


def run(extraction=GOOD, declared=10000, search=None, before_event=True):
    return estimate("TVK rally", "Karur", D, declared, search or fake_search(), lambda payload: extraction,
                    before_event=before_event, today=TODAY, log=lambda s: None)


def test_queries_are_the_specs_three():
    assert queries("TVK rally", "Karur", D) == ["TVK rally Karur expected crowd",
                                                "TVK rally crowd lakh people", "TVK rally attendance"]


def test_window_before_event_stops_the_day_before():
    assert window(D, before_event=True, today=TODAY) == {"start_date": "2025-08-28", "end_date": "2025-09-26"}


def test_window_up_to_today_for_past_event_includes_a_few_days_after():
    assert window(D, before_event=False, today=TODAY)["end_date"] == "2025-09-30"


def test_window_upcoming_event_ends_today():
    assert window(datetime.date(2026, 11, 10), before_event=False, today=TODAY)["end_date"] == "2026-10-25"


def test_check_source():
    texts = {B: RESULTS[B]}
    assert check_source(src(B, "close to 27,000 people may gather", 27000, "expected"), texts)
    assert check_source(src(B, "Close to  27,000 people may   gather", 27000, "expected"), texts)   # case/space
    assert not check_source(src(B, "close to 50,000 people may gather", 50000, "expected"), texts)   # made up
    assert not check_source(src(A, "close to 27,000 people may gather", 27000, "expected"), texts)   # wrong url
    assert not check_source(src(B, "people may gather", 27000, "expected"), texts)                   # no number
    assert not check_source(src(B, "close to 27,000 people may gather", 30000, "expected"), texts)   # wrong number


def test_numbers_in():
    from act.turnout import numbers_in
    assert numbers_in("close to 27,000 people") == {27000}
    assert numbers_in("over 1.5 lakh supporters, maybe 2 lakhs") == {150000, 200000}
    assert numbers_in("10 crore devotees") == {100000000}
    assert numbers_in("tens of thousands of supporters") == set()


def test_reported_numbers_ignored_before_event():
    late = Extraction(note="", sources=GOOD.sources + [src(B, "close to 27,000 people may gather", 27000, "reported")])
    est = run(late, before_event=True)
    assert [s.kind for s in est.sources] == ["declared", "expected"] and est.dropped == 1
    est = run(late, before_event=False)
    assert len(est.sources) == 3


def test_warning_when_turnout_far_above_declared():
    est = run()
    assert (est.low, est.high, est.ratio, est.warning) == (27000, 27000, 2.7, True)
    assert "2.7× the declared crowd" in est.message and est.mode == "before_event"
    assert est.sources[1].published == "Fri, 26 Sep 2025"


def test_declared_numbers_dont_count_as_turnout():
    est = run(Extraction(note="", sources=[GOOD.sources[0]]))
    assert est.high is None and not est.warning and "No usable crowd estimate" in est.message


def test_invented_quote_is_dropped():
    bad = Extraction(note="", sources=GOOD.sources + [src(B, "over 2 lakh people expected", 200000, "expected")])
    est = run(bad)
    assert est.high == 27000 and est.dropped == 1


def test_in_line_with_declared():
    est = run(declared=25000)
    assert not est.warning and "In line with the declared 25,000" in est.message


def test_no_results_no_model_call():
    called = []
    est = estimate("X", "Y", D, 1000, fake_search({}), lambda p: called.append(p), today=TODAY, log=lambda s: None)
    assert called == [] and est.high is None and est.sources == []


def test_three_searches_with_window_and_duplicates_removed():
    search, seen = fake_search(), []
    est = estimate("TVK rally", "Karur", D, 10000, search, lambda p: seen.append(p) or GOOD,
                   before_event=True, today=TODAY, log=lambda s: None)
    assert len(search.calls) == 3 and est.searches == 3
    assert all(p["end_date"] == "2025-09-26" and p["topic"] == "general" and p["country"] == "india"
               for _, p in search.calls)
    assert len(seen[0]["results"]) == 2                        # same 2 urls from 3 searches


def test_worldwide_uses_news_topic():
    from act.turnout import search_params
    assert search_params({"start_date": "a", "end_date": "b"}, country="")["topic"] == "news"


PAST = "Over 10 lakh people gathered for the party's Maanaadu event in Villupuram last year."


def test_past_events_used_only_when_no_estimate_for_this_event():
    results = {**RESULTS, "https://news.example/c": PAST}
    past = src("https://news.example/c", "Over 10 lakh people gathered for the party's Maanaadu event", 1000000, "past_event")
    only_past = Extraction(note="", sources=[GOOD.sources[0], past])
    est = run(only_past, search=fake_search(results))
    assert est.based_on == "past_events" and est.high == 1000000 and est.ratio == 100.0
    assert "the organizer's recent events drew up to 1,000,000" in est.message
    both = Extraction(note="", sources=GOOD.sources + [past])
    est = run(both, search=fake_search(results))
    assert est.based_on == "this_event" and est.high == 27000


def test_number_from_article_without_the_city_counts_as_past_event():
    trichy = "https://news.example/trichy"
    text = "We expected a crowd of around 25,000, but around 1 lakh people gathered in Tiruchi."
    ex = Extraction(note="", sources=[GOOD.sources[0],
                                      src(trichy, "We expected a crowd of around 25,000", 25000, "expected"),
                                      src(trichy, "around 1 lakh people gathered in Tiruchi", 100000, "reported")])
    est = run(ex, search=fake_search({A: RESULTS[A], trichy: text}), before_event=True)
    assert [(s.kind, s.estimate) for s in est.sources] == [("declared", 10000), ("past_event", 25000),
                                                            ("past_event", 100000)]
    assert est.based_on == "past_events" and est.high == 100000 and est.ratio == 10.0
