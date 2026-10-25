
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
  const [showPlan, setShowPlan] = useState(false);
  const [editedVenue, setEditedVenue] = useState<VenueData | null>(null);
  const [savingVenue, setSavingVenue] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [venue, setVenue] = useState<VenueData | null>(null);
  const [forecast, setForecast] = useState<ForecastData | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
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

          <button
            onClick={() => setShowPlan((current) => !current)}
            className="rounded-xl bg-cyan-300 px-5 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-200"
          >
            {showPlan ? "Hide plan preview" : "Preview intervention"}
          </button>
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
              <h3 className="font-semibold">Intervention preview</h3>
              <p className="mt-1 text-xs text-slate-400">
                Illustrative actions only; not sent to the planner
              </p>

              {showPlan ? (
                <div className="mt-4 space-y-3 text-sm">
                  <div className="rounded-xl border border-cyan-300/20 bg-cyan-300/[0.06] p-3">
                    <p className="font-medium text-cyan-200">
                      01 · Review arrival control
                    </p>
                    <p className="mt-1 text-xs text-slate-400">
                      Evaluate whether temporarily holding new arrivals could
                      reduce pressure on the entrance.
                    </p>
                  </div>
                  <div className="rounded-xl border border-cyan-300/20 bg-cyan-300/[0.06] p-3">
                    <p className="font-medium text-cyan-200">
                      02 · Review alternate routes
                    </p>
                    <p className="mt-1 text-xs text-slate-400">
                      Check whether the side exit and connecting routes are
                      available before proposing a change.
                    </p>
                  </div>
                  <p className="text-xs text-amber-300">
                    Preview only. No action has been scored, approved, or
                    executed.
                  </p>
                </div>
              ) : (
                <button
                  onClick={() => setShowPlan(true)}
                  className="mt-4 w-full rounded-xl border border-white/10 px-4 py-3 text-sm text-slate-300 transition hover:bg-white/5"
                >
                  Show example actions
                </button>
              )}
            </article>
          </div>
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
