# Breathing Room

**Predictive crowd-safety intelligence for safer public spaces.**

Breathing Room is a prototype that explores how AI-assisted crowd sensing, venue simulation, and ranked interventions can help identify potentially dangerous crowd conditions before they escalate.

Built for the **Nebius × NVIDIA Global AI Hackathon — Physical AI track**, using NVIDIA Nemotron on Nebius Token Factory, plus Tavily. **Built from scratch during the submission period.**

> Spotting a surge isn't the same as preventing one. Breathing Room reads crowd density, simulates the next 15 minutes 1,000 times, and has an AI planner propose plans that are **tested in the simulation before anything happens**: officers get instructions on Telegram, gate signs change (after a human approves), and calm announcements go out in English, Tamil and Hindi.

The prototype combines crowd-state inputs, a digital venue model, short-horizon forecasts, intervention scoring, and ranked recommendations in a web dashboard.

> **Project status:** Hackathon prototype. Forecasts and intervention scores are simulation-based and should not be treated as validated real-world safety predictions or autonomous emergency-response decisions.

## Features

**Imagine: venue twin and simulation**
- **Venue digital twin:** zones, entry points and connections; a draft can be built from a site-plan photo with Nemotron Super VL.
- **Crowd forecasting:** Monte Carlo simulation of the next 15 minutes (1,000 runs): chance of danger and minutes to danger per zone.
- **Intervention scoring:** every candidate plan is simulated against "do nothing".
- **Itaewon backtest:** a clearly labelled *simulated reconstruction* (see `docs/itaewon_backtest.md`).

**Act: decide and act** (`act/`)
- **Watchdog:** fires when a zone newly reaches ≥30% chance of danger within 15 min, or a serious report comes from a crowded zone. Nemotron Lightning writes the situation summary.
- **Planner:** Nemotron Ultra proposes 3 plans using only the officers, gates and loudspeakers that exist. Code checks every plan (made-up ids, more officers than exist, gate closures that would trap people, panic words) and a rule-based plan is always added. All are scored in the simulator; the safest wins. About 10 s from danger to a published plan.
- **Human in the loop:** closing a gate waits for an operator's **Approve** on the dashboard; no answer in 2 min = no change.
- **Officers and volunteers on Telegram:** instructions with [On my way] / [Arrived] buttons; volunteers report in English, Tamil or Hindi.
- **Report fusion:** call notes and Telegram messages → zone + severity + English summary.
- **Announcements in English, Tamil and Hindi:** each translation is checked in code (right script, left/right not flipped, gate numbers kept) before it can be played.
- **Turnout check with Tavily:** compares likely turnout from the news with the organizer's declared crowd size; every number is checked against its quote.

**Dashboard** (`dashboard/`): `/` live operations view (Act panel: situation, plan card with "safe in X% of futures", officers, announcements, reports, cost per decision, turnout card, approvals) and `/judge` simulation view (venue, forecasts, gate interventions, ranked recommendations).

## Tech stack

| Component | Technologies |
|---|---|
| Backend API | Python, FastAPI, Uvicorn |
| Data validation | Pydantic |
| AI integration | NVIDIA Nemotron, Nebius |
| Messaging | MQTT |
| Dashboard | Next.js, React, TypeScript |
| Testing | pytest, ESLint, TypeScript build checks |

## How we use NVIDIA Nemotron, Nebius Token Factory and Tavily

Every model call goes through **Nebius Token Factory** (`https://api.tokenfactory.nebius.com/v1/`) via one helper, `common/llm.py` line 78 (`client.chat.completions.create`), which validates the JSON reply and logs the cost of each call (shown on the dashboard).

| Model (Token Factory) | What it does | Where (file:line) |
|---|---|---|
| **Nemotron 3 Ultra** `nvidia/Nemotron-3-Ultra-550b-a55b` | Proposes 3 incident plans | `act/planner.py:304` |
| **Nemotron 3 Ultra** | Translates announcements to Tamil and Hindi | `act/announce.py:123` |
| **Nemotron 3.5 Lightning** `nvidia/Nemotron-3_5-Lightning` | Watchdog: situation summary, judges free-text reports | `act/watchdog.py:187` |
| **Nemotron 3 Super** `nvidia/nemotron-3-super-120b-a12b` | Report fusion (call notes, Telegram) → zone + severity | `act/reports.py:90` |
| **Nemotron 3 Super** | Extracts crowd numbers from news for the turnout check | `act/turnout.py:222` |
| **Nemotron 3 Super** | Ranked recommendations on the `/judge` page | `act/recommend.py:250` |
| **Nemotron 3.5 Super VL** `nvidia/Nemotron-3.5-Super-VL` | Site-plan photo → venue twin (and one correction pass) | `imagine/fake_imagine.py:537`, `:576` |
| (all models) | Model ID check | `common/check_models.py:8` |

| Other runtime API | What it does | Where |
|---|---|---|
| **Tavily** search | 3 news searches per turnout estimate | `act/turnout.py:210` (client created at `:202`) |

