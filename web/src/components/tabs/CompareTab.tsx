"use client";

import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Meta, Traces } from "@/lib/types";
import { fmtLapTime } from "@/lib/format";

interface Props {
  meta: Meta;
  traces: Traces;
}

const AXIS = "#5d6373";
const GRID = "#1d212b";

function interp(grid: number[], x: number[], y: number[]): number[] {
  const out = new Array(grid.length);
  let j = 0;
  for (let i = 0; i < grid.length; i++) {
    const g = grid[i];
    while (j < x.length - 2 && x[j + 1] < g) j++;
    const x0 = x[j];
    const x1 = x[j + 1] ?? x0 + 1;
    const t = x1 === x0 ? 0 : (g - x0) / (x1 - x0);
    out[i] = y[j] + (y[j + 1] - y[j]) * t;
  }
  return out;
}

export default function CompareTab({ meta, traces }: Props) {
  const available = meta.drivers.filter((d) => traces[d.code]);
  const ranked = [...available].sort(
    (a, b) =>
      (traces[a.code].lapTime ?? 999) - (traces[b.code].lapTime ?? 999),
  );
  const [a, setA] = useState(ranked[0]?.code ?? "");
  // Default the rival to the quickest driver from a different team, so the two
  // overlaid traces aren't the same colour.
  const [b, setB] = useState(() => {
    const teamA = ranked[0]?.team;
    return (ranked.find((d) => d.team !== teamA) ?? ranked[1])?.code ?? "";
  });

  const colorA = meta.drivers.find((d) => d.code === a)?.color ?? "#fff";
  const colorB = meta.drivers.find((d) => d.code === b)?.color ?? "#888";

  const { rows, lapA, lapB } = useMemo(() => {
    const tA = traces[a];
    const tB = traces[b];
    if (!tA || !tB) return { rows: [], lapA: null, lapB: null };
    const grid = tA.dist;
    const bSpd = interp(grid, tB.dist, tB.spd);
    const bThr = interp(grid, tB.dist, tB.thr);

    // Cumulative time along the lap from speed: dt = dx / v.
    let ta = 0;
    let tb = 0;
    const rows = grid.map((d, i) => {
      if (i > 0) {
        const dx = d - grid[i - 1];
        const va = Math.max(8, (tA.spd[i] + tA.spd[i - 1]) / 2) / 3.6;
        const vb = Math.max(8, (bSpd[i] + bSpd[i - 1]) / 2) / 3.6;
        ta += dx / va;
        tb += dx / vb;
      }
      return {
        dist: Math.round(d),
        spdA: tA.spd[i],
        spdB: bSpd[i],
        thrA: tA.thr[i],
        thrB: bThr[i],
        delta: +(ta - tb).toFixed(3),
      };
    });
    return { rows, lapA: tA.lapTime, lapB: tB.lapTime };
  }, [a, b, traces]);

  const Picker = ({
    value,
    onChange,
    color,
  }: {
    value: string;
    onChange: (v: string) => void;
    color: string;
  }) => (
    <div className="flex items-center gap-2">
      <span className="h-4 w-1.5 rounded" style={{ background: color }} />
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-border bg-panel-2 px-2 py-1 text-sm text-text outline-none"
      >
        {available.map((d) => (
          <option key={d.code} value={d.code}>
            {d.code} — {d.name}
          </option>
        ))}
      </select>
    </div>
  );

  const tooltip = {
    contentStyle: {
      background: "#101218",
      border: "1px solid #262a35",
      borderRadius: 8,
      fontSize: 12,
    },
  };

  return (
    <div className="space-y-4">
      <div className="panel flex flex-wrap items-center justify-between gap-4 p-4">
        <div className="flex flex-wrap items-center gap-4">
          <Picker value={a} onChange={setA} color={colorA} />
          <span className="text-muted-2">vs</span>
          <Picker value={b} onChange={setB} color={colorB} />
        </div>
        <div className="flex gap-5 text-sm">
          <span className="tnum" style={{ color: colorA }}>
            {a} {fmtLapTime(lapA)}
          </span>
          <span className="tnum" style={{ color: colorB }}>
            {b} {fmtLapTime(lapB)}
          </span>
        </div>
      </div>

      <div className="panel p-5">
        <h2 className="text-lg font-bold">Delta time</h2>
        <p className="mb-4 text-sm text-muted-2">
          Cumulative time gap along their quickest laps, aligned by track
          distance. Above zero, <span style={{ color: colorB }}>{b}</span> is
          ahead; below, <span style={{ color: colorA }}>{a}</span> is.
        </p>
        <div className="h-[260px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={rows} margin={{ top: 6, right: 12, bottom: 6, left: -8 }}>
              <CartesianGrid stroke={GRID} />
              <XAxis
                dataKey="dist"
                stroke={AXIS}
                tick={{ fontSize: 11 }}
                tickFormatter={(v) => `${(v / 1000).toFixed(1)}km`}
              />
              <YAxis
                stroke={AXIS}
                tick={{ fontSize: 11 }}
                width={48}
                tickFormatter={(v) => `${v > 0 ? "+" : ""}${v.toFixed(1)}`}
              />
              <ReferenceLine y={0} stroke="#3a3f4d" />
              <Tooltip
                {...tooltip}
                formatter={(value) => {
                  const v = Number(value);
                  return `${v > 0 ? "+" : ""}${v.toFixed(3)}s`;
                }}
                labelFormatter={(v) => `${v} m`}
              />
              <Line
                type="monotone"
                dataKey="delta"
                stroke="#e8eaf0"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="panel p-5">
          <h2 className="text-base font-bold">Speed</h2>
          <div className="mt-3 h-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={rows} margin={{ top: 6, right: 8, bottom: 6, left: -12 }}>
                <CartesianGrid stroke={GRID} />
                <XAxis
                  dataKey="dist"
                  stroke={AXIS}
                  tick={{ fontSize: 11 }}
                  tickFormatter={(v) => `${(v / 1000).toFixed(1)}`}
                />
                <YAxis stroke={AXIS} tick={{ fontSize: 11 }} width={36} />
                <Tooltip {...tooltip} />
                <Line type="monotone" dataKey="spdA" name={a} stroke={colorA} strokeWidth={1.6} dot={false} isAnimationActive={false} />
                <Line type="monotone" dataKey="spdB" name={b} stroke={colorB} strokeWidth={1.6} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="panel p-5">
          <h2 className="text-base font-bold">Throttle</h2>
          <div className="mt-3 h-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={rows} margin={{ top: 6, right: 8, bottom: 6, left: -12 }}>
                <CartesianGrid stroke={GRID} />
                <XAxis
                  dataKey="dist"
                  stroke={AXIS}
                  tick={{ fontSize: 11 }}
                  tickFormatter={(v) => `${(v / 1000).toFixed(1)}`}
                />
                <YAxis stroke={AXIS} tick={{ fontSize: 11 }} width={36} domain={[0, 100]} />
                <Tooltip {...tooltip} />
                <Line type="monotone" dataKey="thrA" name={a} stroke={colorA} strokeWidth={1.6} dot={false} isAnimationActive={false} />
                <Line type="monotone" dataKey="thrB" name={b} stroke={colorB} strokeWidth={1.6} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
}
