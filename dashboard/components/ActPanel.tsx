"use client";

// NAVIKA owns this panel (spec A09): what the AI decided, what it's doing, and what it cost.

import { useEffect, useMemo, useState } from "react";
import { ago, post, useBus, useNow, type Approval } from "@/lib/bus";
import type { Action } from "@/lib/types";
import { Empty, Panel, Pill, Section } from "./ui";

const SEVERITY = [
  "",
  "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  "bg-yellow-100 text-yellow-900 dark:bg-yellow-900/40 dark:text-yellow-200",
  "bg-orange-100 text-orange-900 dark:bg-orange-900/40 dark:text-orange-200",
  "bg-red-100 text-red-900 dark:bg-red-900/50 dark:text-red-200",
  "bg-red-600 text-white",
];

const OFFICER = {
  idle: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  assigned: "bg-yellow-100 text-yellow-900 dark:bg-yellow-900/40 dark:text-yellow-200",
  on_the_way: "bg-sky-100 text-sky-900 dark:bg-sky-900/40 dark:text-sky-200",
  arrived: "bg-emerald-100 text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-200",
};

const LANG = { en: { label: "English", voice: "en-IN" }, ta: { label: "தமிழ்", voice: "ta-IN" }, hi: { label: "हिन्दी", voice: "hi-IN" } } as const;

function describe(a: Action) {
  switch (a.type) {
    case "move_officers": return { icon: "👮", text: `Move ${a.count} officer${a.count === 1 ? "" : "s"} from zone ${a.from_zone} to zone ${a.to_zone}` };
    case "gate": return { icon: a.state === "closed" ? "⛔" : "✅", text: `${a.state === "closed" ? "Close" : "Open"} gate ${a.link}` };
    case "hold_inflow": return { icon: "⏸️", text: `Pause entry at ${a.entry} for ${a.minutes} min` };
    case "announce": return { icon: "📢", text: `Announce in zone ${a.zone}: “${a.text}”` };
  }
}

const pct = (p: number) => `${Math.round(p * 100)}%`;
const usd = (x: number) => (x < 0.01 ? `$${x.toFixed(4)}` : `$${x.toFixed(3)}`);

export default function ActPanel() {
  const bus = useBus();
  const now = useNow();
  const plan = bus.plans[0];
  const watchdog = bus.statuses.find((s) => s.source === "watchdog");
  const planner = bus.statuses.find((s) => s.source === "planner");
  const executor = bus.statuses.find((s) => s.source === "executor");
  const working = !!planner && (!plan || planner.receivedAt > plan.receivedAt) && !/^Chosen|failed/i.test(planner.text);

  return (
    <Panel title="Act" owner="Navika" badge={working ? <Pill className="animate-pulse bg-sky-100 text-sky-900 dark:bg-sky-900/40 dark:text-sky-200">AI working</Pill> : null}>
      <Section title="Situation" right={watchdog && ago(watchdog.receivedAt, now)}>
        {watchdog ? (
          <div className={`rounded-lg p-3 text-sm ${watchdog.urgency === "high" ? "bg-red-50 text-red-950 dark:bg-red-950/40 dark:text-red-100" : "bg-zinc-50 dark:bg-zinc-800"}`}>
            {watchdog.urgency === "high" && <Pill className="mb-1 bg-red-600 text-white">urgent</Pill>}
            <p>{watchdog.text}</p>
          </div>
        ) : <Empty>All quiet. The watchdog speaks when a zone heads for danger.</Empty>}
        {planner && <p className={`text-sm ${working ? "text-sky-700 dark:text-sky-300" : "text-zinc-500"}`}>{planner.text}</p>}
        {executor && <p className="text-xs text-zinc-500">{executor.text}</p>}
      </Section>

      <Approvals approvals={Object.values(bus.approvals)} now={now} />

      <Section title="Chosen plan" right={plan && `${plan.candidates_considered} plans tested · ${ago(plan.receivedAt, now)}`}>
        {!plan ? <Empty>No plan yet.</Empty> : (
          <div className="flex flex-col gap-3 rounded-xl border border-zinc-200 p-3 dark:border-zinc-700">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <p className="font-medium">{plan.plan.strategy}</p>
              <span className="text-xs text-zinc-500">
                {plan.plan.plan_id === "RB" ? <Pill className="bg-violet-100 text-violet-900 dark:bg-violet-900/40 dark:text-violet-200">rule-based plan won</Pill> : `plan ${plan.plan.plan_id}`}
              </span>
            </div>
            <ul className="flex flex-col gap-1 text-sm">
              {plan.plan.actions.map((a, i) => {
                const d = describe(a);
                return <li key={i} className="flex gap-2"><span aria-hidden>{d.icon}</span><span>{d.text}</span></li>;
              })}
            </ul>
            <p className="text-sm text-zinc-600 dark:text-zinc-300">{plan.plan.why}</p>
            <div className="grid grid-cols-2 gap-2 text-center">
              <div className="rounded-lg bg-emerald-50 p-2 dark:bg-emerald-950/40">
                <div className="text-2xl font-semibold tabular-nums text-emerald-800 dark:text-emerald-200">{pct(1 - plan.score.max_p_danger)}</div>
                <div className="text-xs text-zinc-600 dark:text-zinc-400">futures safe with this plan</div>
              </div>
              <div className="rounded-lg bg-zinc-50 p-2 dark:bg-zinc-800">
                <div className="text-2xl font-semibold tabular-nums">{pct(1 - plan.baseline_max_p_danger)}</div>
                <div className="text-xs text-zinc-600 dark:text-zinc-400">futures safe doing nothing</div>
              </div>
            </div>
          </div>
        )}
      </Section>

      <Officers />
      <Announcements />
      <Reports />
      <Costs />
      <CallNote />
    </Panel>
  );
}

