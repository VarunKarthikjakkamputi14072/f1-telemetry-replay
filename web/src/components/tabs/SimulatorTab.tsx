"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { SimStrategy, Simulation, Stint } from "@/lib/types";
import { COMPOUND_COLOR, COMPOUND_LABEL } from "@/lib/format";

function StintBar({ stints, total }: { stints: Stint[]; total: number }) {
  return (
    <div className="flex h-6 w-full overflow-hidden rounded">
      {stints.map((s, i) => {
        const w = ((s.lapEnd - s.lapStart + 1) / total) * 100;
        return (
          <div
            key={i}
            title={`${s.compound}: laps ${s.lapStart}–${s.lapEnd}`}
            className="flex items-center justify-center border-r border-black/40 text-[10px] font-bold"
            style={{
              width: `${w}%`,
              background: COMPOUND_COLOR[s.compound] ?? "#888",
              color: s.compound === "HARD" ? "#000" : "#0008",
            }}
          >
            {w > 5 ? COMPOUND_LABEL[s.compound] : ""}
          </div>
        );
      })}
    </div>
  );
}

function Row({
  label,
  strat,
  total,
  highlight,
}: {
  label: string;
  strat: SimStrategy;
  total: number;
  highlight?: boolean;
}) {
  return (
    <div
      className={`flex items-center gap-3 rounded-lg p-2 ${
        highlight ? "bg-good/10" : ""
      }`}
    >
      <span className="w-24 shrink-0 text-xs">
        <span className="font-semibold">{label}</span>
        <span className="block text-muted-2">{strat.stops}-stop</span>
      </span>
      <div className="flex-1">
        <StintBar stints={strat.stints} total={total} />
      </div>
      <span
        className={`tnum w-16 text-right text-sm font-semibold ${
          strat.deltaToOptimal === 0 ? "text-good" : "text-muted"
        }`}
      >
        {strat.deltaToOptimal === 0
          ? "optimal"
          : `+${strat.deltaToOptimal.toFixed(1)}s`}
      </span>
    </div>
  );
}

export default function SimulatorTab({
  simulation,
  totalLaps,
}: {
  simulation: Simulation;
  totalLaps: number;
}) {
  const { optimal, alternatives, distribution, winner, nSims } = simulation;

  return (
    <div className="space-y-4">
      <div className="panel p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-bold">Strategy simulator</h2>
          <span className="rounded-md bg-purple/15 px-2 py-1 text-xs font-semibold text-purple">
            {nSims.toLocaleString()} Monte Carlo races
          </span>
        </div>
        <p className="mt-2 max-w-3xl text-sm text-muted-2">
          A clear-air pace model (compound offsets, tyre degradation with a cliff,
          and the model&apos;s fuel-burn effect) is run thousands of times per
          strategy with random safety cars. Strategies are ranked by mean race
          time — exactly what a real strategy department simulates.
        </p>

        <div className="mt-4 space-y-1">
          <Row label="Optimal" strat={optimal} total={totalLaps} highlight />
          {alternatives.map((a, i) => (
            <Row key={i} label={`Alt ${i + 1}`} strat={a} total={totalLaps} />
          ))}
          {winner && (
            <div className="mt-2 border-t border-border-soft pt-2">
              <Row
                label={`Winner ${winner.code ?? ""}`}
                strat={winner}
                total={totalLaps}
              />
              <p className="px-2 text-xs text-muted-2">
                The race winner&apos;s actual strategy was{" "}
                <span className="text-text">
                  {winner.deltaToOptimal <= 1
                    ? "essentially optimal"
                    : `+${winner.deltaToOptimal.toFixed(1)}s off the simulated optimum`}
                </span>{" "}
                in pure clear-air pace — real strategy also trades time for track
                position and reacts to safety cars.
              </p>
            </div>
          )}
        </div>
      </div>

      <div className="panel p-5">
        <h3 className="text-base font-bold">Finish-time spread</h3>
        <p className="mb-3 text-xs text-muted-2">
          The optimal strategy&apos;s race-time distribution across the simulated
          safety-car scenarios (seconds relative to its mean).
        </p>
        <div className="h-[220px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={distribution} margin={{ top: 6, right: 12, bottom: 4, left: -18 }}>
              <CartesianGrid stroke="#1d212b" />
              <XAxis
                dataKey="t"
                stroke="#5d6373"
                tick={{ fontSize: 11 }}
                tickFormatter={(v) => `${v > 0 ? "+" : ""}${v}s`}
              />
              <YAxis stroke="#5d6373" tick={{ fontSize: 11 }} />
              <Tooltip
                contentStyle={{ background: "#101218", border: "1px solid #262a35", borderRadius: 8, fontSize: 12 }}
                formatter={(v) => [`${v} sims`, "count"]}
                labelFormatter={(l) => `${Number(l) > 0 ? "+" : ""}${l}s`}
              />
              <Bar dataKey="count" fill="#b14bff" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
