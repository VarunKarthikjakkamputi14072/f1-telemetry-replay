"use client";

import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { PaceModel } from "@/lib/types";
import { COMPOUND_COLOR } from "@/lib/format";

const AXIS = "#5d6373";
const GRID = "#1d212b";
const FEATURE_LABEL: Record<string, string> = {
  trackTemp: "Track temp",
  fuelFrac: "Fuel load",
  age: "Tyre age",
  SOFT: "Soft",
  MEDIUM: "Medium",
  HARD: "Hard",
  INTER: "Inter",
  WET: "Wet",
};

export default function ModelPanel({ model }: { model: PaceModel }) {
  // Merge per-compound curves into one chart dataset keyed by age.
  const curveData = useMemo(() => {
    const rows: Record<number, Record<string, number>> = {};
    for (const [comp, pts] of Object.entries(model.curves)) {
      for (const p of pts) (rows[p.age] ??= { age: p.age })[comp] = p.pace;
    }
    return Object.values(rows).sort((a, b) => a.age - b.age);
  }, [model.curves]);

  const importances = Object.entries(model.importances).slice(0, 6);
  const maxImp = Math.max(...importances.map(([, v]) => v), 0.001);

  return (
    <div className="panel p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-bold">Tyre &amp; pace model</h2>
        <span className="rounded-md bg-purple/15 px-2 py-1 text-xs font-semibold text-purple">
          {model.model}
        </span>
      </div>
      <p className="mt-2 max-w-3xl text-sm text-muted-2">
        A gradient-boosted model trained on {model.nSamples.toLocaleString()}{" "}
        green-flag laps from {model.races.length} races, predicting lap-time pace
        from tyre age, fuel load and track temperature.
      </p>

      {/* Metrics */}
      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Metric label="Test MAE" value={`${model.metrics.mae.toFixed(2)}s`} />
        <Metric label="R²" value={model.metrics.r2.toFixed(2)} />
        <Metric label="Fuel effect" value={`${model.fuelEffect.toFixed(1)}s`} hint="full load" />
        <Metric label="Laps" value={model.nSamples.toLocaleString()} />
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        {/* Degradation curves */}
        <div>
          <h3 className="text-sm font-semibold">Estimated tyre-age effect</h3>
          <p className="mb-2 text-xs text-muted-2">
            Predicted pace vs tyre age (fuel &amp; temp held fixed). Age is a
            small, noisy effect next to fuel and temperature.
          </p>
          <div className="h-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={curveData} margin={{ top: 6, right: 12, bottom: 4, left: -14 }}>
                <CartesianGrid stroke={GRID} />
                <XAxis dataKey="age" type="number" domain={["dataMin", "dataMax"]} stroke={AXIS} tick={{ fontSize: 11 }}
                  label={{ value: "Tyre age (laps)", position: "insideBottom", offset: -2, fill: AXIS, fontSize: 10 }} />
                <YAxis stroke={AXIS} tick={{ fontSize: 11 }} width={44} tickFormatter={(v) => `${v > 0 ? "+" : ""}${v.toFixed(1)}`} />
                <Tooltip
                  contentStyle={{ background: "#101218", border: "1px solid #262a35", borderRadius: 8, fontSize: 12 }}
                  formatter={(v) => `${Number(v) > 0 ? "+" : ""}${Number(v).toFixed(2)}s`}
                  labelFormatter={(l) => `Age ${l}`}
                />
                {Object.keys(model.curves).map((comp) => (
                  <Line key={comp} type="monotone" dataKey={comp} name={comp}
                    stroke={COMPOUND_COLOR[comp] ?? "#888"} strokeWidth={2} dot={false}
                    isAnimationActive={false} connectNulls />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Feature importance */}
        <div>
          <h3 className="text-sm font-semibold">What drives lap time</h3>
          <p className="mb-2 text-xs text-muted-2">
            Gradient-boosting feature importance — the model&apos;s honest take.
          </p>
          <div className="space-y-2 pt-1">
            {importances.map(([f, v]) => (
              <div key={f} className="flex items-center gap-2 text-sm">
                <span className="w-24 shrink-0 text-muted">{FEATURE_LABEL[f] ?? f}</span>
                <div className="h-2.5 flex-1 overflow-hidden rounded bg-panel-2">
                  <div className="h-full rounded bg-purple" style={{ width: `${(v / maxImp) * 100}%` }} />
                </div>
                <span className="tnum w-10 text-right text-xs text-muted">{(v * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Drift */}
      <div className="mt-5">
        <h3 className="text-sm font-semibold">Data drift across races</h3>
        <p className="mb-2 text-xs text-muted-2">
          Track-temperature shift of each race vs the training distribution
          (z-score) — the Evidently-style check a model in production would run.
        </p>
        <div className="overflow-hidden rounded-lg border border-border-soft">
          <table className="w-full text-sm">
            <thead className="bg-panel-2 text-xs text-muted-2">
              <tr>
                <th className="px-3 py-1.5 text-left font-medium">Race</th>
                <th className="px-3 py-1.5 text-right font-medium">Laps</th>
                <th className="px-3 py-1.5 text-right font-medium">Track temp</th>
                <th className="px-3 py-1.5 text-right font-medium">Drift</th>
              </tr>
            </thead>
            <tbody>
              {model.drift.map((d) => (
                <tr key={d.race} className="border-t border-border-soft">
                  <td className="px-3 py-1.5">{d.race}</td>
                  <td className="tnum px-3 py-1.5 text-right text-muted">{d.n}</td>
                  <td className="tnum px-3 py-1.5 text-right text-muted">{d.trackTempMean}°</td>
                  <td className="px-3 py-1.5 text-right">
                    <span className={`tnum ${d.drifted ? "text-accent-2" : "text-muted"}`}>
                      {d.drift.toFixed(2)}
                      {d.drifted && " ⚠"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-border-soft bg-panel-2 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-muted-2">{label}</div>
      <div className="tnum text-lg font-bold text-text">
        {value}
        {hint && <span className="ml-1 text-[10px] font-normal text-muted-2">{hint}</span>}
      </div>
    </div>
  );
}