function Approvals({ approvals, now }: { approvals: Approval[]; now: number }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const open = approvals.filter((a) => !a.resolved && now < a.receivedAt + a.expires_in_s * 1000);
  const recent = approvals
    .filter((a) => !open.includes(a))
    .sort((a, b) => b.receivedAt - a.receivedAt)
    .slice(0, 3);
  if (open.length === 0 && recent.length === 0) return null;

  const answer = async (a: Approval, approved: boolean) => {
    setBusy(a.approval_id); setError(null);
    try { await post("/operator/approve", { approval_id: a.approval_id, approved, by: "dashboard" }); }
    catch (e) { setError(String(e)); }
    finally { setBusy(null); }
  };

  return (
    <Section title="Needs your approval">
      {open.map((a) => {
        const left = Math.max(0, Math.round((a.receivedAt + a.expires_in_s * 1000 - now) / 1000));
        return (
          <div key={a.approval_id} className="flex flex-col gap-2 rounded-xl border-2 border-amber-400 bg-amber-50 p-3 dark:bg-amber-950/30">
            <div className="flex items-baseline justify-between gap-2">
              <p className="font-semibold">⛔ {a.action.state === "closed" ? "Close" : "Open"} gate {a.action.link}?</p>
              <span className="text-xs tabular-nums text-amber-900 dark:text-amber-200">{left} s left</span>
            </div>
            <p className="text-sm">{a.why}</p>
            <div className="flex gap-2">
              <button disabled={busy === a.approval_id} onClick={() => answer(a, true)}
                className="flex-1 rounded-lg bg-zinc-900 px-3 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-white dark:text-zinc-900">
                Approve
              </button>
              <button disabled={busy === a.approval_id} onClick={() => answer(a, false)}
                className="flex-1 rounded-lg border border-zinc-300 px-3 py-2 text-sm font-medium hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-600 dark:hover:bg-zinc-800">
                Reject
              </button>
            </div>
            <p className="text-xs text-zinc-500">No answer means the gate stays as it is.</p>
          </div>
        );
      })}
      {recent.map((a) => (
        <p key={a.approval_id} className="text-xs text-zinc-500">
          Gate {a.action.link} {a.action.state}: {a.resolved === "approved" ? `approved by ${a.by}` : a.resolved === "rejected" ? `rejected by ${a.by}` : a.resolved === "replaced" ? "replaced by a newer plan" : a.resolved === "withdrawn" ? "withdrawn, not changed" : "no answer, not changed"}
        </p>
      ))}
      {error && open.length > 0 && <p className="text-xs text-red-600">{error}</p>}
    </Section>
  );
}

