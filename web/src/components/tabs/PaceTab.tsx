"use client";

import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Analytics, Meta } from "@/lib/types";

interface Props {
  meta: Meta;
  analytics: Analytics;
}

const AXIS = "#5d6373";
const GRID = "#1d212b";

export default function PaceTab({ meta, analytics }: Props) {
  const colorByCode = Object.fromEntries(
    meta.drivers.map((d) => [d.code, d.color]),
  );
  const codes = meta.drivers.map((d) => d.code);
  const [hover, setHover] = useState<string | null>(null);

  // Position by lap → one row per lap with a column per driver.
  const posData = useMemo(() => {
    const rows: Record<number, Record<string, number>> = {};
    for (const code of codes) {
      const m = analytics.positionByLap[code] ?? {};
      for (const [lapStr, pos] of Object.entries(m)) {
        const lap = Number(lapStr);
        (rows[lap] ??= { lap })[code] = pos;
      }
    }
    return Object.values(rows).sort((a, b) => a.lap - b.lap);
  }, [analytics, codes]);

  // Gap to leader by lap.
  const gapData = useMemo(() => {
    const rows: Record<number, Record<string, number>> = {};
    for (const code of codes) {
      for (const { lap, gap } of analytics.gapToLeader[code] ?? []) {
        (rows[lap] ??= { lap })[code] = gap;
      }
    }
    return Object.values(rows).sort((a, b) => a.lap - b.lap);
  }, [analytics, codes]);

  const lines = (key: "pos" | "gap") =>
    codes.map((code) => (
      <Line
        key={code}
        type="monotone"
        dataKey={code}
        stroke={colorByCode[code]}
        strokeWidth={hover === code ? 3 : 1.4}
        strokeOpacity={hover && hover !== code ? 0.18 : 1}
        dot={false}
        isAnimationActive={false}
        connectNulls
        name={code}
        onMouseEnter={() => key === "pos" && setHover(code)}
      />
    ));

  return (
    <div className="space-y-4">
      <div className="panel p-5">
        <h2 className="text-lg font-bold">Position changes</h2>
        <p className="mb-4 text-sm text-muted-2">
          The race as a spaghetti chart — every driver&apos;s track position,
          lap by lap. Hover a line to isolate it.
        </p>
        <div className="h-[360px]" onMouseLeave={() => setHover(null)}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={posData}
              margin={{ top: 6, right: 12, bottom: 6, left: -18 }}
            >
              <CartesianGrid stroke={GRID} />
              <XAxis
                dataKey="lap"
                stroke={AXIS}
                tick={{ fontSize: 11 }}
                label={{
                  value: "Lap",
                  position: "insideBottom",
                  offset: -2,
                  fill: AXIS,
                  fontSize: 11,
                }}
              />
              <YAxis
                reversed
                domain={[1, meta.drivers.length]}
                tick={{ fontSize: 11 }}
                stroke={AXIS}
                allowDecimals={false}
              />
              <Tooltip
                contentStyle={{
                  background: "#101218",
                  border: "1px solid #262a35",
                  borderRadius: 8,
                  fontSize: 12,
                }}
                itemSorter={(i) => Number(i.value)}
              />
              {lines("pos")}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="panel p-5">
        <h2 className="text-lg font-bold">Gap to leader</h2>
        <p className="mb-4 text-sm text-muted-2">
          Cumulative time behind the lap leader. Diverging lines are the field
          spreading out; converging lines are a chase or a safety car.
        </p>
        <div className="h-[320px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={gapData}
              margin={{ top: 6, right: 12, bottom: 6, left: -6 }}
            >
              <CartesianGrid stroke={GRID} />
              <XAxis
                dataKey="lap"
                stroke={AXIS}
                tick={{ fontSize: 11 }}
                label={{
                  value: "Lap",
                  position: "insideBottom",
                  offset: -2,
                  fill: AXIS,
                  fontSize: 11,
                }}
              />
              <YAxis
                reversed
                stroke={AXIS}
                tick={{ fontSize: 11 }}
                width={48}
                tickFormatter={(v) => `${v}s`}
              />
              <Tooltip
                contentStyle={{
                  background: "#101218",
                  border: "1px solid #262a35",
                  borderRadius: 8,
                  fontSize: 12,
                }}
                formatter={(value) => `+${Number(value).toFixed(1)}s`}
                itemSorter={(i) => Number(i.value)}
              />
              {lines("gap")}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
