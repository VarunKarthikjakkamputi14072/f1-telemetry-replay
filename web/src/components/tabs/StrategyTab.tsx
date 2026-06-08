"use client";

import { useMemo } from "react";
import type { Analytics, Meta } from "@/lib/types";
import { COMPOUND_COLOR, COMPOUND_LABEL } from "@/lib/format";

interface Props {
  meta: Meta;
  analytics: Analytics;
}

export default function StrategyTab({ meta, analytics }: Props) {
  const total = meta.totalLaps;
  const teamByCode = Object.fromEntries(meta.drivers.map((d) => [d.code, d]));

  // Order drivers by their final classified position.
  const order = useMemo(() => {
    const finalPos = (code: string) => {
      const m = analytics.positionByLap[code] ?? {};
      const laps = Object.keys(m).map(Number);
      if (!laps.length) return 99;
      return m[String(Math.max(...laps))] ?? 99;
    };
    return Object.keys(analytics.stints)
      .filter((c) => teamByCode[c])
      .sort((a, b) => finalPos(a) - finalPos(b));
  }, [analytics, teamByCode]);

  return (
    <div className="panel p-5">
      <div className="mb-1 flex items-baseline justify-between">
        <h2 className="text-lg font-bold">Tyre Strategy</h2>
        <div className="flex gap-3 text-xs text-muted">
          {Object.entries(COMPOUND_COLOR).map(([k, c]) => (
            <span key={k} className="flex items-center gap-1.5">
              <span
                className="h-2.5 w-2.5 rounded-full"
                style={{ background: c }}
              />
              {k}
            </span>
          ))}
        </div>
      </div>
      <p className="mb-5 text-sm text-muted-2">
        Each bar is a driver&apos;s race, segmented by tyre stint across{" "}
        {total} laps. Pit stops are the breaks between segments.
      </p>

      <div className="space-y-1.5">
        {order.map((code) => {
          const d = teamByCode[code];
          const stints = analytics.stints[code] ?? [];
          return (
            <div key={code} className="flex items-center gap-3">
              <div className="flex w-16 items-center gap-2">
                <span
                  className="h-4 w-1 rounded"
                  style={{ background: d.color }}
                />
                <span className="text-sm font-bold">{code}</span>
              </div>
              <div className="flex h-6 flex-1 overflow-hidden rounded">
                {stints.map((s, i) => {
                  const laps = s.lapEnd - s.lapStart + 1;
                  const w = (laps / total) * 100;
                  const col = COMPOUND_COLOR[s.compound] ?? "#888";
                  const dark = s.compound === "HARD";
                  return (
                    <div
                      key={i}
                      title={`${s.compound}: laps ${s.lapStart}–${s.lapEnd} (${laps})`}
                      className="flex items-center justify-center border-r border-black/40 text-[10px] font-bold"
                      style={{
                        width: `${w}%`,
                        background: col,
                        color: dark ? "#000" : "#0008",
                      }}
                    >
                      {w > 4 ? COMPOUND_LABEL[s.compound] : ""}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      {analytics.undercuts.length > 0 && (
        <div className="mt-6">
          <h3 className="mb-2 text-sm font-semibold uppercase tracking-widest text-muted-2">
            Pit-stop swings
          </h3>
          <div className="flex flex-wrap gap-2">
            {analytics.undercuts.map((u, i) => (
              <span
                key={i}
                className="rounded-md border border-border bg-panel-2 px-2.5 py-1 text-xs"
              >
                <span className="font-bold">{u.driver}</span>{" "}
                <span className="text-good">{u.kind}</span> on{" "}
                <span className="text-muted">{u.rival}</span>
                <span className="text-muted-2"> · lap {u.lap}</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
