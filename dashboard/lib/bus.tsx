"use client";

// One live connection to the backend WebSocket (GET /ws relays every br/# MQTT message
// as {"topic", "data"}). Keeps the latest state per topic; every panel reads it with useBus().

import { createContext, useContext, useEffect, useReducer, useState, type ReactNode } from "react";
import type {
  Announcement, ApprovalAnswer, ApprovalRequest, ChosenPlan, CostEvent, DeviceCommand, Forecast,
  OfficerStatus, Report, Status, ZoneState,
} from "./types";

export const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
const WS_URL = BACKEND_URL.replace(/^http/, "ws") + "/ws";

const HISTORY_MS = 5 * 60 * 1000;

type Stamped<T> = T & { receivedAt: number };

export type Approval = Stamped<ApprovalRequest> & {
  resolved?: "approved" | "rejected" | "replaced" | "withdrawn";
  by?: string;
};

export type BusState = {
  connected: boolean;
  messages: number;
  zones: Record<string, Stamped<ZoneState>>;
  densityHistory: Record<string, { at: number; d: number }[]>;
  forecast: Stamped<Forecast> | null;
  reports: Stamped<Report>[]; // newest first
  plans: Stamped<ChosenPlan>[]; // newest first
  officers: Record<string, Stamped<OfficerStatus>>;
  announcements: Stamped<Announcement>[]; // newest first
  statuses: Stamped<Status>[]; // newest first
  costs: Stamped<CostEvent>[]; // oldest first
  devices: Record<string, Stamped<DeviceCommand>>;
  approvals: Record<string, Approval>;
  raw: { topic: string; data: unknown; at: number }[]; // newest first
};

const initial: BusState = {
  connected: false, messages: 0, zones: {}, densityHistory: {}, forecast: null, reports: [],
  plans: [], officers: {}, announcements: [], statuses: [], costs: [], devices: {}, approvals: {}, raw: [],
};

type Msg = { type: "connected"; value: boolean } | { type: "message"; topic: string; data: unknown; at: number };

const cap = <T,>(list: T[], n: number) => (list.length > n ? list.slice(0, n) : list);

function reduce(s: BusState, m: Msg): BusState {
  if (m.type === "connected") return { ...s, connected: m.value };
  const { topic, at } = m;
  const d = m.data as Record<string, unknown>;
  const stamp = <T,>(x: T) => ({ ...x, receivedAt: at }) as Stamped<T>;
  const next: BusState = { ...s, messages: s.messages + 1, raw: cap([{ topic, data: m.data, at }, ...s.raw], 100) };

  switch (true) {
    case topic === "br/zone_state": {
      const z = stamp(d as unknown as ZoneState);
      const hist = (s.densityHistory[z.zone] ?? []).filter((p) => at - p.at < HISTORY_MS);
      next.zones = { ...s.zones, [z.zone]: z };
      next.densityHistory = { ...s.densityHistory, [z.zone]: [...hist, { at, d: z.density_ppm2 }] };
      break;
    }
    case topic === "br/forecast":
      next.forecast = stamp(d as unknown as Forecast);
      break;
    case topic === "br/report":
      next.reports = cap([stamp(d as unknown as Report), ...s.reports], 50);
      break;
    case topic === "br/plan": {
      const p = stamp(d as unknown as ChosenPlan);
      next.plans = cap([p, ...s.plans], 10);
      // A newer plan replaces approval requests from older plans (the executor withdraws them).
      next.approvals = Object.fromEntries(Object.entries(s.approvals).map(([id, a]) =>
        [id, !a.resolved && a.plan_id !== p.plan.plan_id && a.receivedAt < at ? { ...a, resolved: "replaced" as const } : a]));
      break;
    }
    case topic === "br/officer": {
      const o = stamp(d as unknown as OfficerStatus);
      next.officers = { ...s.officers, [o.officer_id]: o };
      break;
    }
    case topic === "br/announce":
      next.announcements = cap([stamp(d as unknown as Announcement), ...s.announcements], 10);
      break;
    case topic === "br/status": {
      const st = stamp(d as unknown as Status);
      next.statuses = cap([st, ...s.statuses], 50);
      // The executor reports how each approval ended, e.g. "Navika approved: gate G3 closed",
      // "dashboard rejected closing gate G3; ...", "Approval to closed gate G3 withdrawn (...)".
      const gate = st.source === "executor" ? st.text.match(/gate (\w+)/)?.[1] : undefined;
      const outcome = /withdrawn/.test(st.text) ? "withdrawn" : / approved:/.test(st.text) ? "approved" : / rejected /.test(st.text) ? "rejected" : undefined;
      if (gate && outcome) {
        const by = outcome === "withdrawn" ? undefined : st.text.split(outcome === "approved" ? " approved:" : " rejected ")[0];
        next.approvals = Object.fromEntries(Object.entries(s.approvals).map(([id, a]) =>
          [id, !a.resolved && a.action.link === gate && a.receivedAt <= at ? { ...a, resolved: outcome, by } : a]));
      }
      break;
    }
    case topic === "br/cost":
      next.costs = [...s.costs, stamp(d as unknown as CostEvent)].slice(-500);
      break;
    case topic.startsWith("br/device/"): {
      const c = stamp(d as unknown as DeviceCommand);
      next.devices = { ...s.devices, [c.to]: c };
      break;
    }
    case topic === "br/approval": {
      const a = stamp(d as unknown as ApprovalRequest);
      next.approvals = { ...s.approvals, [a.approval_id]: a };
      break;
    }
    case topic === "br/approve": {
      const ans = d as unknown as ApprovalAnswer;
      const a = s.approvals[ans.approval_id];
      if (a && !a.resolved)
        next.approvals = { ...s.approvals, [a.approval_id]: { ...a, resolved: ans.approved ? "approved" : "rejected", by: ans.by } };
      break;
    }
  }
  return next;
}

const BusContext = createContext<BusState>(initial);

export function BusProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reduce, initial);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let retry = 1000;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;

    const connect = () => {
      ws = new WebSocket(WS_URL);
      ws.onopen = () => { retry = 1000; dispatch({ type: "connected", value: true }); };
      ws.onmessage = (e) => {
        try {
          const { topic, data } = JSON.parse(e.data);
          dispatch({ type: "message", topic, data, at: Date.now() });
        } catch { /* ignore a malformed frame */ }
      };
      ws.onclose = () => {
        dispatch({ type: "connected", value: false });
        if (!stopped) { timer = setTimeout(connect, retry); retry = Math.min(retry * 2, 10000); }
      };
      ws.onerror = () => ws?.close();
    };
    connect();
    return () => { stopped = true; clearTimeout(timer); ws?.close(); };
  }, []);

  return <BusContext.Provider value={state}>{children}</BusContext.Provider>;
}

export const useBus = () => useContext(BusContext);

/** Current time, refreshed every `ms` - for "updated 12 s ago" labels and countdowns. */
export function useNow(ms = 1000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(id);
  }, [ms]);
  return now;
}

export function ago(at: number | undefined, now: number) {
  if (!at) return "never";
  const s = Math.max(0, Math.round((now - at) / 1000));
  return s < 60 ? `${s} s ago` : `${Math.floor(s / 60)} min ago`;
}

export async function post(path: string, body: unknown) {
  const r = await fetch(`${BACKEND_URL}${path}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${path} failed: ${r.status}`);
  return r.json();
}
