# Breathing Room dashboard

Next.js 15 + React 19 + Tailwind CSS 4. One page, three panels (Sense · Imagine · Act), all fed live from the shared backend.

## Run it

Needs Node.js 20+ and the backend running (`uvicorn backend.app:app --port 8000` from the repo root).

```bash
cd dashboard
npm install
npm run dev -- -p 3100
```

Open http://localhost:3100. (Port 3000 is reserved by Windows on some laptops, hence 3100.)

The backend address defaults to `http://localhost:8000`. To change it, copy `.env.example` to `.env.local` and set `NEXT_PUBLIC_BACKEND_URL`.

To see data without the real slices, run the fake publishers from the repo root: `uvicorn imagine.fake_imagine:app --port 8002`, `python -m sense.fake_sense`, `python -m act.fake_act --every 20`.

## How it fits together

| File | Owner | What |
|---|---|---|
| `lib/bus.tsx` | shared | One WebSocket to `GET /ws` (reconnects on its own). Keeps the latest state per topic. Every panel calls `useBus()`. Also `post()` for backend calls. |
| `lib/types.ts` | shared | TypeScript copy of `common/contracts.py`. Change both together, only with team agreement. |
| `lib/thresholds.ts` | shared | Density / danger colours (same numbers as `common/thresholds.json`). |
| `components/ui.tsx` | shared | `Panel`, `Section`, `Pill`, `Sparkline`, so the panels look like one product. |
| `components/SensePanel.tsx` | Shirali | Placeholder table; replace with the blurred frame + heatmap (S10). |
| `components/ImaginePanel.tsx` | Ananya | Placeholder table; replace with the venue map + fan chart (I08). |
| `components/ActPanel.tsx` | Navika | Situation, AI progress, gate-closure approvals, chosen plan, officers, announcements, reports, cost per decision, call-note box (A09). |

**Adding to your panel:** read what you need from `useBus()`, e.g. `const { zones, forecast } = useBus();`. You never need to touch the WebSocket code. The "Raw messages (debug)" box at the bottom of the page shows every message as it arrives.

**Backend calls the dashboard makes:** `POST /operator/report` (call notes) and `POST /operator/approve` (Approve / Reject a gate closure).