**Model routing:** Ultra only where a real decision or a safety-critical translation is needed; Lightning and Super (reasoning off) for frequent short jobs. We switched some jobs away from the planned model after testing: Lightning flipped "left"/"right" in Tamil and turned "thousands" into exact numbers, so translation uses Ultra and number extraction uses Super. Details and numbers: `docs/act-log.md`, tool feedback: `docs/feedback.md`.

## Safety by design

- **The LLM never acts directly.** Every plan is validated in code and simulated before it is carried out, and a simple rule-based plan is always in the running.
- **Humans approve gate closures.** No answer means no change.
- **No made-up instructions:** announcements and turnout numbers are checked in code; anything that fails is dropped, not sent.
- **Privacy:** counts and movement only, no face recognition, raw video never stored.

## Quick start

### Prerequisites

- Python 3.11
- Node.js and npm
- Git
- Environment credentials configured for the services you intend to use

### 1. Clone the repository

```bash
git clone https://github.com/nkapoor175/breathing-room.git
cd breathing-room
```

### 2. Set up the Python environment

**Windows PowerShell:**

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

**macOS/Linux:**

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Configure the required environment variables in `.env`. Never commit API keys, passwords, or broker credentials.

### 3. Start the simulation API

From the repository root, activate the virtual environment and run:

```bash
uvicorn imagine.fake_imagine:app --host 127.0.0.1 --port 8002 --reload
```

The API is available at `http://127.0.0.1:8002`.

Explore its endpoints at `http://127.0.0.1:8002/docs`.

### 4. Start the dashboard

Open a separate terminal:

```powershell
cd dashboard
npm install
npm run dev
```

Open `http://localhost:3000` (operations view) and `http://localhost:3000/judge` (simulation view). If Windows has port 3000 reserved, run `npm run dev -- -p 3100` instead. Set `NEXT_PUBLIC_BACKEND_URL` / `NEXT_PUBLIC_IMAGINE_URL` in `dashboard/.env.local` if the backend or the Imagine API run elsewhere.

### 5. Optional: start the shared backend and publishers

For the broader MQTT and WebSocket integration, use separate terminals from the repository root:

```bash
uvicorn backend.app:app --port 8000 --reload
```

```bash
python -m sense.fake_sense
```

```bash
python -m act.run_act          # Watchdog -> Planner -> executor (+ Telegram bot if TELEGRAM_BOT_TOKEN is set)
```

```bash
python -m act.reports          # call notes from the dashboard -> reports
```

```bash
python -m act.turnout --event "TVK Vijay rally" --organizer "TVK (Tamilaga Vettri Kazhagam), leader Vijay" --city Karur --date 2025-09-27 --declared 10000 --before-event --publish
```

Start the Imagine API (step 3) **before** these, so they load its venue. `python -m act.fake_act --every 20` publishes fake plans instead of running the real planner.

The WebSocket stream is available at `ws://localhost:8000/ws`.

These services may require valid environment variables and MQTT broker credentials. Configure them before starting the publishers.

### 6. Check the configured AI models

```bash
python -m common.check_models
```

This diagnostic checks the configured model identifiers. Successful model access also depends on valid credentials and provider availability.

## Using the dashboard

1. Open the dashboard and inspect the venue and zone forecasts.
2. Review the baseline crowd-risk forecast.
3. Select a gate and evaluate a proposed intervention.
4. Compare the baseline score with the intervention score.
5. Inspect the ranked recommendations and their explanations.
6. Try an unsafe gate closure to verify that the safety validator rejects it.

Use the simulated venue for development and demonstration. Do not interpret simulated scores as guarantees of real-world safety.

## Testing

Run the backend tests from the repository root:

```powershell
pytest -q
```

Run frontend checks:

```powershell
cd dashboard
npm run lint
npm run build
```

157 backend tests pass on the current `main` (Imagine + Act + shared).

## Repository layout

| Directory | Responsibility |
|---|---|
| `common/` | Shared contracts, LLM helpers, messaging utilities, and gate-safety validation |
| `backend/` | Shared backend, WebSocket relay, and operator-facing endpoints |
| `sense/` | Crowd-sensing components and fake sensing publisher |
| `imagine/` | Venue model, simulation, forecasts, scoring API, and backtesting utilities |
| `act/` | Intervention planning, recommendation logic, and action-related components |
| `firmware/` | ESP32 firmware and hardware-facing components |
| `dashboard/` | Next.js web interface |

## Limitations and future work

- Validate forecasts against representative real-world crowd data.
- Evaluate false positives, false negatives, and forecast uncertainty.
- Test performance under larger venues and heavier message loads.
- Improve observability, fault handling, and deployment configuration.
- Validate any real-world intervention with qualified safety personnel before operational use.

The current prototype is intended for research, experimentation, and demonstration—not as a replacement for trained crowd-safety teams or established emergency procedures.

## Team

| Person | Slice | What they built |
|---|---|---|
| **Shirali** | Sense | Crowd sensing: cameras, counting, volunteer buttons |
| **Ananya** | Imagine | Venue twin, crowd simulator, forecasts and scoring, Itaewon backtest, `/judge` view, README |
| **Navika** | Act | Watchdog, planner, executor, approvals, Telegram bot, report fusion, Tamil/Hindi announcements, Tavily turnout check, operations dashboard, ESP-NOW gateway |

## License

Licensed under the [Apache License 2.0](LICENSE).
