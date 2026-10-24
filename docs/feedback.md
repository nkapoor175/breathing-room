# Tool feedback (compiled by Navika, A10)

For each tool: what we used it for, what worked, what didn't, time from zero to first working call, would we use it again. Everyone adds notes as they go.

## Nebius Token Factory

- Oct 23 (Navika): promo credits → API key → first working call in under 30 min. `models.list()` showed all four model IDs exactly as listed in our spec. OpenAI SDK worked unchanged with the base URL swap.
- `response_format: json_schema` (Pydantic schema) worked first try on Ultra and Lightning; no need for the json_object fallback.

## Nebius Serverless Endpoints

## Nebius Serverless Jobs

## Nemotron 3 Ultra

- First test (short watchdog-style prompt): 93 in / 360 out tokens, 1.5 s, $0.0012. Faster than we expected for a 550B model.

## Nemotron 3.5 Lightning

- Oct 25: in number extraction from news, Lightning turned vague phrases into exact numbers ("thousands" → 3,000, "tens of thousands" → 30,000). Super did not. We now verify every number against the quote in code.
- Oct 25: Tamil translation of announcements mixed in Korean characters and flipped left/right; Hindi was fine.
- First test (same prompt): 93 in / 605 out tokens, 3.3 s, $0.00015. Used more output tokens than Ultra for a 2-sentence answer (likely hidden reasoning); still very cheap.

## Nemotron 3.5 Super VL

## Tavily

- Oct 25 (Navika): turnout estimator. Key → first working search in minutes; `tavily-python` 0.8.5 has `start_date`/`end_date`, which made a "news published before the event" backtest possible (better than `time_range`).
- `topic="news"` was strongly US/UK-centric: for a Tamil Nadu rally it returned the London march, NPR, CNN and MLB. `topic="general"` + `country="india"` found The Hindu, NDTV, New Indian Express, Deccan Herald.
- `include_domains` (Indian outlets) on `news` returned pages whose scraped content included sidebar headlines from weeks later, so date filtering doesn't guarantee date-clean content.
- `general` results often have no `published_date`, so we couldn't check dates ourselves.
- `include_usage=True` showing credits per call was useful for budgeting. 12 credits for a full day of experiments.
