# Devpost submission: Breathing Room

**Track:** Physical AI · **Bonus:** Best Use of Tavily

**Elevator pitch (≤200 chars):**
AI that stops crowd crushes before they start: it reads crowd density, simulates the next 15 minutes, and moves police, gates and announcements early. Built on NVIDIA Nemotron and Nebius.

**Built from scratch during the submission period.**

---

## Inspiration

On the night of the Itaewon crush in Seoul, the first emergency call warning that the alley was dangerously crowded came at 18:34. The crush began around 22:15, and 159 people died. At the 2025 Maha Kumbh, AI cameras sent surge alerts on time, and nearly 40 people still died, because police weren't where they were needed. At the Karur rally in 2025, the organizer had declared 10,000 people; reports before the rally already showed the same organizer's previous rally drawing around 1 lakh.

The warnings were there each time. What was missing was turning them into a decision early enough to matter. **Spotting a surge isn't the same as preventing one.**

## What it does

Breathing Room watches a venue, predicts where it will become dangerous, and acts early:

1. **Sense:** people per square metre and movement for each zone, every 2 seconds, from camera counting or any crowd-count feed (the demo also runs on a simulated feed), plus "pushing here" / "someone fell" buttons for volunteers that work over an ESP-NOW radio mesh with no phone signal.
2. **Imagine:** a digital twin of the venue (a draft can be built from a photo of the site plan) and a simulation of the next 15 minutes, run 1,000 times, giving each zone's chance of danger and minutes to danger.
3. **Act:** when danger is coming, an AI planner (Nemotron 3 Ultra) proposes three plans using only the officers, gates and loudspeakers that actually exist. **Every plan is tested in the simulation before anything happens**, and a simple rule-based plan is always in the running. Then the safest plan is carried out:
   - officers get instructions on Telegram with "On my way" / "Arrived" buttons,
   - gate signs change, but closing a gate waits for a human to press **Approve**,
   - calm announcements go out in English, Tamil and Hindi.
4. **Listens to people, not just cameras:** call notes and Telegram messages in English, Tamil or Hindi become pins on the map.
5. **Checks the organizer's numbers:** before an event, Tavily searches the news and compares likely turnout with the declared crowd size. Using only news from before the Karur rally, it warns: *likely turnout up to 10× the declared 10,000*.

## How we built it

- **Python + FastAPI** services talking over **MQTT** (EMQX Cloud), a **Next.js** dashboard over a WebSocket, **Pydantic** data contracts shared by all three of us.
- **NVIDIA Nemotron on Nebius Token Factory** for every model call, with model routing:
  - **Nemotron 3 Ultra**: incident planning, and Tamil/Hindi translation of announcements.
  - **Nemotron 3.5 Lightning** (reasoning off): the watchdog's situation summary, ~1 s.
  - **Nemotron 3 Super** (reasoning off): turning call notes and Telegram messages into reports; extracting crowd numbers from news.
  - **Nemotron 3.5 Super VL**: site-plan photo → venue twin.
  - Each call's cost and latency is shown on the dashboard. A full decision costs about 1–2 cents.
- **Tavily** for the turnout check (country-filtered search in a date window, results cached).
- **NumPy** Monte Carlo crowd simulator (zones and links, density-dependent flow).
- **Telegram Bot API** for officers and volunteers; **ESP32 + ESP-NOW** for buttons and gate signs.
- The README lists the file and line of every model call.

## Challenges we ran into

- **Models making things up in safety-critical places.** In testing, Lightning and Super both turned "left" into "right" when translating announcements into Tamil, and Lightning mixed in Korean characters. We moved translation to Ultra and added a checker in code (right script, left/right not flipped, gate numbers kept); a language that fails is left out rather than broadcast. The checker caught a real Malayalam character in Ultra's Tamil during a live test.
- **Numbers from nowhere.** For the turnout check, Lightning turned "thousands of people" into 3,000 and "tens of thousands" into 30,000. Now every number must appear in a quote that appears in the article, or it's dropped.
- **Hidden reasoning.** With reasoning on, a Lightning call took 44 s and ran out of tokens with no answer. Turning it off for short jobs brought it to ~1 s.
- **Search that didn't know India.** Tavily's news search returned London and US stories for a Tamil Nadu rally; general search filtered to India found the right coverage.
- **"Before the event" isn't automatic.** Some pages dated before the Karur rally contained headlines from after it. In before-event mode we drop anything reported on the day.
- **Three slices, one system.** Our first full rehearsal on the real simulator found a venue mismatch, a mis-sized fake sensor feed and an API argument bug, all invisible in each slice's own tests.

## Accomplishments that we're proud of

- **The LLM never acts directly.** Plans are validated in code, simulated, compared with a rule-based plan, and gate closures need a human.
- About **10 seconds** from "danger coming" to a published plan, at about **1–2 cents** per decision.
- A **Telegram** loop tested on a real phone: instruction → On my way → Arrived on the dashboard in seconds.
- Announcements in **Tamil and Hindi** that are checked before they can be played.
- A turnout warning for Karur built **only from news published before the rally**.

## What we learned

- "The LLM proposes, the simulation decides" is a much easier system to trust, and to explain, than an LLM that acts.
- Test the model choice per job: the cheapest model was fine for summaries and wrong for Tamil directions.
- Check everything a model outputs that a person will act on: quotes, numbers, directions.

## What's next

- Run the counting model on an edge device at the venue so it keeps working without internet.
- Calibrate the simulator against real crowd data and publish lead-time and false-alarm numbers.
- Pilot with a real event team: one venue, one evening, operators in the loop.
- Live location of officers on the map; more Indian languages.

---

## Built with

python, fastapi, pydantic, numpy, mqtt, emqx, next.js, react, typescript, tailwind, nvidia-nemotron, nebius-token-factory, tavily, telegram, esp32, esp-now, arduino

## Links

- Repo: https://github.com/nkapoor175/breathing-room (Apache 2.0)
- Video: *(YouTube link)*
- Tool feedback: `docs/feedback.md`
