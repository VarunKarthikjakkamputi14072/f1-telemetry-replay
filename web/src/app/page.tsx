"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { getManifest } from "@/lib/data";
import type { RaceSummary } from "@/lib/types";

export default function Home() {
  const [races, setRaces] = useState<RaceSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    getManifest()
      .then((m) => setRaces(m.races.slice()))
      .catch((e) => setError(String(e)));
  }, []);

  // Filter by free text, then group by season (newest first).
  const seasons = useMemo<[number, RaceSummary[]][]>(() => {
    if (!races) return [];
    const q = query.trim().toLowerCase();
    const filtered = q
      ? races.filter((r) =>
          `${r.race} ${r.circuit} ${r.country} ${r.year}`
            .toLowerCase()
            .includes(q),
        )
      : races;
    const byYear = new Map<number, RaceSummary[]>();
    for (const r of filtered) {
      const arr = byYear.get(r.year) ?? [];
      arr.push(r);
      byYear.set(r.year, arr);
    }
    return [...byYear.entries()]
      .map(([y, list]): [number, RaceSummary[]] => [
        y,
        list.sort((a, b) => a.round - b.round),
      ])
      .sort((a, b) => b[0] - a[0]);
  }, [races, query]);

  return (
    <main className="mx-auto w-full max-w-5xl px-6 py-16">
      <header className="mb-14">
        <div className="flex items-center gap-3">
          <span className="inline-block h-7 w-1.5 rounded bg-accent" />
          <h1 className="text-5xl font-black tracking-tight">APEX</h1>
        </div>
        <p className="mt-4 max-w-2xl text-lg text-muted">
          A broadcast-style Formula 1 race replay and analytics studio. Real
          telemetry from <span className="text-text">FastF1</span>,
          distance-aligned timing gaps, tyre strategy, and side-by-side driver
          comparison — rebuilt for the browser.
        </p>
        <div className="mt-5 flex flex-wrap gap-2 text-xs text-muted-2">
          {[
            "60 fps canvas replay",
            "Real time gaps (not metres ÷ 70)",
            "Tyre stint strategy",
            "Distance-aligned telemetry",
          ].map((t) => (
            <span
              key={t}
              className="rounded-full border border-border px-3 py-1"
            >
              {t}
            </span>
          ))}
        </div>
      </header>

      <div className="mb-4 flex items-center justify-between gap-4">
        <h2 className="text-sm font-semibold uppercase tracking-widest text-muted-2">
          Select a Grand Prix
        </h2>
        {races && races.length > 3 && (
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search race, circuit, year…"
            className="w-56 rounded-md border border-border bg-panel-2 px-3 py-1.5 text-sm text-text outline-none transition focus:border-accent placeholder:text-muted-2"
          />
        )}
      </div>

      {error && (
        <p className="text-accent-2">Could not load race index: {error}</p>
      )}

      {!races && !error && (
        <div className="grid gap-4 sm:grid-cols-2">
          {Array.from({ length: 2 }).map((_, i) => (
            <div key={i} className="skeleton h-28 rounded-xl" />
          ))}
        </div>
      )}

      {seasons.map(([year, list]) => (
        <section key={year} className="mb-8">
          <div className="mb-3 flex items-baseline gap-3">
            <h3 className="text-2xl font-black tracking-tight">{year}</h3>
            <span className="text-xs text-muted-2">
              {list.length} race{list.length > 1 ? "s" : ""}
            </span>
            <div className="h-px flex-1 bg-border-soft" />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            {list.map((r) => (
              <Link
                key={r.id}
                href={`/race/${r.year}/${r.round}`}
                className="panel group relative overflow-hidden p-5 transition hover:border-accent"
              >
                <div className="absolute -right-6 -top-8 text-[120px] font-black leading-none text-white/[0.03] transition group-hover:text-accent/[0.06]">
                  {r.round}
                </div>
                <div className="relative">
                  <div className="flex items-center gap-2 text-xs text-muted-2">
                    <span className="tnum">{r.year}</span>
                    <span>·</span>
                    <span>Round {r.round}</span>
                  </div>
                  <h3 className="mt-1 text-2xl font-bold tracking-tight">
                    {r.race}
                  </h3>
                  <div className="mt-3 flex gap-5 text-sm text-muted">
                    <span>
                      <span className="tnum text-text">{r.totalLaps}</span> laps
                    </span>
                    <span>
                      <span className="tnum text-text">{r.drivers}</span> drivers
                    </span>
                    <span>{r.circuit}</span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </section>
      ))}

      {races && races.length > 0 && seasons.length === 0 && (
        <p className="text-muted">No races match “{query}”.</p>
      )}

      {races && races.length === 0 && (
        <p className="text-muted">
          No races exported yet. Run{" "}
          <code className="rounded bg-panel-2 px-1.5 py-0.5 text-text">
            python -m pipeline.export --year 2021 --race &quot;Abu Dhabi&quot;
          </code>
        </p>
      )}

      <footer className="mt-20 border-t border-border-soft pt-6 text-xs text-muted-2">
        Telemetry via FastF1. Not affiliated with Formula 1. Built as a
        portfolio project.
      </footer>
    </main>
  );
}
