// Same numbers as common/thresholds.json (Next.js can't import files outside dashboard/).
export const CAUTION = 4.0; // people per m2
export const DANGER = 5.0;

// Density colours from spec S10: green < 2, yellow 2-4, orange 4-5, red >= 5.
export function densityTone(d: number): "green" | "yellow" | "orange" | "red" {
  if (d >= DANGER) return "red";
  if (d >= CAUTION) return "orange";
  if (d >= 2) return "yellow";
  return "green";
}

// Forecast colours from spec I08: green < 0.1, yellow to 0.3, red above.
export function dangerTone(p: number): "green" | "yellow" | "red" {
  if (p > 0.3) return "red";
  if (p >= 0.1) return "yellow";
  return "green";
}

export const TONE: Record<string, string> = {
  green: "bg-emerald-100 text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-200",
  yellow: "bg-yellow-100 text-yellow-900 dark:bg-yellow-900/40 dark:text-yellow-200",
  orange: "bg-orange-100 text-orange-900 dark:bg-orange-900/40 dark:text-orange-200",
  red: "bg-red-100 text-red-900 dark:bg-red-900/50 dark:text-red-200",
};
