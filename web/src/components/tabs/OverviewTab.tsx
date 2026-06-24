"use client";

import { useMemo } from "react";
import type { RaceData } from "@/lib/types";
import { fmtLapTime } from "@/lib/format";
import { raceHasRain } from "@/lib/eventsUtil";

export type SectionId =
  | "replay"
  | "strategy"
  | "pace"
  | "compare"
  | "engineer"
  | "simulator"
  | "ask";

interface Section {
  id: SectionId;
  title: string;
  desc: string;
}

const GROUPS: { group: string; items: Section[] }[] = [
  {
    group: "Watch",
    items: [
      {
        id: "replay",
        title: "Race Replay",
        desc: "Scrub the race on track with the live timing tower, onboard camera, race-control flags and key-moment markers.",
      },
    ],
  },
  {
    group: "Analyse",
    items: [
      { id: "strategy", title: "Tyre Strategy", desc: "Every driver's stints and pit stops across the race." },
      { id: "pace", title: "Pace & Sectors", desc: "Mini-sector dominance map, position-change spaghetti and gap-to-leader." },
      { id: "compare", title: "Head-to-Head", desc: "Two drivers compared: distance-aligned delta, speed and throttle." },
    ],
  },
  {
    group: "AI & Strategy",
    items: [
      { id: "engineer", title: "AI Engineer", desc: "Independent pit calls graded against reality, plus the trained tyre/pace model." },
      { id: "simulator", title: "Strategy Simulator", desc: "Monte Carlo the optimal strategy and the finish-time spread." },
      { id: "ask", title: "Ask the Strategist", desc: "Ask anything about the race — grounded answers with lap/driver citations." },
    ],
  },
];

export default function OverviewTab({
  data,
  onNavigate,
}: {
  data: RaceData;
  onNavigate: (id: SectionId) => void;
}) {
  const { meta, analytics, laps, events } = data;

  const summary = useMemo(() => {
    const finalPos: Record<string, number> = {};
    for (const [c, m] of Object.entries(analytics.positionByLap)) {
      const lks = Object.keys(m).map(Number);
      if (lks.length) finalPos[c] = m[String(Math.max(...lks))];
    }
    const podium = Object.entries(finalPos)
      .sort((a, b) => a[1] - b[1])
      .slice(0, 3)
      .map(([code, pos]) => ({ code, pos }));
    let fl: { code: string; t: number } | null = null;
    for (const [code, recs] of Object.entries(laps))
      for (const r of recs)
        if (r.lapTime && r.lapTime > 0 && (!fl || r.lapTime < fl.t)) fl = { code, t: r.lapTime };
    return { podium, fl, wet: raceHasRain(events) };
  }, [analytics, laps, events]);

  const nameOf = Object.fromEntries(meta.drivers.map((d) => [d.code, d.name]));
  const colorOf = Object.fromEntries(meta.drivers.map((d) => [d.code, d.color]));

  return (
    <div className="space-y-6">
      {/* Result summary */}
      <div className="panel flex flex-wrap items-center gap-x-8 gap-y-4 p-5">
        <div className="flex gap-5">
          {summary.podium.map((p) => (
            <div key={p.code} className="flex items-center gap-2">
              <span className="tnum text-2xl font-black text-muted-2">P{p.pos}</span>
              <div>
                <div className="flex items-center gap-1.5">
                  <span className="h-3 w-1 rounded" style={{ background: colorOf[p.code] }} />
                  <span className="font-bold">{p.code}</span>
                </div>
                <div className="text-[11px] text-muted-2">{nameOf[p.code]}</div>
              </div>
            </div>
          ))}
        </div>
        <div className="flex gap-6 text-sm text-muted">
          <Fact label="Laps" value={String(meta.totalLaps)} />
          {summary.fl && (
            <Fact label="Fastest lap" value={`${summary.fl.code} ${fmtLapTime(summary.fl.t)}`} />
          )}
          <Fact label="Conditions" value={summary.wet ? "Wet" : "Dry"} />
          <Fact label="Drivers" value={String(meta.drivers.length)} />
        </div>
      </div>

      {/* Section cards, grouped */}
      {GROUPS.map((g) => (
        <div key={g.group}>
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-widest text-muted-2">
            {g.group}
          </h3>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {g.items.map((s) => (
              <button
                key={s.id}
                onClick={() => onNavigate(s.id)}
                className="panel group flex flex-col p-4 text-left transition hover:border-accent"
              >
                <span className="flex items-center justify-between text-base font-bold">
                  {s.title}
                  <span className="text-muted-2 transition group-hover:text-accent">→</span>
                </span>
                <span className="mt-1 text-sm text-muted-2">{s.desc}</span>
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-muted-2">{label}</div>
      <div className="tnum font-bold text-text">{value}</div>
    </div>
  );
}
