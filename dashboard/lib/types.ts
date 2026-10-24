// TypeScript mirror of common/contracts.py (spec Section 7.2). Keep in sync; never change one side alone.

export type ZoneState = {
  t: string;
  zone: string;
  count: number;
  density_ppm2: number;
  speed_mps?: number | null;
  direction_deg?: number | null; // 0 = right/east on the image, counter-clockwise
  turbulence?: number | null;
  source: string;
};

export type Report = {
  t: string;
  source: "volunteer_button" | "telegram" | "call_note" | "operator";
  node?: string | null;
  zone?: string | null;
  text: string;
  severity: number; // 1-5, 5 = someone fell / cannot breathe
};

export type ZoneForecast = {
  zone: string;
  p50_density: number;
  p90_density: number;
  p_danger: number;
  minutes_to_danger?: number | null;
};

export type Forecast = { t: string; horizon_min: number; runs: number; zones: ZoneForecast[] };

export type Action = {
  type: "move_officers" | "gate" | "announce" | "hold_inflow";
  count?: number | null;
  from_zone?: string | null;
  to_zone?: string | null;
  link?: string | null;
  state?: "open" | "closed" | null;
  zone?: string | null;
  langs?: string[] | null;
  text?: string | null;
  minutes?: number | null;
  entry?: string | null;
};

export type Plan = { plan_id: string; strategy: string; actions: Action[]; why: string };

export type ScoreResult = {
  plan_id: string;
  max_p_danger: number;
  min_minutes_to_danger?: number | null;
  zones: ZoneForecast[];
};

export type ChosenPlan = {
  t: string;
  plan: Plan;
  score: ScoreResult;
  baseline_max_p_danger: number;
  candidates_considered: number;
};

export type DeviceCommand = {
  to: string;
  cmd: "arrow" | "blink";
  value: "left" | "right" | "up" | "stop" | "clear";
};

export type OfficerStatus = {
  t: string;
  officer_id: string;
  name: string;
  zone: string;
  status: "idle" | "assigned" | "on_the_way" | "arrived";
  task?: string | null;
  simulated: boolean;
};

export type Announcement = { t: string; zone: string; plan_id: string; texts: Record<string, string> };

export type CostEvent = {
  t: string;
  role: "ultra" | "lightning" | "vl" | "super";
  purpose: string;
  prompt_tokens: number;
  completion_tokens: number;
  usd: number;
  latency_s: number;
};

// Not frozen contracts: Act's progress and approval messages.
export type Status = {
  t: string;
  source?: string; // "watchdog" | "planner" | "executor"
  text: string;
  urgency?: "low" | "high";
  reasons?: string[];
};

export type ApprovalRequest = {
  t: string;
  approval_id: string;
  plan_id: string;
  action: Action;
  why: string;
  expires_in_s: number;
};

export type ApprovalAnswer = { t: string; approval_id: string; approved: boolean; by?: string };

// br/turnout (A07, act/turnout.py TurnoutEstimate): Tavily-based turnout estimate, one per run.
export type TurnoutSource = {
  url: string;
  quote: string;
  estimate: number;
  kind: "expected" | "reported" | "declared" | "past_event";
  published?: string | null;
};

export type TurnoutEstimate = {
  t: string;
  event: string;
  city: string;
  date: string; // YYYY-MM-DD
  declared: number;
  low: number | null;
  high: number | null;
  ratio: number | null; // high / declared
  based_on: "this_event" | "past_events" | "none";
  warning: boolean; // ratio > 1.5
  message: string; // card headline
  sources: TurnoutSource[];
  dropped: number; // sources rejected by the quote check
  note: string; // model's one-liner: its numbers are NOT facts, only sources are checked
  window: { start_date: string; end_date: string };
  mode: "before_event" | "up_to_today";
  searches: number;
};
