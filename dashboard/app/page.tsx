
"use client";

import { useEffect, useState } from "react";

const API_URL = "http://127.0.0.1:8002";
const DANGER_DENSITY = 5;

type VenueZone = {
  id: string;
  name: string;
  area_m2: number;
  polygon_px: number[][];
  polygon_map: number[][];
  capacity_note?: string | null;
};

type VenueLink = {
  id: string;
  from: string;
  to: string;
  width_m: number;
  kind: string;
  state: string;
};

type VenueData = {
  venue_id: string;
  name: string;
  zones: VenueZone[];
  links: VenueLink[];
  entries: { zone: string; name: string }[];
  pa_zones: string[];
  officers_total: number;
};

type ForecastZone = {
  zone: string;
  p50_density: number;
  p90_density: number;
  p_danger: number;
  minutes_to_danger: number | null;
};

type ForecastData = {
  t: string;
  horizon_min: number;
  runs: number;
  zones: ForecastZone[];
};

type ScoreData = {
  plan_id: string;
  max_p_danger: number;
  min_minutes_to_danger: number | null;
  zones: ForecastZone[];
};


type RecommendedPlan = {
  plan: {
    plan_id: string;
    strategy: string;
    actions: {
      type: string;
      count?: number | null;
      from_zone?: string | null;
      to_zone?: string | null;
      link?: string | null;
      state?: string | null;
      entry?: string | null;
      zone?: string | null;
      minutes?: number | null;
      langs?: string[] | null;
      text?: string | null;
    }[];
    why: string;
  };
  score: ScoreData;
  rank: number;
  explanation: string;
};

type RecommendationData = {
  baseline: ScoreData;
  recommended_plan_id: string;
  candidates_considered: number;
  generation_source: "ai" | "fallback" | "user_supplied";
  recommendations: RecommendedPlan[];
};


const zonePositions: Record<
  string,
  { x: number; y: number; w: number; h: number }
> = {
  // Original demo venue
  A: { x: 8, y: 36, w: 22, h: 28 },
  B: { x: 34, y: 26, w: 30, h: 44 },
  C: { x: 69, y: 18, w: 23, h: 31 },
  D: { x: 69, y: 58, w: 23, h: 23 },

  // Uploaded residential venue
  zone_bedroom: { x: 8, y: 10, w: 28, h: 30 },
  zone_living_room: { x: 8, y: 43, w: 28, h: 45 },
  zone_hallway: { x: 39, y: 10, w: 18, h: 78 },
  zone_bathroom: { x: 60, y: 10, w: 30, h: 25 },
  zone_kitchen: { x: 60, y: 38, w: 30, h: 50 },
};

const riskStyles: Record<string, string> = {
  low: "border-emerald-400/40 bg-emerald-400/15 text-emerald-300",
  medium: "border-amber-400/40 bg-amber-400/15 text-amber-300",
  high: "border-red-400/50 bg-red-500/20 text-red-300",
};

function getRisk(probability: number): "low" | "medium" | "high" {
  if (probability > 0.3) return "high";
  if (probability >= 0.1) return "medium";
  return "low";
}

function formatTime(timestamp: string | undefined): string {
  if (!timestamp) return "Not available";

  const date = new Date(timestamp);

  if (Number.isNaN(date.getTime())) return "Not available";

  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}


export default function Home() {
  const [selectedZone, setSelectedZone] = useState("C");
  const [editedVenue, setEditedVenue] = useState<VenueData | null>(null);
  const [savingVenue, setSavingVenue] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [venue, setVenue] = useState<VenueData | null>(null);
  const [forecast, setForecast] = useState<ForecastData | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [scoring, setScoring] = useState(false);
  const [scoreError, setScoreError] = useState<string | null>(null);
  const [baselineScore, setBaselineScore] = useState<ScoreData | null>(null);
  const [planScore, setPlanScore] = useState<ScoreData | null>(null);
  const [holdMinutes, setHoldMinutes] = useState(5);
  const [comparisonScores, setComparisonScores] = useState<ScoreData[]>([]);
  const [selectedGateId, setSelectedGateId] = useState("");
  const [gateState, setGateState] = useState<"open" | "closed">("closed");
  const [gateScore, setGateScore] = useState<ScoreData | null>(null);
  const [gateScoring, setGateScoring] = useState(false);
  const [recommendations, setRecommendations] = useState<RecommendationData | null>(null);
  const [recommendationLoading, setRecommendationLoading] = useState(false);  
  const [recommendationError, setRecommendationError] = useState<string | null>(null);

  async function handleScoreIntervention() {
    if (!venue) return;

    const entryName = venue.entries[0]?.name;
    if (!entryName) {
      setScoreError("This venue has no configured entry to hold.");
      return;
    }

    const durations = [2, 5, 10];
    setScoring(true);
    setScoreError(null);
    setBaselineScore(null);
    setPlanScore(null);
    setComparisonScores([]);

    try {
      const baselineResponse = await fetch(`${API_URL}/score/baseline`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const baselineBody = await baselineResponse.json().catch(() => null);
      if (!baselineResponse.ok) {
        throw new Error(
          baselineBody?.detail ??
            `Baseline scoring failed (${baselineResponse.status}).`
        );
      }

      const baseline = baselineBody as ScoreData;
      const results = await Promise.all(
        durations.map(async (minutes) => {
          const plan = {
            plan_id: `hold-arrivals-${minutes}-min`,
            strategy: `Hold arrivals for ${minutes} minutes`,
            why: `Evaluate whether a ${minutes}-minute pause in incoming arrivals changes forecast danger.`,
            actions: [{ type: "hold_inflow", entry: entryName, minutes }],
          };
          const response = await fetch(`${API_URL}/score`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ plan }),
          });
          const body = await response.json().catch(() => null);
          if (!response.ok) {
            throw new Error(
              body?.detail ?? `The ${minutes}-minute plan failed (${response.status}).`
            );
          }
          return body as ScoreData;
        })
      );

      setBaselineScore(baseline);
      setComparisonScores(results);
      setPlanScore(
        results.find((result) => result.plan_id === `hold-arrivals-${holdMinutes}-min`) ??
          results[1]
      );
    } catch (error) {
      setScoreError(
        error instanceof Error
          ? error.message
          : "Could not score the intervention scenarios."
      );
    } finally {
      setScoring(false);
    }
  }

