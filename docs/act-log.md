# Act slice log (Navika)

Running log of what got done, what was decided and why, what's blocked, and what's next.
Newest day at the top. Task IDs refer to spec Section 11.4.

## Status at a glance

| Task | What | Status |
|---|---|---|
| Skeleton | Repo, contracts, helpers, backend relay, fake publishers (spec 8.3) | ✅ Done Oct 23 |
| A01 | `common/llm.py` working, model IDs confirmed, `fake_act.py` | ✅ Software done Oct 23 · ⏳ gateway MAC |
| A02 | Watchdog | ✅ Done Oct 23 (PR `act/watchdog`) |
| A03 | Planner + executor skeleton | ✅ Done Oct 23 (PR `act/planner`) |
| A04 | Report fusion | ✅ Done Oct 23 (PR `act/reports`) |
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
- **A02 Watchdog** (`act/watchdog.py`): the three spec rules, 60 s cooldown, severity-5 bypass, Lightning for free-text reports and the situation summary. Publishes the trigger on `br/status` (`source: "watchdog"`, `text`, `urgency`, `reasons`) and calls an `on_trigger` hook where the Planner will plug in. 12 unit tests (`tests/test_watchdog.py`), 18 tests total pass.
  - **Live test** over the real broker with fake Imagine/Sense and real Lightning: zone B climbed 0.10 → 0.34; the Watchdog fired **once** at the crossing and stayed quiet at 0.40 (spec "done when" met). Summary: "Zone B has a 34% chance of dangerous density in about 11 minutes. Officers must monitor crowd pressure and enforce capacity limits in that zone." Cost $0.0008.
- **A03 Planner + executor skeleton**:
  - `act/planner.py`: `build_context`, Ultra → 3 plans, `validate_plan` (repair or drop), `baseline_plan` (rule-based "RB"), parallel `/score` + `/score/baseline`, `choose`, "Request backup" above 30% danger, progress on `br/status`.
  - `act/executor.py`: officers (from `act/officers.json`), gate `DeviceCommand`s, announcements (English only until A06), hold-inflow instructions. Simulated officers go assigned → on_the_way → arrived and change zone. Telegram (A05) plugs into `notify`.
  - `act/run_act.py`: one process, Watchdog → Planner → Executor. Replans run on a worker thread so a slow Ultra call doesn't block the watchdog.
  - `data/demo-venue.json` (zones A–D, 6 links, 2 entries, 12 officers) as a placeholder venue; fake Imagine now serves it on `GET /venue/{id}`.
  - 27 new tests (45 total pass).
  - PR #1 (Watchdog) merged. PR #2 (Planner) open.
  - **Live test with real Ultra** (fake Imagine/Sense, real broker): zone B crossed 0.3 → watchdog fired → Ultra returned 3 plans in 10.8 s ($0.0125) → 4 plans scored → **plan published 11.3 s after the trigger** (target: under 60 s). Winner P3 "Reinforce Zone B with officers": move 2 officers C → B + announce "Use both exits". Safe in 96% of futures vs 62% doing nothing (fake scores). Ultra's P1 had a hold_inflow with no zone and no minutes, and `validate_plan` repaired it. Executor messages (officer statuses, gate-3 stop, announcement) verified over the broker.
- **Reasoning on/off test (Lightning).** Same Tamil report, 4 settings: default = **44 s, hit the 8,192-token limit, returned nothing**; `chat_template_kwargs.enable_thinking=False` = **0.4 s**, valid JSON; `reasoning_effort=low` and `/no_think` in the prompt = 22–25 s and badly mistranslated the Tamil. → added `NO_THINK` + optional `extra_body` to `common/llm.py`; Watchdog now uses it: **summary in ~1 s instead of 10–12 s** (51 output tokens instead of ~2,600).
- **Model comparison for report extraction** (6 messages: 2 Tamil, 2 Hindi, 2 English, reasoning off): Lightning 5/6 (put a Tamil "stage front" message in the overflow ground), **Super 6/6, 2.0 s avg**, Ultra 5/6.
- **A04 report fusion** (`act/reports.py`): `br/report_raw` → Nemotron Super (reasoning off) → `Report` on `br/report`. `ReportFusion.fuse()` is what the Telegram bot (A05) will call. 12 new tests (57 total pass).
  - **Live test** through the real path (dashboard form → backend `/operator/report` → `br/report_raw` → fusion → `br/report`): 4/4 published, all correct. English "crushed… a girl fainted" → A/5; Hindi "pushing near gate 2" → B/4; Tamil "very crowded at the stage front" → A/3; a note with no location used the operator's zone pick (D).

