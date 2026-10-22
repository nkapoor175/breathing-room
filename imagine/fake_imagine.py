"""Fake Imagine (stub for Ananya's I01/I05 - she owns and may replace it).

- Publishes a Forecast on br/forecast every 30 s: zone B's p_danger climbs 0.1 -> 0.7
  over 5 minutes, then loops.
- Serves a fake Imagine API on port 8002: GET /forecast/latest, POST /score (random
  improvement over baseline), POST /score/baseline.

Run:  uvicorn imagine.fake_imagine:app --port 8002
"""
import asyncio, random, time
from contextlib import asynccontextmanager

from fastapi import FastAPI

from common.bus import make_client, publish
from common.contracts import Forecast, ScoreResult, ZoneForecast
from common.timeutil import now_iso

CLIMB_S = 300
latest: Forecast | None = None
t0 = time.time()


def p_danger_b() -> float:
    frac = ((time.time() - t0) % CLIMB_S) / CLIMB_S
    return round(0.1 + 0.6 * frac, 2)


def make_forecast() -> Forecast:
    p = p_danger_b()
    return Forecast(t=now_iso(), zones=[
        ZoneForecast(zone="A", p50_density=2.6, p90_density=3.2, p_danger=0.02),
        ZoneForecast(zone="B", p50_density=round(3.5 + 3 * p, 1), p90_density=round(4.5 + 3.5 * p, 1),
                     p_danger=p, minutes_to_danger=round(15 - 12 * p, 1) if p >= 0.05 else None),
        ZoneForecast(zone="C", p50_density=0.8, p90_density=1.1, p_danger=0.0),
        ZoneForecast(zone="D", p50_density=1.5, p90_density=2.0, p_danger=0.01),
    ])


async def forecast_loop(mq):
    global latest
    while True:
        latest = make_forecast()
        publish(mq, "br/forecast", latest)
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    mq = make_client("imagine-fake")
    mq.loop_start()
    task = asyncio.create_task(forecast_loop(mq))
    yield
    task.cancel()
    mq.loop_stop()


app = FastAPI(title="Fake Imagine API", lifespan=lifespan)


@app.get("/forecast/latest")
def forecast_latest():
    return latest or make_forecast()


@app.post("/score/baseline")
def score_baseline(body: dict):
    p = p_danger_b()
    return ScoreResult(plan_id="baseline", max_p_danger=p, min_minutes_to_danger=round(15 - 12 * p, 1),
                       zones=make_forecast().zones)


@app.post("/score")
def score(body: dict):
    plan_id = body.get("plan", {}).get("plan_id", "?")
    p = round(p_danger_b() * random.uniform(0.05, 0.6), 3)
    return ScoreResult(plan_id=plan_id, max_p_danger=p, min_minutes_to_danger=None if p < 0.05 else 12.0,
                       zones=[ZoneForecast(zone="B", p50_density=4.0, p90_density=4.7, p_danger=p)])
