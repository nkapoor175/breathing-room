# Breathing Room

**Predictive crowd-safety intelligence for safer public spaces.**

Breathing Room is a prototype that explores how AI-assisted crowd sensing, venue simulation, and ranked interventions can help identify potentially dangerous crowd conditions before they escalate.

Built for the **Nebius × NVIDIA Global AI Hackathon — Physical AI track**, using NVIDIA Nemotron and Nebius.

The prototype combines crowd-state inputs, a digital venue model, short-horizon forecasts, intervention scoring, and ranked recommendations in a web dashboard.

> **Project status:** Hackathon prototype. Forecasts and intervention scores are simulation-based and should not be treated as validated real-world safety predictions or autonomous emergency-response decisions.

## Features

- **Venue digital twin:** Represents zones, entry points, and connections between areas.
- **Crowd forecasting:** Simulates crowd conditions over a 15-minute horizon.
- **Intervention scoring:** Compares a baseline forecast with proposed actions.
- **Gate safety validation:** Rejects gate closures that disconnect zones from an outside route.
- **AI-assisted recommendations:** Generates and ranks candidate intervention plans, with fallback behavior when generation fails.
- **Web dashboard:** Displays venue information, forecasts, gate interventions, and ranked recommendations.
- **Backend API:** Provides endpoints for simulation, scoring, recommendations, and application integration.

## Tech stack

| Component | Technologies |
|---|---|
| Backend API | Python, FastAPI, Uvicorn |
| Data validation | Pydantic |
| AI integration | NVIDIA Nemotron, Nebius |
| Messaging | MQTT |
| Dashboard | Next.js, React, TypeScript |
| Testing | pytest, ESLint, TypeScript build checks |

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

Open `http://localhost:3000` in your browser.

### 5. Optional: start the shared backend and publishers

For the broader MQTT and WebSocket integration, use separate terminals from the repository root:

```bash
uvicorn backend.app:app --port 8000 --reload
```

```bash
python -m sense.fake_sense
```

```bash
python -m act.fake_act --every 20
```

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

The backend test suite previously passed **46 tests** in the development environment. Rerun the checks against the current checkout to verify its status.

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

## Team contributions

The project is developed collaboratively across sensing, simulation, action planning, firmware, and dashboard workstreams. Refer to the repository history and project documentation for implementation details and individual contributions.

## License

Licensed under the [Apache License 2.0](LICENSE).
