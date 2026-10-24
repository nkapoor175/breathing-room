// Small shared building blocks so the three panels look like one product.
import type { ReactNode } from "react";

export function Panel({ title, owner, badge, children }: { title: string; owner: string; badge?: ReactNode; children: ReactNode }) {
  return (
    <section className="flex min-w-0 flex-col gap-4 rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <header className="flex items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
        <div className="flex items-center gap-2 text-xs text-zinc-500">
          {badge}
          <span>{owner}</span>
        </div>
      </header>
      {children}
    </section>
  );
}

export function Section({ title, right, children }: { title: string; right?: ReactNode; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">{title}</h3>
        {right && <span className="text-xs text-zinc-500">{right}</span>}
      </div>
      {children}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="rounded-lg border border-dashed border-zinc-300 p-3 text-sm text-zinc-500 dark:border-zinc-700">{children}</p>;
}

export function Pill({ className = "", children }: { className?: string; children: ReactNode }) {
  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${className}`}>{children}</span>;
}

/** Tiny line chart of recent values (no axes): for density over the last 5 minutes. */
export function Sparkline({ values, max = 7, danger }: { values: number[]; max?: number; danger?: number }) {
  if (values.length < 2) return <span className="text-xs text-zinc-400">…</span>;
  const w = 80, h = 20;
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${h - (Math.min(v, max) / max) * h}`).join(" ");
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="overflow-visible text-zinc-700 dark:text-zinc-300" aria-hidden>
      {danger !== undefined && (
        <line x1={0} x2={w} y1={h - (danger / max) * h} y2={h - (danger / max) * h} stroke="currentColor" strokeOpacity={0.25} strokeDasharray="2 2" />
      )}
      <polyline points={pts} fill="none" stroke="currentColor" strokeWidth={1.5} />
    </svg>
  );
}
