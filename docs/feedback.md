# Tool feedback (compiled by Navika, A10)

**Summary:** Token Factory made it easy to route each job to the right Nemotron model through one OpenAI-compatible endpoint; structured JSON output worked first try. The biggest surprises were hidden reasoning (a 44 s Lightning call that ran out of tokens with no answer until we passed `chat_template_kwargs.enable_thinking=False`, which we found by trial; a documented, per-request switch would help) and translation/number hallucinations in the smaller models, which we now check in code. Tavily's date filters made an honest "before the event" backtest possible; its news topic was US/UK-centric for Indian events.


For each tool: what we used it for, what worked, what didn't, time from zero to first working call, would we use it again. Everyone adds notes as they go.

## Nebius Token Factory

- Oct 23 (Navika): promo credits → API key → first working call in under 30 min. `models.list()` showed all four model IDs exactly as listed in our spec. OpenAI SDK worked unchanged with the base URL swap.
- `response_format: json_schema` (Pydantic schema) worked first try on Ultra and Lightning; no need for the json_object fallback.

## Nebius Serverless Endpoints

## Nebius Serverless Jobs

## Nemotron 3 Ultra

- First test (short watchdog-style prompt): 93 in / 360 out tokens, 1.5 s, $0.0012. Faster than we expected for a 550B model.
- Planning (3 plans from ~1.5k tokens of venue/forecast JSON): 7.5–11 s, ~$0.009–0.0125 per call; `json_schema` output valid every time, but it often omitted `zone`/`minutes` in `hold_inflow` actions, so we validate and repair in code.
- Tamil/Hindi translation: the only model of the three that kept left/right correct in Tamil in our test; still once emitted a Malayalam letter, so we check every translation in code. ~1–3 s, ~$0.001 per line.
- Would use again: yes, for the decisions that matter; too slow/expensive for frequent small jobs.

## Nemotron 3.5 Lightning

- Oct 25: in number extraction from news, Lightning turned vague phrases into exact numbers ("thousands" → 3,000, "tens of thousands" → 30,000). Super did not. We now verify every number against the quote in code.
- Oct 25: Tamil translation of announcements mixed in Korean characters and flipped left/right; Hindi was fine.
- First test (same prompt): 93 in / 605 out tokens, 3.3 s, $0.00015. Used more output tokens than Ultra for a 2-sentence answer (likely hidden reasoning); still very cheap.

## Nemotron 3 Super (Navika)

- Report extraction (en/ta/hi messages → zone + severity), reasoning off: 6/6 correct in our test vs Lightning 5/6 and Ultra 5/6, ~2 s, ~$0.0002 per report.
- Turnout number extraction from news: invented no numbers where Lightning invented four; most conservative of the three.
- Would use again: yes; our default "accurate but cheap" model.

## Nemotron 3.5 Super VL

## Tavily

- Oct 25 (Navika): turnout estimator. Key → first working search in minutes; `tavily-python` 0.8.5 has `start_date`/`end_date`, which made a "news published before the event" backtest possible (better than `time_range`).
- `topic="news"` was strongly US/UK-centric: for a Tamil Nadu rally it returned the London march, NPR, CNN and MLB. `topic="general"` + `country="india"` found The Hindu, NDTV, New Indian Express, Deccan Herald.
- `include_domains` (Indian outlets) on `news` returned pages whose scraped content included sidebar headlines from weeks later, so date filtering doesn't guarantee date-clean content.
- `general` results often have no `published_date`, so we couldn't check dates ourselves.
- `include_usage=True` showing credits per call was useful for budgeting. 12 credits for a full day of experiments.
