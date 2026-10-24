"use client";

import ActPanel from "@/components/ActPanel";
import ImaginePanel from "@/components/ImaginePanel";
import SensePanel from "@/components/SensePanel";
import { ago, useBus, useNow } from "@/lib/bus";

export default function Home() {
  return (
    <div className="mx-auto flex max-w-[1600px] flex-col gap-4 p-4">
      <Header />
      <main className="grid grid-cols-1 items-start gap-4 lg:grid-cols-3">
        <SensePanel />
        <ImaginePanel />
        <ActPanel />
      </main>
      <RawFeed />
    </div>
  );
}

function Header() {
  const { connected, messages } = useBus();
  return (
    <header className="flex flex-wrap items-center justify-between gap-2">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Breathing Room</h1>
        <p className="text-sm text-zinc-500">Spotting a surge isn&apos;t the same as preventing one.</p>
      </div>
      <div className="flex items-center gap-2 text-sm">
        <span className={`h-2.5 w-2.5 rounded-full ${connected ? "bg-emerald-500" : "bg-red-500"}`} aria-hidden />
        <span>{connected ? "Live" : "Disconnected, retrying…"}</span>
        <span className="text-zinc-500">· {messages.toLocaleString()} messages</span>
      </div>
    </header>
  );
}

// For debugging integration: every message as it arrives.
function RawFeed() {
  const { raw } = useBus();
  const now = useNow(2000);
  return (
    <details className="rounded-2xl border border-zinc-200 bg-white p-4 text-sm dark:border-zinc-800 dark:bg-zinc-900">
      <summary className="cursor-pointer font-medium">Raw messages (debug)</summary>
      <ul className="mt-2 max-h-80 overflow-y-auto font-mono text-xs">
        {raw.map((m, i) => (
          <li key={i} className="truncate border-t border-zinc-100 py-1 dark:border-zinc-800">
            <span className="text-zinc-500">{ago(m.at, now)}</span> <b>{m.topic}</b> {JSON.stringify(m.data)}
          </li>
        ))}
      </ul>
    </details>
  );
}
