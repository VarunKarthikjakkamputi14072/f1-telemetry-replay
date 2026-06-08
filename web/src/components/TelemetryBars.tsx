"use client";

import type { Sample } from "@/lib/raceEngine";
import type { DriverMeta } from "@/lib/types";

interface Props {
  driver: DriverMeta;
  sample: Sample;
}

function Bar({
  label,
  value,
  max,
  color,
  unit,
}: {
  label: string;
  value: number;
  max: number;
  color: string;
  unit?: string;
}) {
  const pct = Math.max(0, Math.min(1, value / max));
  return (
    <div className="flex items-center gap-2">
      <span className="w-8 text-[10px] font-semibold text-muted-2">{label}</span>
      <div className="h-2 flex-1 overflow-hidden rounded bg-black/40">
        <div
          className="h-full rounded transition-[width] duration-75"
          style={{ width: `${pct * 100}%`, background: color }}
        />
      </div>
      <span className="tnum w-14 text-right text-[11px] text-text">
        {Math.round(value)}
        {unit}
      </span>
    </div>
  );
}

export default function TelemetryBars({ driver, sample }: Props) {
  return (
    <div className="panel px-3 py-2.5">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span
            className="h-4 w-1 rounded"
            style={{ background: driver.color }}
          />
          <span className="text-sm font-bold">{driver.code}</span>
          <span className="text-xs text-muted-2">{driver.name}</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="tnum text-xs text-muted">
            GEAR{" "}
            <span className="text-base font-bold text-text">
              {sample.gear || "N"}
            </span>
          </span>
          <span className="tnum text-xs text-muted">
            <span className="text-base font-bold text-text">
              {Math.round(sample.spd)}
            </span>{" "}
            km/h
          </span>
        </div>
      </div>
      <div className="space-y-1.5">
        <Bar label="THR" value={sample.thr} max={100} color="#2ee06a" unit="%" />
        <Bar label="BRK" value={sample.brk} max={100} color="#ff3b3b" unit="%" />
        <Bar
          label="SPD"
          value={sample.spd}
          max={360}
          color="#4aa3ff"
          unit=""
        />
      </div>
    </div>
  );
}
