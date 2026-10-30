"use client";

// ANANYA owns this panel (spec I08). This is a working placeholder built on the shared bus:
// replace it with the venue map coloured by p_danger and the fan chart (do nothing vs chosen plan).

import { ago, useBus, useNow } from "@/lib/bus";
import { TONE, dangerTone } from "@/lib/thresholds";
import { Empty, Panel, Pill, Section } from "./ui";

export default function ImaginePanel() {
  const { forecast } = useBus();
  const now = useNow();
  const zones = forecast ? [...forecast.zones].sort((a, b) => b.p_danger - a.p_danger) : [];

  return (
    <Panel
      title="Imagine"
      owner="Ananya"
      badge={forecast && <span>{forecast.runs.toLocaleString()} runs · updated {ago(forecast.receivedAt, now)}</span>}
    >
      <a
        href="/judge"
        target="_blank"
        className="flex items-center justify-between rounded-xl bg-zinc-100 px-4 py-3 text-sm text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
      >
        <span>Venue twin, gate what-ifs and ranked plans</span>
        <span className="font-medium">Open simulation view →</span>
      </a>

      <Section title={`Next ${forecast?.horizon_min ?? 15} minutes`}>
        {!forecast ? (
          <Empty>Waiting for br/forecast…</Empty>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-zinc-500">
              <tr><th className="py-1">Zone</th><th>Danger chance</th><th>Danger in</th><th>Density p50 / p90</th></tr>
            </thead>
            <tbody>
              {zones.map((z) => (
                <tr key={z.zone} className="border-t border-zinc-100 dark:border-zinc-800">
                  <td className="py-1.5 font-medium">{z.zone}</td>
                  <td><Pill className={TONE[dangerTone(z.p_danger)]}>{Math.round(z.p_danger * 100)}%</Pill></td>
                  <td className="tabular-nums">{z.minutes_to_danger != null ? `${Math.round(z.minutes_to_danger)} min` : "–"}</td>
                  <td className="tabular-nums">{z.p50_density.toFixed(1)} / {z.p90_density.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>
    </Panel>
  );
}