### Decisions
- **Broker: EMQX Cloud Serverless instead of HiveMQ Cloud.** HiveMQ no longer offers a free hosted tier (only Starter at ~$249/month with a 15-day trial ending before judging, or self-hosted Docker that teammates and judges couldn't reach). EMQX Serverless is free (1M session minutes, 1 GB/month), TLS on 8883, spend limit set to $0, so it can never bill. `common/bus.py` works unchanged. Not a data-contract change; team informed. Host: `g96ca606.ala.asia-southeast1.emqxsl.com` (Asia-Pacific).
- **Broker users are named by slice** (`sense`, `imagine`, `act`), not by person.
- **`common/__init__.py` loads `.env`** with python-dotenv so every script picks up keys without extra code. Small addition on top of the spec's helpers; behaviour otherwise identical.
- **Sense dependencies (torch, lwcc, OpenCV) kept out of the shared `requirements.txt`**, because lwcc may pin an old torch (spec 9.5). Shirali keeps them in her own requirements/venv.
- **Kept `json_schema` output** (not the json_object fallback), since it works on both models.
- **Watchdog rule 1 is edge-triggered** (fires when a zone *becomes* at risk, not while it stays at risk) and **rule 3 fires at most once per plan**. Why: forecasts arrive every 30 s, so with only the 60 s cooldown the watchdog would replan every minute; the spec's "done when" says fire once. A zone that recovers and becomes risky again fires again.
- **Triggers inside the cooldown are deferred, not dropped**: they fire when the cooldown ends. Otherwise an edge-triggered event (e.g. zone A newly at risk 30 s after zone B) would be lost.
- **Button presses only count through rule 2** (no Lightning call): their text is fixed, so an LLM adds nothing. Free text from Telegram / call notes goes to Lightning.
- **Rule 3 only compares forecasts made after the plan**, so a forecast computed before the plan existed can't flag it as failing.
- **If Lightning fails, the watchdog still fires** with the rule text as the summary. Safety logic never depends on the LLM being up.
- **`validate_plan` repairs what is safe to repair** (officer count clamped to who's there, hold_inflow capped at 20 min or defaulted to 10, hold zone corrected to where the entry leads, missing announce languages → en/ta/hi) and **drops** anything unknown or unsafe (made-up zone/link/entry ids, announce without a loudspeaker, more than 6 actions, gate changes that leave an occupied zone with no path to outside). The "no way out" check is a path search over open links; a zone with a 0 count may be closed off.
- **Ultra gets 40 s**, then the planner continues with whatever it has (worst case: only the rule-based plan). This keeps the full replan inside the 60 s target. `PLANNER_MODEL=super` switches to the faster backup model for filming (spec 11.5).
- **Rule-based plan id is "RB"** so the dashboard can show when the simple plan beat the AI.
- **`/score` request's `officers` field = `{"A": 4, "B": 2, ...}`** (officers per zone). The spec left it as `{...}`; Ananya to confirm.
- **Opening a gate sends arrow "up" (go)**. The spec says "the arrow pointing towards the zone people should use", but the venue has no geometry telling us left vs right yet. Revisit with the real gate sign (A08).
- **Report extraction uses Nemotron 3 Super, not Lightning** (spec said Lightning). Why: in the 6-message test only Super got every zone and severity right, and it was the fastest (2.0 s). A wrong zone on a "someone fell" report sends officers to the wrong place; Super costs ~$0.0002 per report, so accuracy wins. That fits the spec's own routing rule ("the cheapest model that does it well"). `REPORT_MODEL=lightning` switches back. Lightning stays on the watchdog summary, where it's accurate.
- **Reasoning off for the watchdog and report extraction; on for the Ultra planner.** Short extraction/summary jobs don't need it and it made Lightning unusably slow; planning is the one job where thinking helps, and Ultra's 10.8 s fits the budget.
- **`common/llm.py` change is backward compatible**: new optional `extra_body` (default `None`) + a `NO_THINK` constant. Existing calls (Ananya's VL) behave exactly as before. Team told in the PR.
- **A report is never dropped.** If the model call fails, it's published anyway with a keyword severity (English, Hindi and Tamil words for fell / fainted / can't breathe → 5; push / climb / barricade → 4; otherwise 3 so a human looks) and the original text.
- **A zone the operator picks on the dashboard form overrides the model's guess**; a zone id the model invents is discarded.
- **Report prompt got one extra rule**: "if several things are described, use the most severe one". The first Tamil test said "pushing… someone fell" and came back as severity 3.
- **Watchdog context key renamed `densities_ppm2` → `density_people_per_m2`**: Lightning was copying "ppm" into the summary for officers.
- **Context is snapshotted on the watchdog loop** at trigger time and handed to the worker thread, so the planner never reads data the loop is changing. A trigger during a running replan queues exactly one follow-up replan.

### Observations
- Lightning used ~600 output tokens for a 2-sentence answer, so it probably reasons before replying. Still cheap; watch latency in the Watchdog.
- Ultra was faster than expected (1.5 s on a short prompt). Real planning calls will be ~10k tokens in, so expect longer.
- Lightning took **12 s** for the watchdog summary in the live test (vs 3 s in the morning test). It counts toward the 60 s replan target. If it stays slow: start the Planner in parallel with the summary instead of after it.
- In the planner live test Lightning used **2,622 output tokens for a 2-sentence summary** (10 s), almost all hidden reasoning. **Fixed** with `NO_THINK` (see above).
- Ultra sometimes omits fields (`zone`, `minutes`) in actions; the validator catches it. Ultra also sent `langs: ["en"]` only; A06 translation will fill Tamil and Hindi regardless.

### Blocked / waiting
- **Gateway MAC** (rest of A01): need to flash the gateway ESP32 and post its MAC so Shirali's buttons can send to it. Needs the board plus my esp32 board-package version.
- **Dashboard shell (Next.js)**: no owner yet; asked in team chat.

### Next
- Ask Ananya to confirm the `officers` shape in `POST /score` and to replace `data/demo-venue.json` with the real venue.
- A05 Telegram officer bot and A06 announcements (Oct 25). A06 translation should also use `NO_THINK`; have a native speaker check Tamil and Hindi lines.