function Officers() {
  const { officers, devices } = useBus();
  const list = Object.values(officers).sort((a, b) => a.officer_id.localeCompare(b.officer_id, undefined, { numeric: true }));
  const gates = Object.values(devices).sort((a, b) => a.to.localeCompare(b.to));
  return (
    <Section title="Officers and gates">
      {list.length === 0 && gates.length === 0 ? <Empty>No officers moved yet.</Empty> : (
        <>
          {gates.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {gates.map((g) => (
                <Pill key={g.to} className={g.value === "stop" ? "bg-red-100 text-red-900 dark:bg-red-900/50 dark:text-red-200" : "bg-emerald-100 text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-200"}>
                  {g.to}: {g.value === "stop" ? "closed" : g.value}
                </Pill>
              ))}
            </div>
          )}
          <ul className="flex flex-col gap-1 text-sm">
            {list.map((o) => (
              <li key={o.officer_id} className="flex items-center justify-between gap-2">
                <span>{o.name} <span className="text-zinc-500">· zone {o.zone}{o.simulated ? " · simulated" : ""}</span></span>
                <Pill className={OFFICER[o.status]}>{o.status.replace(/_/g, " ")}</Pill>
              </li>
            ))}
          </ul>
        </>
      )}
    </Section>
  );
}

function Announcements() {
  const { announcements } = useBus();
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  useEffect(() => {
    if (typeof window === "undefined" || !window.speechSynthesis) return;
    const load = () => setVoices(window.speechSynthesis.getVoices());
    load();
    window.speechSynthesis.addEventListener("voiceschanged", load);
    return () => window.speechSynthesis.removeEventListener("voiceschanged", load);
  }, []);
  const a = announcements[0];
  if (!a) return null;

  const voiceFor = (code: string) => voices.find((v) => v.lang.replace("_", "-").startsWith(code)) ?? voices.find((v) => v.lang.startsWith(code.slice(0, 2)));
  const play = (lang: keyof typeof LANG, text: string) => {
    const u = new SpeechSynthesisUtterance(text);
    const v = voiceFor(LANG[lang].voice);
    if (v) u.voice = v;
    u.lang = LANG[lang].voice;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
  };

  return (
    <Section title={`Announcement · zone ${a.zone}`}>
      <ul className="flex flex-col gap-2">
        {(Object.keys(LANG) as (keyof typeof LANG)[]).map((l) => {
          // A translation that failed Act's safety check is left out: say so and play English instead.
          const missing = !a.texts[l];
          const lang = missing ? "en" : l;
          const hasVoice = !!voiceFor(LANG[lang].voice);
          return (
            <li key={l} className="flex items-start gap-2 text-sm">
              <button onClick={() => play(lang, a.texts[lang] ?? "")} disabled={!hasVoice || !a.texts[lang]}
                title={missing ? "Translation not available; plays English" : hasVoice ? "Play" : "No voice for this language on this computer; read it out"}
                className="mt-0.5 rounded-md border border-zinc-300 px-1.5 text-xs disabled:opacity-40 dark:border-zinc-600">▶</button>
              <span>
                <span className="text-xs text-zinc-500">{LANG[l].label}</span><br />
                {missing ? <span className="text-zinc-500">Translation not available; play the English line.</span> : a.texts[l]}
              </span>
            </li>
          );
        })}
      </ul>
    </Section>
  );
}