async function handleScoreGateIntervention() {
  if (!venue) return;

  if (!selectedGateId) {
    setScoreError("Please select a gate/link first.");
    return;
  }

  const selectedGate = venue.links.find(
    (link) => link.id === selectedGateId
  );

  if (!selectedGate) {
    setScoreError("The selected gate/link was not found.");
    return;
  }

  setGateScoring(true);
  setScoreError(null);
  setGateScore(null);

  try {
    const baselineResponse = await fetch(`${API_URL}/score/baseline`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });

    const baselineBody = await baselineResponse.json().catch(() => null);

    if (!baselineResponse.ok) {
      throw new Error(
        baselineBody?.detail ??
          `Baseline scoring failed (${baselineResponse.status}).`
      );
    }

    const plan = {
      plan_id: `gate-${selectedGateId}-${gateState}`,
      strategy: `${gateState === "closed" ? "Close" : "Open"} link ${selectedGateId}`,
      why: `Evaluate the forecast with link ${selectedGateId} set to ${gateState}.`,
      actions: [
        {
          type: "gate",
          link: selectedGateId,
          state: gateState,
        },
      ],
    };

    const response = await fetch(`${API_URL}/score`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan }),
    });

    const body = await response.json().catch(() => null);

    if (!response.ok) {
      throw new Error(
        body?.detail ?? `Gate scoring failed (${response.status}).`
      );
    }

    setBaselineScore(baselineBody as ScoreData);
    setGateScore(body as ScoreData);
  } catch (error) {
    setScoreError(
      error instanceof Error
        ? error.message
        : "Could not score the gate intervention."
    );
  } finally {
    setGateScoring(false);
  }
}

  
  async function handleGetRecommendations() {
    setRecommendationLoading(true);
    setRecommendationError(null);
    setRecommendations(null);

    try {
      const response = await fetch(`${API_URL}/recommend`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });

      const body = await response.json().catch(() => null);

      if (!response.ok) {
        const detail = body?.detail;
        throw new Error(
          typeof detail === "string"
            ? detail
            : detail
              ? JSON.stringify(detail)
              : `Recommendation request failed (${response.status}).`
        );
      }

      if (
        !body ||
        !Array.isArray(body.recommendations) ||
        !body.baseline
      ) {
        throw new Error(
          "The API response is missing baseline or recommendations data."
        );
      }

      setRecommendations(body as RecommendationData);
    } catch (error) {
      setRecommendationError(
        error instanceof Error
          ? error.message
          : "Could not load AI recommendations."
      );
    } finally {
      setRecommendationLoading(false);
    }
  }

  async function handleSaveVenue() {
    if (!editedVenue || !venue) return;

    setSavingVenue(true);
    setSaveMessage(null);

    try {
      const response = await fetch(
        `${API_URL}/venue/${encodeURIComponent(venue.venue_id)}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(editedVenue),
        }
      );

      if (!response.ok) {
        const errorBody = await response.json().catch(() => null);
        throw new Error(
          errorBody?.detail ?? `Save failed (${response.status})`
        );
      }

      const savedVenue = (await response.json()) as VenueData;

      setVenue(savedVenue);
      setEditedVenue(structuredClone(savedVenue));
      setSaveMessage("Venue saved successfully.");
    } catch (error) {
      setSaveMessage(
        error instanceof Error
          ? error.message
          : "Could not save the venue."
      );
    } finally {
      setSavingVenue(false);
    }
  }

  useEffect(() => {
    let cancelled = false;

    async function loadData() {
      try {
        const [venueResponse, forecastResponse] = await Promise.all([
          fetch(`${API_URL}/venue/uploaded-venue`),
          fetch(`${API_URL}/forecast/latest`),
        ]);

        if (!venueResponse.ok) {
          throw new Error(`Venue request failed (${venueResponse.status}).`);
        }

        if (!forecastResponse.ok) {
          throw new Error(
            `Forecast request failed (${forecastResponse.status}).`
          );
        }

        const venueData: VenueData = await venueResponse.json();
        const forecastData: ForecastData = await forecastResponse.json();

        if (!cancelled) {
          setVenue(venueData);
          setEditedVenue(structuredClone(venueData));
          setSaveMessage(null);
          setForecast(forecastData);
          setApiError(null);

          setSelectedZone((current) =>
            venueData.zones.some((zone) => zone.id === current)
              ? current
              : (venueData.zones[0]?.id ?? "")
          );
        }
      } catch (error) {
        if (!cancelled) {
          setApiError(
            error instanceof Error
              ? error.message
              : "Could not connect to the Imagine API."
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadData();

    // Refresh the latest forecast every 30 seconds.
    const interval = window.setInterval(() => {
      void loadData();
    }, 30_000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  const selectedVenueZone = venue?.zones.find(
    (zone) => zone.id === selectedZone
  );

  const selectedForecast = forecast?.zones.find(
    (zone) => zone.zone === selectedZone
  );

  const metrics = [
    {
      label: "Venue zones",
      value: venue ? String(venue.zones.length).padStart(2, "0") : "—",
      note: venue?.name ?? "Loading venue...",
    },
    {
      label: "Forecast horizon",
      value: forecast ? `${forecast.horizon_min} min` : "—",
      note: "Prediction window",
    },
    {
      label: "Danger threshold",
      value: `${DANGER_DENSITY.toFixed(1)}`,
      note: "People per m²",
    },
    {
      label: "Simulation runs",
      value: forecast ? forecast.runs.toLocaleString() : "—",
      note: "Runs reported by API",
    },
  ];

  return (
    <main className="min-h-screen bg-[#080d16] text-slate-100">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 px-6 py-4 lg:px-10">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-400/15 text-xl text-cyan-300">
            ⌁
          </div>
          <div>
            <h1 className="text-lg font-semibold tracking-tight">
              Breathing Room
            </h1>
            <p className="text-xs text-slate-400">
              Crowd safety intelligence · Imagine
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3 text-xs">
          <span className="rounded-full border border-white/10 px-3 py-2 text-slate-300">
            DEMO VENUE
          </span>
          <span
            className={`flex items-center gap-2 rounded-full border px-3 py-2 ${
              apiError
                ? "border-red-400/20 bg-red-400/10 text-red-300"
                : "border-emerald-400/20 bg-emerald-400/10 text-emerald-300"
            }`}
          >
            <span
              className={`h-2 w-2 rounded-full ${
                apiError ? "bg-red-400" : "bg-emerald-400"
              }`}
            />
            {apiError ? "API connection issue" : "Imagine API"}
          </span>
        </div>
      </header>

      <div className="mx-auto max-w-[1500px] px-5 py-7 lg:px-10">
        <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.22em] text-cyan-300">
              Imagine / Venue twin
            </p>
            <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
              See the next 15 minutes.
            </h2>
            <p className="mt-2 max-w-2xl text-sm text-slate-400">
              Explore forecast density and danger probabilities, then inspect
              possible interventions before acting.
            </p>
          </div>

        </div>

        {apiError && (
          <div
            role="alert"
            className="mb-5 rounded-xl border border-red-400/30 bg-red-400/10 p-4 text-sm text-red-200"
          >
            <p className="font-semibold">Could not load the latest data.</p>
            <p className="mt-1">{apiError}</p>
            <p className="mt-1 text-xs text-red-200/70">
              Check that the Imagine API is running on port 8002. The displayed
              values may be from the last successful request.
            </p>
          </div>
        )}

        {loading && !venue && (
          <p className="mb-5 text-sm text-slate-400">
            Loading venue and forecast from the Imagine API...
          </p>
        )}

        <section className="mb-5 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {metrics.map((item) => (
            <article
              key={item.label}
              className="rounded-2xl border border-white/10 bg-white/[0.035] p-5"
            >
              <p className="text-sm text-slate-400">{item.label}</p>
              <p className="mt-3 text-3xl font-semibold tracking-tight">
                {item.value}
              </p>
              <p className="mt-2 text-xs text-slate-500">{item.note}</p>
            </article>
          ))}
        </section>

        <section className="grid grid-cols-1 gap-5 xl:grid-cols-[1.55fr_0.85fr]">
          <article className="rounded-2xl border border-white/10 bg-[#0e1624] p-5 sm:p-6">
            <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="font-semibold">Venue overview</h3>
                <p className="mt-1 text-xs text-slate-400">
                  Select a zone to inspect its latest forecast
                </p>
              </div>
              <span className="rounded-lg border border-white/10 px-3 py-2 text-xs text-slate-400">
                SCHEMATIC MAP
              </span>
            </div>

            <div className="relative min-h-[360px] overflow-hidden rounded-xl border border-white/10 bg-[#0a111d] sm:min-h-[430px]">
              <div
                className="absolute inset-0 opacity-30"
                style={{
                  backgroundImage:
                    "linear-gradient(#314158 1px, transparent 1px), linear-gradient(90deg, #314158 1px, transparent 1px)",
                  backgroundSize: "28px 28px",
                }}
              />

              <div className="absolute left-[8%] top-[12%] text-[10px] uppercase tracking-widest text-slate-500">
                North
              </div>

              <svg
                className="absolute inset-0 h-full w-full"
                viewBox="0 0 100 100"
                preserveAspectRatio="none"
                aria-label="Schematic venue connections"
              >
                {venue?.links.map((link) => {
                  const from = zonePositions[link.from];
                  const to = zonePositions[link.to];

                  if (!from || !to) return null;

                  const x1 = from.x + from.w / 2;
                  const y1 = from.y + from.h / 2;
                  const x2 = to.x + to.w / 2;
                  const y2 = to.y + to.h / 2;

                  return (
                    <line
                      key={link.id}
                      x1={x1}
                      y1={y1}
                      x2={x2}
                      y2={y2}
                      stroke={link.state === "closed" ? "#f87171" : "#64748b"}
                      strokeWidth="1.2"
                      strokeDasharray={link.state === "closed" ? "3 2" : "2 2"}
                    />
                  );
                })}
              </svg>

              {(venue?.zones ?? []).map((zone) => {
                const position = zonePositions[zone.id] ?? {
                  x: 10,
                  y: 10,
                  w: 20,
                  h: 20,
                };

                const zoneForecast = forecast?.zones.find(
                  (item) => item.zone === zone.id
                );

                const risk = getRisk(zoneForecast?.p_danger ?? 0);
                const density = zoneForecast?.p50_density;
                const probability = zoneForecast?.p_danger;

                return (
                  <button
                    key={zone.id}
                    onClick={() => setSelectedZone(zone.id)}
                    aria-pressed={selectedZone === zone.id}
                    title={`${zone.name}: ${
                      probability == null
                        ? "Forecast unavailable"
                        : `${(probability * 100).toFixed(1)}% danger probability`
                    }`}
                    className={`absolute flex flex-col items-start justify-center rounded-xl border p-2 text-left transition sm:p-3 ${
                      riskStyles[risk]
                    } ${
                      selectedZone === zone.id
                        ? "ring-2 ring-white/80 ring-offset-2 ring-offset-[#0a111d]"
                        : "hover:brightness-125"
                    }`}
                    style={{
                      left: `${position.x}%`,
                      top: `${position.y}%`,
                      width: `${position.w}%`,
                      height: `${position.h}%`,
                    }}
                  >
                    <span className="text-[10px] font-semibold opacity-70">
                      ZONE {zone.id}
                    </span>
                    <span className="mt-1 text-xs font-semibold sm:text-sm">
                      {zone.name}
                    </span>
                    <span className="mt-2 text-lg font-semibold sm:text-2xl">
                      {density == null ? "—" : density.toFixed(2)}
                    </span>
                    <span className="text-[10px]">people / m² · median</span>
                    <span className="mt-1 text-[10px]">
                      {probability == null
                        ? "No forecast"
                        : `${(probability * 100).toFixed(0)}% danger`}
                    </span>
                  </button>
                );
              })}

              {venue && venue.zones.length === 0 && (
                <p className="absolute inset-0 flex items-center justify-center text-sm text-slate-400">
                  No zones are configured for this venue.
                </p>
              )}

              <div className="absolute bottom-3 left-3 flex flex-wrap gap-3 rounded-lg border border-white/10 bg-[#080d16]/90 px-3 py-2 text-[10px] text-slate-300">
                <span>
                  <span className="mr-1 inline-block h-2 w-2 rounded-full bg-emerald-400" />
                  Low (&lt;10%)
                </span>
                <span>
                  <span className="mr-1 inline-block h-2 w-2 rounded-full bg-amber-400" />
                  Caution (10–30%)
                </span>
                <span>
                  <span className="mr-1 inline-block h-2 w-2 rounded-full bg-red-400" />
                  High (&gt;30%)
                </span>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div className="rounded-xl bg-white/[0.035] p-4">
                <p className="text-xs text-slate-400">Selected zone</p>
                <p className="mt-1 font-semibold">
                  {selectedVenueZone?.name ?? "Select a zone"}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  {selectedVenueZone
                    ? `${selectedVenueZone.area_m2} m²`
                    : "Waiting for venue data"}
                </p>
              </div>

              <div className="rounded-xl bg-white/[0.035] p-4">
                <p className="text-xs text-slate-400">Median density</p>
                <p className="mt-1 font-semibold">
                  {selectedForecast
                    ? `${selectedForecast.p50_density.toFixed(2)} people/m²`
                    : "No forecast"}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  P90:{" "}
                  {selectedForecast
                    ? `${selectedForecast.p90_density.toFixed(2)} people/m²`
                    : "—"}
                </p>
              </div>

              <div className="rounded-xl bg-white/[0.035] p-4">
                <p className="text-xs text-slate-400">Danger probability</p>
                <p className="mt-1 font-semibold">
                  {selectedForecast
                    ? `${(selectedForecast.p_danger * 100).toFixed(1)}%`
                    : "No forecast"}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  {selectedForecast?.minutes_to_danger != null
                    ? `Median crossing: ${selectedForecast.minutes_to_danger.toFixed(1)} min`
                    : "No reported crossing time"}
                </p>
              </div>
            </div>
          </article>

          <div className="flex flex-col gap-5">
            <article className="rounded-2xl border border-white/10 bg-[#0e1624] p-5">
              <h3 className="font-semibold">Latest forecast</h3>
              <p className="mt-1 text-xs text-slate-400">
                Actual API output by zone; P50 and P90 density
              </p>

              {!forecast && (
                <p className="mt-5 text-sm text-slate-500">
                  Forecast data is not available yet.
                </p>
              )}

              {forecast && (
                <>
                  <div className="mt-5 space-y-4">
                    {forecast.zones.map((item) => {
                      const maxDensity = Math.max(
                        DANGER_DENSITY,
                        item.p90_density
                      );

                      return (
                        <div key={item.zone}>
                          <div className="mb-1 flex items-center justify-between gap-2 text-xs">
                            <span className="text-slate-300">
                              {venue?.zones.find(
                                (zone) => zone.id === item.zone
                              )?.name ?? `Zone ${item.zone}`}
                            </span>
                            <span className="text-slate-400">
                              P50 {item.p50_density.toFixed(2)} · P90{" "}
                              {item.p90_density.toFixed(2)}
                            </span>
                          </div>

                          <div
                            className="relative h-3 overflow-hidden rounded-full bg-white/5"
                            title={`P50 ${item.p50_density}; P90 ${item.p90_density} people per square metre`}
                          >
                            <div
                              className="absolute inset-y-0 left-0 rounded-full bg-cyan-400/40"
                              style={{
                                width: `${Math.min(
                                  100,
                                  (item.p90_density / maxDensity) * 100
                                )}%`,
                              }}
                            />
                            <div
                              className={`absolute inset-y-0 left-0 rounded-full ${
                                item.p_danger > 0.3
                                  ? "bg-red-400"
                                  : item.p_danger >= 0.1
                                    ? "bg-amber-400"
                                    : "bg-cyan-300"
                              }`}
                              style={{
                                width: `${Math.min(
                                  100,
                                  (item.p50_density / maxDensity) * 100
                                )}%`,
                              }}
                            />
                          </div>

                          <p className="mt-1 text-[10px] text-slate-500">
                            Danger probability:{" "}
                            {(item.p_danger * 100).toFixed(1)}%
                          </p>
                        </div>
                      );
                    })}
                  </div>

                  <div className="mt-5 flex flex-wrap items-center gap-4 text-[10px] text-slate-400">
                    <span>
                      <span className="mr-1 inline-block h-2 w-2 rounded-full bg-cyan-300" />
                      P50 median
                    </span>
                    <span>
                      <span className="mr-1 inline-block h-2 w-2 rounded-full bg-cyan-300/40" />
                      P90
                    </span>
                  </div>

                  <div className="mt-4 border-t border-white/10 pt-3 text-xs text-slate-500">
                    <p>Updated: {formatTime(forecast.t)}</p>
                    <p className="mt-1">
                      {forecast.runs.toLocaleString()} runs ·{" "}
                      {forecast.horizon_min}-minute horizon
                    </p>
                  </div>
                </>
              )}
            </article>

            <article className="rounded-2xl border border-white/10 bg-[#0e1624] p-5">
              <h3 className="font-semibold">Intervention scoring</h3>
              <p className="mt-1 text-xs text-slate-400">
                Compare 2-, 5-, and 10-minute arrival holds against one shared baseline.
              </p>

              <div className="mt-4 rounded-xl border border-cyan-300/20 bg-cyan-300/[0.06] p-3">
                <label htmlFor="hold-duration" className="mb-2 block text-sm font-medium text-cyan-200">
                  Show zone details for
                </label>
                <select
                  id="hold-duration"
                  value={holdMinutes}
                  onChange={(event) => {
                    const minutes = Number(event.target.value);
                    setHoldMinutes(minutes);
                    const selected = comparisonScores.find(
                      (result) => result.plan_id === `hold-arrivals-${minutes}-min`
                    );
                    if (selected) setPlanScore(selected);
                  }}
                  disabled={scoring}
                  className="w-full rounded-lg border border-white/10 bg-[#0e1624] px-3 py-2 text-sm text-white outline-none focus:border-cyan-300 disabled:opacity-50"
                >
                  <option value={2}>2 minutes</option>
                  <option value={5}>5 minutes</option>
                  <option value={10}>10 minutes</option>
                </select>
                <p className="mt-2 text-xs text-slate-400">
                  Entry: {venue?.entries[0]?.name ?? "No entry configured"} · Simulation only; no action is executed.
                </p>
              </div>

              <button
                onClick={handleScoreIntervention}
                disabled={!venue || scoring}
                className="mt-4 w-full rounded-xl bg-cyan-300 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {scoring ? "Scoring all three plans..." : "Compare all 3 plans"}
              </button>

              {scoreError && <p className="mt-3 text-sm text-red-300" role="alert">{scoreError}</p>}

              {baselineScore && comparisonScores.length > 0 && (
                <div className="mt-5 space-y-4">
                  <div>
                    <h4 className="font-medium">Plan comparison</h4>
                    <p className="mt-1 text-xs text-slate-400">All three plans use the same baseline forecast.</p>
                  </div>
                  <div className="overflow-x-auto rounded-xl border border-white/10">
                    <table className="w-full min-w-[440px] text-left text-xs">
                      <thead className="bg-white/[0.03] text-slate-400">
                        <tr>
                          <th className="p-3 font-medium">Plan</th>
                          <th className="p-3 text-right font-medium">Max danger</th>
                          <th className="p-3 text-right font-medium">Change</th>
                          <th className="p-3 text-right font-medium">Time to danger</th>
                        </tr>
                      </thead>
                      <tbody>
                        {comparisonScores.map((result) => {
                          const change = (result.max_p_danger - baselineScore.max_p_danger) * 100;
                          const match = result.plan_id.match(/hold-arrivals-(\d+)-min/);
                          const minutes = match ? Number(match[1]) : 5;
                          const isSelected = minutes === holdMinutes;
                          return (
                            <tr key={result.plan_id} className={`border-t border-white/5 ${isSelected ? "bg-cyan-300/[0.07]" : ""}`}>
                              <td className="p-3">
                                <button type="button" onClick={() => { setHoldMinutes(minutes); setPlanScore(result); }} className="text-left text-slate-200 hover:text-cyan-200">
                                  {minutes} min {isSelected ? "• Selected" : ""}
                                </button>
                              </td>
                              <td className="p-3 text-right tabular-nums">{(result.max_p_danger * 100).toFixed(1)}%</td>
                              <td className={`p-3 text-right tabular-nums ${change < -0.05 ? "text-emerald-300" : change > 0.05 ? "text-red-300" : "text-slate-300"}`}>
                                {change > 0 ? "+" : ""}{change.toFixed(1)} pp
                              </td>
                              <td className="p-3 text-right tabular-nums">
                                {result.min_minutes_to_danger == null ? "Not reached" : `${result.min_minutes_to_danger.toFixed(1)} min`}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>

                  {planScore && (
                    <>
                      <div className="grid grid-cols-2 gap-3">
                        <div className="rounded-xl border border-white/10 p-3">
                          <p className="text-xs text-slate-400">Baseline max danger</p>
                          <p className="mt-1 text-2xl font-semibold">{(baselineScore.max_p_danger * 100).toFixed(1)}%</p>
                        </div>
                        <div className="rounded-xl border border-white/10 p-3">
                          <p className="text-xs text-slate-400">{holdMinutes}-minute plan max danger</p>
                          <p className="mt-1 text-2xl font-semibold">{(planScore.max_p_danger * 100).toFixed(1)}%</p>
                        </div>
                      </div>

                      <div className="rounded-xl border border-white/10 p-3">
                        <h4 className="font-medium">Zone-by-zone comparison · {holdMinutes}-minute plan</h4>
                        <div className="mt-3 overflow-x-auto">
                          <table className="w-full min-w-[420px] text-left text-xs">
                            <thead className="text-slate-400">
                              <tr className="border-b border-white/10">
                                <th className="pb-2 pr-3 font-medium">Zone</th>
                                <th className="px-2 pb-2 text-right font-medium">Baseline</th>
                                <th className="px-2 pb-2 text-right font-medium">Plan</th>
                                <th className="pb-2 pl-2 text-right font-medium">Change</th>
                              </tr>
                            </thead>
                            <tbody>
                              {Array.from(new Set([...baselineScore.zones.map((zone) => zone.zone), ...planScore.zones.map((zone) => zone.zone)])).map((zoneId) => {
                                const before = baselineScore.zones.find((zone) => zone.zone === zoneId);
                                const after = planScore.zones.find((zone) => zone.zone === zoneId);
                                const zoneChange = before && after ? (after.p_danger - before.p_danger) * 100 : null;
                                const zoneName = venue?.zones.find((zone) => zone.id === zoneId)?.name ?? zoneId;
                                const status = zoneChange === null ? "Unavailable" : zoneChange < -0.05 ? "Improved" : zoneChange > 0.05 ? "Worsened" : "No material change";
                                return (
                                  <tr key={zoneId} className="border-b border-white/5 last:border-0">
                                    <td className="py-2 pr-3 text-slate-200">{zoneName}<div className="mt-1 text-[10px] text-slate-500">{status}</div></td>
                                    <td className="px-2 py-2 text-right tabular-nums">{before ? `${(before.p_danger * 100).toFixed(1)}%` : "—"}</td>
                                    <td className="px-2 py-2 text-right tabular-nums">{after ? `${(after.p_danger * 100).toFixed(1)}%` : "—"}</td>
                                    <td className="py-2 pl-2 text-right tabular-nums">{zoneChange === null ? "—" : `${zoneChange > 0 ? "+" : ""}${zoneChange.toFixed(1)} pp`}</td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                        <div className="mt-3 grid grid-cols-2 gap-3">
                          <div>
                            <p className="text-xs text-slate-400">Baseline time to danger</p>
                            <p className="mt-1 font-semibold">{baselineScore.min_minutes_to_danger == null ? "Not reached" : `${baselineScore.min_minutes_to_danger.toFixed(1)} min`}</p>
                          </div>
                          <div>
                            <p className="text-xs text-slate-400">Selected plan time to danger</p>
                            <p className="mt-1 font-semibold">{planScore.min_minutes_to_danger == null ? "Not reached" : `${planScore.min_minutes_to_danger.toFixed(1)} min`}</p>
                          </div>
                        </div>
                      </div>
                    </>
                  )}
                  <p className="text-xs text-amber-300">Simulation only. These results do not execute or authorize real-world actions. A lower maximum danger probability does not guarantee every zone is safer.</p>
                </div>
              )}
            </article>
          </div>
        </section>
        
        
        <section className="mt-6 rounded-2xl border border-white/10 bg-[#0e1624] p-5 sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-widest text-cyan-300">
                AI planning
              </p>
              <h3 className="mt-2 text-xl font-semibold">
                Ranked recommendations
              </h3>
              <p className="mt-1 text-sm text-slate-400">
                Generate candidate interventions, simulate their forecast outcomes,
                and compare them with baseline risk.
              </p>
            </div>

            <button
              type="button"
              onClick={handleGetRecommendations}
              disabled={recommendationLoading}
              className="rounded-xl bg-cyan-300 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {recommendationLoading
                ? "Generating plans..."
                : "Generate recommendations"}
            </button>
          </div>

        {recommendationError && (
          <div
              role="alert"
              className="mt-4 rounded-xl border border-red-400/30 bg-red-400/10 p-3 text-sm text-red-200"
            >
              {recommendationError}
            </div>
          )}

          {recommendationLoading && (
            <p className="mt-4 text-sm text-slate-400">
              The AI planner is generating candidate plans and scoring their simulated
              outcomes. This may take a little while.
            </p>
          )}

          {recommendations && (
            <div className="mt-6 space-y-5">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div className="rounded-xl border border-white/10 p-4">
                  <p className="text-xs text-slate-400">Baseline maximum danger</p>
                  <p className="mt-2 text-2xl font-semibold">
                    {(recommendations.baseline.max_p_danger * 100).toFixed(1)}%
                  </p>
                </div>

                <div className="rounded-xl border border-white/10 p-4">
                  <p className="text-xs text-slate-400">Candidates considered</p>

                  <div className="mt-2 flex items-center justify-between gap-2">
                    <p className="text-2xl font-semibold">
                      {recommendations.candidates_considered}
                    </p>

                    <span className="rounded-full bg-gray-100 px-2 py-1 text-xs text-gray-700">
                      {recommendations.generation_source === "fallback"
                        ? "Fallback plans"
                        : recommendations.generation_source === "user_supplied"
                          ? "User-supplied plans"
                          : "AI-generated plans"}
                      </span>
                    </div>
                  </div>

                <div className="rounded-xl border border-white/10 p-4">
                  <p className="text-xs text-slate-400">Recommended plan</p>
                  <p className="mt-2 text-2xl font-semibold">
                    {recommendations.recommended_plan_id}
                  </p>
                </div>
              </div>

              {recommendations.recommendations.length === 0 && (
                <p className="text-sm text-amber-300">
                  The API returned no ranked plans. Check the backend response.
                </p>
              )}

              <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
                {recommendations.recommendations.map((item) => {
                  const baselineRisk =
                    recommendations.baseline.max_p_danger;
                  const planRisk = item.score.max_p_danger;
                  const change = (planRisk - baselineRisk) * 100;
                  const isRecommended =
                    item.plan.plan_id === recommendations.recommended_plan_id;

                  return (
                    <article
                      key={item.plan.plan_id}
                      className={`rounded-xl border p-4 ${
                        isRecommended
                          ? "border-cyan-300/50 bg-cyan-300/[0.06]"
                          : "border-white/10 bg-white/[0.02]"
                      }`}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                          Rank {item.rank}
                        </span>

                        {isRecommended && (
                          <span className="rounded-full border border-cyan-300/30 px-2 py-1 text-xs text-cyan-200">
                            Top recommendation
                          </span>
                        )}
                      </div>

                      <h4 className="mt-3 font-semibold">
                        {item.plan.strategy}
                      </h4>
                      <p className="mt-1 text-xs text-slate-500">
                        {item.plan.plan_id}
                      </p>

                      <div className="mt-4 grid grid-cols-2 gap-3">
                        <div>
                          <p className="text-xs text-slate-400">Max danger</p>
                          <p className="mt-1 text-xl font-semibold">
                            {(planRisk * 100).toFixed(1)}%
                          </p>
                        </div>
                        <div>
                          <p className="text-xs text-slate-400">Vs baseline</p>
                          <p
                            className={`mt-1 text-xl font-semibold ${
                              change < -0.05
                                ? "text-emerald-300"
                                : change > 0.05
                                  ? "text-red-300"
                                  : "text-slate-200"
                            }`}
                          >
                            {change > 0 ? "+" : ""}
                            {change.toFixed(1)} pp
                          </p>
                        </div>
                      </div>

                      <p className="mt-3 text-sm text-slate-300">
                        {item.explanation || item.plan.why}
                      </p>

                      <h5 className="mt-4 text-xs font-semibold uppercase tracking-wider text-slate-400">
                        Proposed actions
                      </h5>

                      {item.plan.actions.length === 0 ? (
                        <p className="mt-2 text-sm text-slate-400">
                          No intervention proposed.
                        </p>
                      ) : (
                        <ul className="mt-2 space-y-2">
                          {item.plan.actions.map((action, index) => (
                            <li
                              key={`${item.plan.plan_id}-${index}`}
                              className="rounded-lg bg-white/[0.04] p-3 text-sm"
                            >
                              <p className="font-medium">
                                {action.type.replaceAll("_", " ")}
                              </p>
                              <p className="mt-1 break-words text-xs text-slate-400">
                                {action.type === "hold_inflow"
                                  ? `Entry: ${action.entry ?? "—"} · ${action.minutes ?? "—"} minutes`
                                  : action.type === "gate"
                                    ? `Link: ${action.link ?? "—"} · State: ${action.state ?? "—"}`
                                    : action.type === "move_officers"
                                      ? `${action.count ?? "—"} officers: ${action.from_zone ?? "—"} → ${action.to_zone ?? "—"}`
                                      : action.type === "announce"
                                        ? `Zone: ${action.zone ?? "—"} · ${action.text ?? ""}`
                                        : "Review action details"}
                              </p>
                            </li>
                          ))}
                        </ul>
                      )}

                      <div className="mt-4 border-t border-white/10 pt-3 text-xs text-slate-400">
                        <p>
                          Time to danger:{" "}
                          {item.score.min_minutes_to_danger == null
                            ? "Not reached"
                            : `${item.score.min_minutes_to_danger.toFixed(1)} min`}
                        </p>
                      </div>
                    </article>
                  );
                })}
              </div>

              <p className="text-xs text-amber-300">
                Simulation only. These are model-generated recommendations, not
                authorization to execute real-world actions. A lower maximum danger
                probability does not guarantee every zone is safer.
              </p>
            </div>
          )}
        </section>


        <section className="rounded-xl border p-4 space-y-4">
          <h3 className="text-lg font-semibold">Gate Intervention</h3>

          <p className="text-sm opacity-75">
            Evaluate how opening or closing a link affects forecast risk.
          </p>

          <div className="space-y-2">
            <label htmlFor="gate-select" className="block text-sm font-medium">
              Select gate/link
            </label>

            <select
              id="gate-select"
              value={selectedGateId}
              onChange={(event) => setSelectedGateId(event.target.value)}
              className="w-full rounded-md border border-slate-600 bg-slate-900 p-2 text-white"
            >
              <option value="">Choose a link...</option>
              {venue?.links.map((link) => (
                <option key={link.id} value={link.id}>
                  {link.id}: {link.from} → {link.to} ({link.state})
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-2">
            <label htmlFor="gate-state" className="block text-sm font-medium">
              Evaluate link as
            </label>

            <select
              id="gate-state"
              value={gateState}
              onChange={(event) =>
                setGateState(event.target.value as "open" | "closed")
              }
              className="w-full rounded-md border border-slate-600 bg-slate-900 p-2 text-white"
            >
              <option value="closed">Closed</option>
              <option value="open">Open</option>
            </select>
          </div>

          <button
            type="button"
            onClick={handleScoreGateIntervention}
            disabled={gateScoring || !selectedGateId}
            className="rounded-md border px-4 py-2 disabled:opacity-50"
          >
            {gateScoring ? "Scoring gate..." : "Score Gate Intervention"}
          </button>

          {gateScore && baselineScore && (
            <div className="space-y-3">
              <h4 className="font-semibold">Forecast comparison</h4>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="rounded-lg border p-3">
                  <p className="text-sm opacity-75">Baseline maximum danger</p>
                  <p className="text-xl font-semibold">
                    {(baselineScore.max_p_danger * 100).toFixed(1)}%
                  </p>
                </div>

                <div className="rounded-lg border p-3">
                  <p className="text-sm opacity-75">Gate plan maximum danger</p>
                  <p className="text-xl font-semibold">
                    {(gateScore.max_p_danger * 100).toFixed(1)}%
                  </p>
                </div>
              </div>

              <p className="text-sm">
                Change in maximum danger:{" "}
                {(
                  (gateScore.max_p_danger - baselineScore.max_p_danger) *
                  100
                ).toFixed(1)}
                percentage points
              </p>

              <h4 className="font-semibold">Zone-by-zone comparison</h4>

              <div className="space-y-2">
                {gateScore.zones.map((zone) => {
                  const baselineZone = baselineScore.zones.find(
                    (item) => item.zone === zone.zone
                  );

                  return (
                    <div key={zone.zone} className="rounded-lg border p-3">
                      <p className="font-medium">{zone.zone}</p>
                      <p className="text-sm">
                        Baseline:{" "}
                        {baselineZone
                          ? `${(baselineZone.p_danger * 100).toFixed(1)}%`
                          : "N/A"}
                      </p>
                      <p className="text-sm">
                        Gate plan: {(zone.p_danger * 100).toFixed(1)}%
                      </p>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </section>

        {/* Venue Editor */}
        <section className="mt-6 rounded-2xl border border-white/10 bg-[#0e1624] p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="text-lg font-semibold">Venue Editor</h3>
              <p className="mt-1 text-sm text-slate-400">
                Edit zone details and link states, then save your venue.
              </p>
            </div>
            <button
              onClick={handleSaveVenue}
              disabled={!editedVenue || savingVenue}
              className="rounded-xl bg-cyan-300 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {savingVenue ? "Saving..." : "Save venue"}
            </button>
          </div>

          {saveMessage && (
            <p className="mt-3 text-sm text-cyan-200" role="status">
              {saveMessage}
            </p>
          )}

          {!editedVenue ? (
            <p className="mt-5 text-sm text-slate-400">
              Waiting for venue data...
            </p>
          ) : (
            <>
              <div className="mt-5">
                <label
                  htmlFor="venue-name"
                  className="mb-2 block text-xs text-slate-400"
                >
                  Venue name
                </label>
                <input
                  id="venue-name"
                  value={editedVenue.name}
                  onChange={(event) =>
                    setEditedVenue({
                      ...editedVenue,
                      name: event.target.value,
                    })
                  }
                  className="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm outline-none focus:border-cyan-300/50"
                />
              </div>

              <h4 className="mt-6 font-medium">Zones</h4>
              <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
                {editedVenue.zones.map((zone, index) => (
                  <div
                    key={zone.id}
                    className="rounded-xl border border-white/10 bg-white/[0.025] p-4"
                  >
                    <p className="mb-3 text-xs font-semibold text-cyan-200">
                      Zone {zone.id}
                    </p>

                    <label
                      htmlFor={`zone-name-${zone.id}`}
                      className="mb-1 block text-xs text-slate-400"
                    >
                      Zone name
                    </label>
                    <input
                      id={`zone-name-${zone.id}`}
                      value={zone.name}
                      onChange={(event) => {
                        const zones = [...editedVenue.zones];
                        zones[index] = {
                          ...zone,
                          name: event.target.value,
                        };
                        setEditedVenue({ ...editedVenue, zones });
                      }}
                      className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm outline-none focus:border-cyan-300/50"
                    />

                    <label
                      htmlFor={`zone-area-${zone.id}`}
                      className="mb-1 mt-3 block text-xs text-slate-400"
                    >
                      Area (m²)
                    </label>
                    <input
                      id={`zone-area-${zone.id}`}
                      type="number"
                      min="1"
                      step="0.1"
                      value={zone.area_m2}
                      onChange={(event) => {
                        const area = Number(event.target.value);
                        const zones = [...editedVenue.zones];
                        zones[index] = { ...zone, area_m2: area };
                        setEditedVenue({ ...editedVenue, zones });
                      }}
                      className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm outline-none focus:border-cyan-300/50"
                    />
                  </div>
                ))}
              </div>

              <h4 className="mt-6 font-medium">Links and gates</h4>
              <div className="mt-3 space-y-3">
                {editedVenue.links.map((link, index) => (
                  <div
                    key={link.id}
                    className="grid grid-cols-1 gap-3 rounded-xl border border-white/10 bg-white/[0.025] p-4 sm:grid-cols-4 sm:items-end"
                  >
                    <div>
                      <p className="text-xs text-slate-400">Link</p>
                      <p className="mt-1 text-sm font-medium">{link.id}</p>
                      <p className="text-xs text-slate-500">
                        {link.from} → {link.to}
                      </p>
                    </div>

                    <div>
                      <label
                        htmlFor={`link-width-${link.id}`}
                        className="mb-1 block text-xs text-slate-400"
                      >
                        Width (m)
                      </label>
                      <input
                        id={`link-width-${link.id}`}
                        type="number"
                        min="0.1"
                        step="0.1"
                        value={link.width_m}
                        onChange={(event) => {
                          const links = [...editedVenue.links];
                          links[index] = {
                            ...link,
                            width_m: Number(event.target.value),
                          };
                          setEditedVenue({ ...editedVenue, links });
                        }}
                        className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm outline-none focus:border-cyan-300/50"
                      />
                    </div>

                    <div>
                      <label
                        htmlFor={`link-kind-${link.id}`}
                        className="mb-1 block text-xs text-slate-400"
                      >
                        Type
                      </label>
                      <select
                        id={`link-kind-${link.id}`}
                        value={link.kind}
                        onChange={(event) => {
                          const links = [...editedVenue.links];
                          links[index] = {
                            ...link,
                            kind: event.target.value,
                          };
                          setEditedVenue({ ...editedVenue, links });
                        }}
                        className="w-full rounded-lg border border-white/10 bg-[#111b2a] px-3 py-2 text-sm outline-none focus:border-cyan-300/50"
                      >
                        <option value="gate">Gate</option>
                        <option value="opening">Opening</option>
                        <option value="corridor">Corridor</option>
                      </select>
                    </div>

                    <div>
                      <label
                        htmlFor={`link-state-${link.id}`}
                        className="mb-1 block text-xs text-slate-400"
                      >
                        State
                      </label>
                      <select
                        id={`link-state-${link.id}`}
                        value={link.state}
                        onChange={(event) => {
                          const links = [...editedVenue.links];
                          links[index] = {
                            ...link,
                            state: event.target.value,
                          };
                          setEditedVenue({ ...editedVenue, links });
                        }}
                        className="w-full rounded-lg border border-white/10 bg-[#111b2a] px-3 py-2 text-sm outline-none focus:border-cyan-300/50"
                      >
                        <option value="open">Open</option>
                        <option value="closed">Closed</option>
                      </select>
                    </div>
                  </div>
                ))}
              </div>

              <p className="mt-4 text-xs text-slate-500">
                Changes stay in the editor until you save. Saving sends them
                to the Imagine API, which validates and activates the venue.
              </p>
            </>
          )}
        </section>

        <footer className="mt-7 flex flex-wrap items-center justify-between gap-2 border-t border-white/10 pt-4 text-xs text-slate-500">
          <span>Breathing Room · Imagine slice</span>
          <span>
            {venue?.name ?? "Demo venue"} ·{" "}
            {forecast ? "Forecast connected" : "Awaiting forecast"}
          </span>
        </footer>
      </div>
    </main>
  );
}
