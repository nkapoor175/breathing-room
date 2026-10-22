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

def _now():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).isoformat()

def call_json(role: str, purpose: str, system: str, user: str, schema: type[BaseModel],
              images: list[str] | None = None, retries: int = 1, temperature: float = 0.2,
              on_cost=None) -> BaseModel:
    """Call a Nemotron model and return a validated Pydantic object."""
    content = user if not images else (
        [{"type": "text", "text": user}] +
        [{"type": "image_url", "image_url": {"url": u}} for u in images])
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": content}]
    rf = {"type": "json_schema",
          "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema()}}
    last_err = None
    for _ in range(retries + 1):
        t0 = time.time()
        resp = client.chat.completions.create(model=MODELS[role], messages=messages,
                                              temperature=temperature, response_format=rf)
        text = resp.choices[0].message.content or ""
        u = resp.usage
        usd = u.prompt_tokens / 1e6 * PRICES[role][0] + u.completion_tokens / 1e6 * PRICES[role][1]
        if on_cost:  # e.g. publish a CostEvent on br/cost
            on_cost({"t": _now(), "role": role, "purpose": purpose,
                     "prompt_tokens": u.prompt_tokens, "completion_tokens": u.completion_tokens,
                     "usd": round(usd, 6), "latency_s": round(time.time() - t0, 2)})
        try:
            return schema.model_validate_json(text)
        except ValidationError as e:
            last_err = e
            messages += [{"role": "assistant", "content": text},
                         {"role": "user", "content": f"Invalid JSON for the schema: {e}. Reply with corrected JSON only."}]
    raise RuntimeError(f"{role} returned invalid JSON: {last_err}")