function Reports() {
  const { reports } = useBus();
  const now = useNow(5000);
  return (
    <Section title="Reports">
      {reports.length === 0 ? <Empty>No reports yet.</Empty> : (
        <ul className="flex max-h-48 flex-col gap-1 overflow-y-auto text-sm">
          {reports.slice(0, 20).map((r, i) => (
            <li key={i} className="flex items-start gap-2">
              <Pill className={SEVERITY[r.severity] ?? SEVERITY[1]}>{r.severity}</Pill>
              <span>{r.text} <span className="text-zinc-500">· zone {r.zone ?? "?"} · {r.source.replace(/_/g, " ")} · {ago(r.receivedAt, now)}</span></span>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

function Costs() {
  const { costs, plans, statuses } = useBus();
  const summary = useMemo(() => {
    const byRole: Record<string, { calls: number; usd: number; latency: number }> = {};
    for (const c of costs) {
      const r = (byRole[c.role] ??= { calls: 0, usd: 0, latency: 0 });
      r.calls++; r.usd += c.usd; r.latency += c.latency_s;
    }
    // Last decision = model calls from the watchdog trigger that led to the latest plan until just
    // after it (announcement translations), never reaching back into the previous decision.
    const plan = plans[0];
    let decision: { usd: number; seconds: number; calls: string } | null = null;
    if (plan) {
      const prevEnd = plans[1] ? plans[1].receivedAt + 20000 : 0;
      const trigger = statuses.find((s) => s.source === "watchdog" && s.receivedAt <= plan.receivedAt && s.receivedAt >= prevEnd);
      const start = Math.max(prevEnd, trigger ? trigger.receivedAt - 15000 : plan.receivedAt - 90000);
      const calls = costs.filter((c) => c.receivedAt >= start && c.receivedAt <= plan.receivedAt + 20000);
      const counts = new Map<string, number>();
      for (const c of calls) counts.set(`${c.role} ${c.purpose}`, (counts.get(`${c.role} ${c.purpose}`) ?? 0) + 1);
      decision = {
        usd: calls.reduce((s, c) => s + c.usd, 0),
        seconds: trigger ? (plan.receivedAt - trigger.receivedAt) / 1000 : NaN,
        calls: [...counts].map(([k, n]) => (n > 1 ? `${k} ×${n}` : k)).join(", "),
      };
    }
    return { byRole, total: costs.reduce((s, c) => s + c.usd, 0), decision };
  }, [costs, plans, statuses]);

  if (costs.length === 0) return null;
  return (
    <Section title="Cost and speed" right={`total ${usd(summary.total)}`}>
      {summary.decision && (
        <p className="text-sm">
          Last decision: <b>{usd(summary.decision.usd)}</b>
          {!Number.isNaN(summary.decision.seconds) && <> · decided in <b>{summary.decision.seconds.toFixed(0)} s</b></>}
          {summary.decision.calls && <>{" "}<span className="text-zinc-500">({summary.decision.calls})</span></>}
        </p>
      )}
      <table className="w-full text-sm">
        <thead className="text-left text-xs text-zinc-500"><tr><th className="py-1">Model</th><th>Calls</th><th>Spend</th><th>Avg time</th></tr></thead>
        <tbody>
          {Object.entries(summary.byRole).map(([role, r]) => (
            <tr key={role} className="border-t border-zinc-100 dark:border-zinc-800">
              <td className="py-1">Nemotron {role === "ultra" ? "3 Ultra" : role === "lightning" ? "3.5 Lightning" : role === "super" ? "3 Super" : "3.5 Super VL"}</td>
              <td className="tabular-nums">{r.calls}</td>
              <td className="tabular-nums">{usd(r.usd)}</td>
              <td className="tabular-nums">{(r.latency / r.calls).toFixed(1)} s</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Section>
  );
}

function CallNote() {
  const { zones, forecast } = useBus();
  const ids = Array.from(new Set([...Object.keys(zones), ...(forecast?.zones.map((z) => z.zone) ?? [])])).sort();
  const [text, setText] = useState("");
  const [zone, setZone] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");

  const send = async () => {
    if (!text.trim()) return;
    setState("sending");
    try {
      await post("/operator/report", { text: text.trim(), zone: zone || null });
      setText(""); setState("sent");
    } catch { setState("error"); }
  };

  return (
    <Section title="Call note" right={state === "sent" ? "sent" : state === "error" ? "failed, is the backend running?" : undefined}>
      <textarea value={text} onChange={(e) => { setText(e.target.value); setState("idle"); }} rows={2}
        placeholder="What did the caller say? English, Tamil or Hindi."
        className="w-full resize-y rounded-lg border border-zinc-300 bg-transparent p-2 text-sm dark:border-zinc-700" />
      <div className="flex gap-2">
        <select value={zone} onChange={(e) => setZone(e.target.value)} className="rounded-lg border border-zinc-300 bg-transparent px-2 text-sm dark:border-zinc-700">
          <option value="">Zone unknown</option>
          {ids.map((z) => <option key={z} value={z}>Zone {z}</option>)}
        </select>
        <button onClick={send} disabled={!text.trim() || state === "sending"}
          className="flex-1 rounded-lg bg-zinc-900 px-3 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-white dark:text-zinc-900">
          {state === "sending" ? "Sending…" : "Send report"}
        </button>
      </div>
    </Section>
  );
}
