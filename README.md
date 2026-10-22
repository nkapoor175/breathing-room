# Breathing Room

AI that stops crowd crushes before they start: it reads crowd video, simulates the next 15 minutes, and moves police, gates and announcements early. Built on NVIDIA Nemotron and Nebius.

Entry to the Nebius × NVIDIA Global AI Hackathon, Physical AI track. Built from scratch during the submission period. License: [Apache 2.0](LICENSE).

> Skeleton README. Ananya owns the final version (spec task I09).

## Quick start (development)

Requires Python 3.11.

```bash
py -3.11 -m venv .venv
.venv\Scripts\activate          # Windows  (source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
copy .env.example .env          # then fill in your own keys - never commit .env
```

Confirm the Nemotron model IDs on Token Factory:

```bash
python -m common.check_models
```

Run the shared backend and the fake publishers (each in its own terminal):

```bash
uvicorn backend.app:app --port 8000 --reload
uvicorn imagine.fake_imagine:app --port 8002
python -m sense.fake_sense
python -m act.fake_act --every 20
```

Watch the live stream at `ws://localhost:8000/ws`.

## Layout

| Folder | Owner | What |
|---|---|---|
| `common/` | all | contracts, LLM helper, MQTT helper |
| `backend/` | all | WebSocket relay, `/results`, `/operator/report` |
| `sense/` | Shirali | video → zone density and flow |
| `imagine/` | Ananya | venue twin, simulator, forecasts, `/score` |
| `act/` | Navika | watchdog, planner, executor, Telegram, Tavily, serial bridge |
| `firmware/` | Shirali, Navika | ESP32 buttons, gateway, gate sign |
| `dashboard/` | all | Next.js dashboard, one panel each |
