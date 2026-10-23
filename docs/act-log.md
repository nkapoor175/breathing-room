# Act slice log (Navika)

Running log of what got done, what was decided and why, what's blocked, and what's next.
Newest day at the top. Task IDs refer to spec Section 11.4.

## Status at a glance

| Task | What | Status |
|---|---|---|
| Skeleton | Repo, contracts, helpers, backend relay, fake publishers (spec 8.3) | ✅ Done Oct 23 |
| A01 | `common/llm.py` working, model IDs confirmed, `fake_act.py` | ✅ Software done Oct 23 · ⏳ gateway MAC |
| A02 | Watchdog | ⏳ Next (was due Oct 22) |
| A03 | Planner + executor skeleton | ⏳ Due Oct 23–24 |
| A04 | Report fusion | Oct 24 |
| A05 | Telegram officer bot | Oct 25 |
| A06 | Announcements (en/ta/hi) | Oct 25 |
| A07 | Tavily turnout estimator | Oct 26 |
| A08 | Gateway, gate sign, serial bridge | Oct 26 |
| A09 | Act dashboard panel | Oct 27 |
| A10 | Devpost write-up + tool feedback | Oct 29 |

---

## Fri Oct 23

### Done
- **Created the GitHub repo** [nkapoor175/breathing-room](https://github.com/nkapoor175/breathing-room) (public) and pushed the Section 8.3 skeleton:
  - Apache 2.0 `LICENSE`, folder layout from 8.1, `.gitignore` (blocks `.env`, video, model weights), `.env.example`, `requirements.txt`
  - `common/contracts.py`, `llm.py`, `bus.py` copied verbatim from Section 7, plus `timeutil.py`, `thresholds.json` (caution 4.0, danger 5.0), `check_models.py`
  - `backend/app.py`: WebSocket `/ws` relaying every `br/#` message, `POST /results`, `POST /operator/report` → `br/report_raw`
  - Fake publishers: `act/fake_act.py` (mine), plus starter stubs `sense/fake_sense.py` and `imagine/fake_imagine.py` (with a fake `/score` on port 8002) for Shirali and Ananya to replace
  - Planner, watchdog and report-extract prompts copied from the spec into `act/prompts/`
  - `firmware/common/espnow_msg.h` (channel 1, 200-byte limit, placeholder gateway MAC)
  - `tests/test_contracts.py`: all Section 7.3 example messages parse (6 tests pass)
- **MQTT broker** set up on EMQX Cloud Serverless (see decisions). Users `sense`, `imagine`, `act` created. Round-trip publish/subscribe tested from my laptop.
- **End-to-end skeleton test**: backend + all three fake publishers running; a WebSocket client received `zone_state`, `plan`, `status`, `cost`, `officer`, `announce`, `device/gate-*`. Fake `/score` and `/operator/report` respond.
- **A01 Token Factory**: claimed $25 promo credits, created API key. `check_models` confirmed all four spec model IDs exist as written. `json_schema` structured output works on Ultra and Lightning (first test: Ultra 1.5 s / $0.0012, Lightning 3.3 s / $0.00015).
- Sent Shirali and Ananya the repo link, setup steps and their broker logins.

### Decisions
- **Broker: EMQX Cloud Serverless instead of HiveMQ Cloud.** HiveMQ no longer offers a free hosted tier (only Starter at ~$249/month with a 15-day trial ending before judging, or self-hosted Docker that teammates and judges couldn't reach). EMQX Serverless is free (1M session minutes, 1 GB/month), TLS on 8883, spend limit set to $0, so it can never bill. `common/bus.py` works unchanged. Not a data-contract change; team informed. Host: `g96ca606.ala.asia-southeast1.emqxsl.com` (Asia-Pacific).
- **Broker users are named by slice** (`sense`, `imagine`, `act`), not by person.
- **`common/__init__.py` loads `.env`** with python-dotenv so every script picks up keys without extra code. Small addition on top of the spec's helpers; behaviour otherwise identical.
- **Sense dependencies (torch, lwcc, OpenCV) kept out of the shared `requirements.txt`**, because lwcc may pin an old torch (spec 9.5). Shirali keeps them in her own requirements/venv.
- **Kept `json_schema` output** (not the json_object fallback), since it works on both models.

### Observations
- Lightning used ~600 output tokens for a 2-sentence answer, so it probably reasons before replying. Still cheap; watch latency in the Watchdog.
- Ultra was faster than expected (1.5 s on a short prompt). Real planning calls will be ~10k tokens in, so expect longer.

### Blocked / waiting
- **Gateway MAC** (rest of A01): need to flash the gateway ESP32 and post its MAC so Shirali's buttons can send to it. Needs the board plus my esp32 board-package version.
- **Dashboard shell (Next.js)**: no owner yet; asked in team chat.

### Next
- A02 Watchdog: rules + 60 s cooldown + Lightning summary, tested against the fake forecast.
- A03 Planner: Ultra → 3 plans, `validate_plan`, `baseline_plan`, parallel scoring, choose, publish.
