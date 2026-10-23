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

- First test (same prompt): 93 in / 605 out tokens, 3.3 s, $0.00015. Used more output tokens than Ultra for a 2-sentence answer (likely hidden reasoning); still very cheap.

## Nemotron 3.5 Super VL

## Tavily
