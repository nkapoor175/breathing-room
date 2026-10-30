"use client";

// SHIRALI owns this panel (spec S10). This is a working placeholder built on the shared bus:
// replace it with the blurred frame + heatmap from GET /frame/latest.jpg, zone outlines,
// direction arrows and volunteer-button pins.

import { ago, useBus, useNow } from "@/lib/bus";
import { DANGER, TONE, densityTone } from "@/lib/thresholds";
import { Empty, Panel, Pill, Section, Sparkline } from "./ui";

export default function SensePanel() {
  const { zones, densityHistory, reports } = useBus();
  const now = useNow();
  const rows = Object.values(zones).sort((a, b) => a.zone.localeCompare(b.zone));
  const latest = rows.reduce((m, z) => Math.max(m, z.receivedAt), 0);
  const pins = reports.filter((r) => r.source === "volunteer_button").slice(0, 5);

  return (
    <Panel title="Sense" owner="Shirali" badge={<span>updated {ago(latest, now)}</span>}>
      <div className="rounded-xl bg-zinc-100 px-4 py-3 text-sm text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
        Crowd counts per zone, every 2 s.{" "}
        {rows.some((z) => z.source === "sim") && <span className="font-medium">Simulated crowd feed in this demo.</span>}
      </div>

      <Section title="Zones">
        {rows.length === 0 ? (
          <Empty>Waiting for br/zone_state…</Empty>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-zinc-500">
              <tr><th className="py-1">Zone</th><th>People</th><th>Density</th><th>Speed</th><th>Dir</th><th>5 min</th></tr>
            </thead>
            <tbody>
              {rows.map((z) => (
                <tr key={z.zone} className="border-t border-zinc-100 dark:border-zinc-800">
                  <td className="py-1.5 font-medium">{z.zone}</td>
                  <td className="tabular-nums">{z.count}</td>
                  <td><Pill className={TONE[densityTone(z.density_ppm2)]}>{z.density_ppm2.toFixed(1)}/m²</Pill></td>
                  <td className="tabular-nums">{z.speed_mps != null ? `${z.speed_mps.toFixed(1)} m/s` : "–"}</td>
                  <td>
                    {z.direction_deg != null ? (
                      // 0° = east, counter-clockwise; CSS rotates clockwise, so negate.
                      <span className="inline-block" style={{ transform: `rotate(${-z.direction_deg}deg)` }} aria-label={`${z.direction_deg}°`}>→</span>
                    ) : "–"}
                  </td>
                  <td><Sparkline values={(densityHistory[z.zone] ?? []).map((p) => p.d)} danger={DANGER} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      <Section title="Volunteer buttons">
        {pins.length === 0 ? <Empty>No button presses yet.</Empty> : (
          <ul className="flex flex-col gap-1 text-sm">
            {pins.map((r, i) => (
              <li key={i}>📍 {r.node} · zone {r.zone ?? "?"} · {r.text} <span className="text-zinc-500">· {ago(r.receivedAt, now)}</span></li>
            ))}
          </ul>
        )}
      </Section>

      <p className="text-xs text-zinc-500">Faces blurred. No face recognition. Raw video never stored.</p>
    </Panel>
  );
}
