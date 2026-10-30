import os, json, time, datetime
from openai import OpenAI
from pydantic import BaseModel, ValidationError

client = OpenAI(base_url="https://api.tokenfactory.nebius.com/v1/",
                api_key=os.environ["NEBIUS_API_KEY"])

# Confirm these IDs on Day 1 with client.models.list()  (python -m common.check_models)
MODELS = {
    "ultra": "nvidia/Nemotron-3-Ultra-550b-a55b",
    "lightning": "nvidia/Nemotron-3_5-Lightning",
    "vl": "nvidia/Nemotron-3.5-Super-VL",
    "super": "nvidia/nemotron-3-super-120b-a12b",
}

# USD per 1M tokens (input, output), from the Token Factory catalog. Re-check before the demo.
PRICES = {"ultra": (1.00, 3.00), "lightning": (0.06, 0.24), "vl": (0.30, 0.90), "super": (0.30, 0.90)}

# Pass as extra_body= to turn off hidden reasoning. Tested Oct 23: Lightning with reasoning
# on took up to 44 s and could hit the token limit with no answer; off, it answers in ~2 s.
NO_THINK = {"chat_template_kwargs": {"enable_thinking": False}}


def _now():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).isoformat()


def call_json(
    role: str,
    purpose: str,
    system: str,
    user: str,
    schema: type[BaseModel],
    images: list[str] | None = None,
    retries: int = 2,
    temperature: float = 0.2,
    on_cost=None,
    extra_body: dict | None = None,
    max_tokens: int | None = 8192,
) -> BaseModel:
    """Call a Nemotron model and return a validated Pydantic object.

    extra_body: extra request fields, e.g. NO_THINK.
    max_tokens: cap on the reply (hidden reasoning counts too). Ultra's planner used
    3,665 tokens in testing, so keep this well above that.
    Transient API errors and empty or invalid replies are retried with backoff."""

    if role not in MODELS:
        raise ValueError(f"Unknown model role: {role}")

    content = user if not images else (
        [{"type": "text", "text": user}]
        + [
            {"type": "image_url", "image_url": {"url": url}}
            for url in images
        ]
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": content},
    ]

    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": schema.__name__,
            "schema": schema.model_json_schema(),
        },
    }

    last_err = None

    for attempt in range(retries + 1):
        started = time.time()

        try:
            resp = client.chat.completions.create(
                model=MODELS[role],
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
                extra_body=extra_body,
            )
        except Exception as exc:
            # Retry transient provider/API failures, then report the real error.
            if attempt < retries:
                time.sleep(min(2 ** attempt, 4))
                continue
            raise RuntimeError(
                f"{role} API request failed for {purpose}: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        usage = resp.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0

        cost = (
            prompt_tokens / 1_000_000 * PRICES[role][0]
            + completion_tokens / 1_000_000 * PRICES[role][1]
        )

        if on_cost:  # e.g. publish a CostEvent on br/cost
            on_cost({
                "t": _now(),
                "role": role,
                "purpose": purpose,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "usd": round(cost, 6),
                "latency_s": round(time.time() - started, 2),
            })

        choice = resp.choices[0] if resp.choices else None
        message = choice.message if choice else None
        text = (message.content or "").strip() if message else ""

        if not text:
            finish_reason = choice.finish_reason if choice else "no_choice"
            last_err = (
                f"Empty response from {role}; "
                f"finish_reason={finish_reason!r}; "
                f"completion_tokens={completion_tokens}"
            )
        else:
            try:
                return schema.model_validate_json(text)
            except (ValidationError, ValueError) as exc:
                last_err = (
                    f"{type(exc).__name__}: {exc}; "
                    f"response_preview={text[:300]!r}"
                )

        if attempt < retries:
            messages = [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": (
                        content
                        if isinstance(content, str)
                        else json.dumps(content)
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Your previous response was unusable: {last_err}\n"
                        f"Return one complete JSON object matching this schema, "
                        f"with no markdown or commentary:\n"
                        f"{json.dumps(schema.model_json_schema())}"
                    ),
                },
            ]
            time.sleep(min(2 ** attempt, 4))

    raise RuntimeError(
        f"{role} failed to return valid {schema.__name__} JSON "
        f"for {purpose} after {retries + 1} attempts: {last_err}"
    )
