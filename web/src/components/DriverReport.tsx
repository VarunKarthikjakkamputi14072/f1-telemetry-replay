"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { RaceData } from "@/lib/types";
import { COMPOUND_COLOR, fmtLapTime } from "@/lib/format";
import {
  bestLapTime,
  pitCount,
  racingLaps,
  scLapRanges,
} from "@/lib/driverReport";

const AXIS = "#5d6373";
const GRID = "#1d212b";

export default function DriverReport({
  data,
  code,
}: {
  data: RaceData;
  code: string;
}) {
  const { meta, laps, analytics, events, engineer } = data;
  const d = meta.drivers.find((x) => x.code === code);
  const recs = useMemo(() => laps[code] ?? [], [laps, code]);

  const report = useMemo(() => {
    const racing = racingLaps(recs);
    const scRanges = scLapRanges(events, recs);
    const inSC = (lap: number) =>
      scRanges.some((r) => lap >= r.lapStart && lap <= r.lapEnd);

    // Pace line: green-flag racing laps only (SC/pit excluded), so the gaps
    // line up with the shaded safety-car windows.
    const pace = racing
      .filter((l) => !inSC(l.lap!))
      .map((l) => ({ lap: l.lap!, lapTime: l.lapTime!, compound: l.compound }));

    const stints = analytics.stints[code] ?? [];
    // Degradation: lap time vs tyre age within each stint.
    const deg = stints.map((s) => {
      const pts = racing
        .filter((l) => l.lap! >= s.lapStart && l.lap! <= s.lapEnd && !inSC(l.lap!))
        .map((l) => ({ age: l.lap! - s.lapStart + 1, t: l.lapTime! }));
      return { stint: s, pts };
    });

    const pos = Object.entries(analytics.positionByLap[code] ?? {})
      .map(([lap, p]) => ({ lap: Number(lap), pos: p }))
      .sort((a, b) => a.lap - b.lap);
    const gap = analytics.gapToLeader[code] ?? [];

    // Sector bests vs the field's best.
    const mine = analytics.sectorBest[code] ?? {};
    const sectors = (["s1", "s2", "s3"] as const).map((s) => {
      const fieldBest = Math.min(
        ...Object.values(analytics.sectorBest)
          .map((b) => b[s])
          .filter((v): v is number => v != null && v > 0),
      );
      return {
        s,
        mine: mine[s] ?? null,
        fieldBest: isFinite(fieldBest) ? fieldBest : null,
        owner: analytics.sectorOwners[s] === code,
      };
    });

    return { pace, deg, scRanges, pos, gap, sectors };
  }, [recs, events, analytics, code]);

  const eng = engineer.drivers.find((x) => x.code === code);

  if (!d) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-20">
        <p className="text-accent-2">No data for {code}.</p>
        <Link href={`/race/${meta.year}/${meta.round}`} className="text-muted">
          ← Back
        </Link>
      </main>
    );
  }

  const best = bestLapTime(recs);
  const stops = pitCount(recs);
  const finalPos = report.pos.length ? report.pos[report.pos.length - 1].pos : null;

  const tooltip = {
    contentStyle: {
      background: "#101218",
      border: "1px solid #262a35",
      borderRadius: 8,
      fontSize: 12,
    },
  };

  return (
    <main className="mx-auto w-full max-w-[1100px] px-4 py-6">
      <Link
        href={`/race/${meta.year}/${meta.round}`}
        className="text-xs text-muted-2 transition hover:text-text"
      >
        ← {meta.race} {meta.year}
      </Link>

      {/* Header */}
      <div className="mt-2 mb-5 flex flex-wrap items-end gap-4">
        <div className="flex items-center gap-3">
          <span className="h-9 w-1.5 rounded" style={{ background: d.color }} />
          <div>
            <h1 className="text-3xl font-black tracking-tight">
              {d.code}{" "}
              <span className="tnum align-middle text-base font-medium text-muted-2">
                #{d.num}
              </span>
            </h1>
            <p className="text-sm text-muted">
              {d.name} · {d.team}
            </p>
          </div>
        </div>
        <div className="ml-auto flex gap-5 text-sm">
          <Stat label="Finish" value={finalPos ? `P${finalPos}` : "—"} />
          <Stat label="Best lap" value={fmtLapTime(best)} />
          <Stat label="Stops" value={String(stops)} />
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Lap pace */}
        <div className="panel p-5 lg:col-span-2">
          <h2 className="text-base font-bold">Lap pace</h2>
          <p className="mb-3 text-xs text-muted-2">
            Green-flag lap times, dots coloured by tyre. Shaded spans are safety
            car / VSC.
          </p>
          <div className="h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={report.pace} margin={{ top: 6, right: 12, bottom: 4, left: 4 }}>
                <CartesianGrid stroke={GRID} />
                {report.scRanges.map((r, i) => (
                  <ReferenceArea
                    key={i}
                    x1={r.lapStart}
                    x2={r.lapEnd}
                    fill="#ff8c1a"
                    fillOpacity={0.1}
                  />
                ))}
                <XAxis dataKey="lap" stroke={AXIS} tick={{ fontSize: 11 }} type="number" domain={["dataMin", "dataMax"]} />
                <YAxis
                  stroke={AXIS}
                  tick={{ fontSize: 11 }}
                  width={52}
                  domain={["dataMin - 0.5", "dataMax + 0.5"]}
                  tickFormatter={(v) => fmtLapTime(v)}
                />
                <Tooltip
                  {...tooltip}
                  formatter={(value) => fmtLapTime(Number(value))}
                  labelFormatter={(l) => `Lap ${l}`}
                />
                <Line
                  type="monotone"
                  dataKey="lapTime"
                  stroke="#3a3f4d"
                  strokeWidth={1}
                  isAnimationActive={false}
                  connectNulls={false}
                  dot={(props: { cx?: number; cy?: number; payload?: { compound?: string } }) => {
                    const { cx, cy, payload } = props;
                    if (cx == null || cy == null) return <g />;
                    return (
                      <circle
                        cx={cx}
                        cy={cy}
                        r={3}
                        fill={COMPOUND_COLOR[payload?.compound ?? ""] ?? "#888"}
                      />
                    );
                  }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Tyre degradation */}
        <div className="panel p-5">
          <h2 className="text-base font-bold">Tyre life</h2>
          <p className="mb-3 text-xs text-muted-2">
            Lap time vs tyre age, per stint — the slope is degradation.
          </p>
          <div className="h-[240px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart margin={{ top: 6, right: 12, bottom: 4, left: 4 }}>
                <CartesianGrid stroke={GRID} />
                <XAxis
                  type="number"
                  dataKey="age"
                  stroke={AXIS}
                  tick={{ fontSize: 11 }}
                  domain={["dataMin", "dataMax"]}
                  label={{ value: "Tyre age (laps)", position: "insideBottom", offset: -2, fill: AXIS, fontSize: 10 }}
                />
                <YAxis stroke={AXIS} tick={{ fontSize: 11 }} width={52} domain={["dataMin - 0.3", "dataMax + 0.3"]} tickFormatter={(v) => fmtLapTime(v)} />
                <Tooltip {...tooltip} formatter={(value) => fmtLapTime(Number(value))} />
                {report.deg.map((s, i) => (
                  <Line
                    key={i}
                    data={s.pts}
                    dataKey="t"
                    stroke={COMPOUND_COLOR[s.stint.compound] ?? "#888"}
                    strokeWidth={1.8}
                    dot={false}
                    isAnimationActive={false}
                    name={`${s.stint.compound} (L${s.stint.lapStart})`}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Sector bests */}
        <div className="panel p-5">
          <h2 className="text-base font-bold">Sector bests vs field</h2>
          <p className="mb-3 text-xs text-muted-2">
            Personal best per sector and the gap to the fastest car.
          </p>
          <div className="space-y-3 pt-1">
            {report.sectors.map((sec) => {
              const delta =
                sec.mine != null && sec.fieldBest != null
                  ? sec.mine - sec.fieldBest
                  : null;
              return (
                <div key={sec.s} className="flex items-center gap-3">
                  <span className="w-8 text-xs font-semibold uppercase text-muted-2">
                    {sec.s}
                  </span>
                  <span className="tnum w-20 text-sm text-text">
                    {sec.mine != null ? `${sec.mine.toFixed(3)}s` : "—"}
                  </span>
                  {sec.owner ? (
                    <span className="rounded bg-purple/20 px-2 py-0.5 text-[10px] font-bold text-purple">
                      FASTEST
                    </span>
                  ) : (
                    <span className="tnum text-xs text-muted-2">
                      {delta != null ? `+${delta.toFixed(3)}` : ""}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Position */}
        <div className="panel p-5">
          <h2 className="text-base font-bold">Track position</h2>
          <div className="mt-3 h-[180px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={report.pos} margin={{ top: 6, right: 12, bottom: 4, left: -20 }}>
                <CartesianGrid stroke={GRID} />
                <XAxis dataKey="lap" stroke={AXIS} tick={{ fontSize: 11 }} />
                <YAxis reversed domain={[1, meta.drivers.length]} stroke={AXIS} tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip {...tooltip} formatter={(value) => `P${Number(value)}`} labelFormatter={(l) => `Lap ${l}`} />
                <Line type="stepAfter" dataKey="pos" stroke={d.color} strokeWidth={2} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Gap to leader */}
        <div className="panel p-5">
          <h2 className="text-base font-bold">Gap to leader</h2>
          <div className="mt-3 h-[180px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={report.gap} margin={{ top: 6, right: 12, bottom: 4, left: -6 }}>
                <CartesianGrid stroke={GRID} />
                <XAxis dataKey="lap" stroke={AXIS} tick={{ fontSize: 11 }} />
                <YAxis reversed stroke={AXIS} tick={{ fontSize: 11 }} width={44} tickFormatter={(v) => `${v}s`} />
                <Tooltip {...tooltip} formatter={(value) => `+${Number(value).toFixed(1)}s`} labelFormatter={(l) => `Lap ${l}`} />
                <Line type="monotone" dataKey="gap" stroke={d.color} strokeWidth={2} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Engineer verdict */}
        {eng && (
          <div className="panel p-5 lg:col-span-2">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-bold">AI engineer&apos;s read</h2>
              <span className="tnum text-xs text-muted-2">
                {eng.agreement.pct}% match with reality
              </span>
            </div>
            <p className="mt-2 text-sm leading-relaxed text-muted">{eng.verdict}</p>
          </div>
        )}
      </div>
    </main>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="text-right">
      <div className="text-[10px] uppercase tracking-wider text-muted-2">{label}</div>
      <div className="tnum text-lg font-bold text-text">{value}</div>
    </div>
  );
}
