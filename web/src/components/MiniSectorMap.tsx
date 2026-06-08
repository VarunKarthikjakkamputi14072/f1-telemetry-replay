"use client";

import { useMemo } from "react";
import type { Meta } from "@/lib/types";

/**
 * Track map coloured by mini-sector dominance: each ~1/20th of the lap is tinted
 * with the team colour of whoever was quickest through it on their best lap.
 */
export default function MiniSectorMap({ meta }: { meta: Meta }) {
  const sectors = useMemo(() => meta.miniSectors ?? [], [meta]);
  const line = meta.racingLine;

  const { bands, vb, sw, dominance } = useMemo(() => {
    const [minX, maxX, minY, maxY] = meta.bounds;
    const w = Math.max(1, maxX - minX);
    const h = Math.max(1, maxY - minY);
    const sw = Math.max(w, h) / 60;
    const px = (p: [number, number]) => [p[0] - minX, maxY - p[1]] as const;

    const n = sectors.length || 1;
    const L = line.length;
    const bands = sectors.map((s, i) => {
      const a = Math.floor((i * L) / n);
      const b = Math.min(L - 1, Math.floor(((i + 1) * L) / n));
      const pts = line.slice(a, b + 1).map(px);
      return { points: pts.map((p) => p.join(",")).join(" "), color: s.color };
    });

    const counts = new Map<string, { n: number; color: string }>();
    for (const s of sectors) {
      if (!s.owner) continue;
      const c = counts.get(s.owner) ?? { n: 0, color: s.color };
      c.n += 1;
      counts.set(s.owner, c);
    }
    const dominance = [...counts.entries()]
      .map(([code, v]) => ({ code, ...v }))
      .sort((a, b) => b.n - a.n);

    return { bands, vb: `0 0 ${w} ${h}`, sw, dominance };
  }, [meta.bounds, line, sectors]);

  if (!sectors.length || line.length < 2) return null;

  return (
    <div className="panel p-5">
      <h2 className="text-lg font-bold">Mini-sector dominance</h2>
      <p className="mb-3 text-sm text-muted-2">
        The lap split into {sectors.length} mini-sectors, each shaded with the
        team colour of the driver quickest through it on their best lap.
      </p>
      <div className="grid items-center gap-4 sm:grid-cols-[1fr_180px]">
        <div className="h-[320px]">
          <svg viewBox={vb} className="h-full w-full" preserveAspectRatio="xMidYMid meet">
            <polyline
              points={line.map((p) => [p[0] - meta.bounds[0], meta.bounds[3] - p[1]].join(",")).join(" ")}
              fill="none"
              stroke="#05060a"
              strokeWidth={sw + sw * 0.5}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
            {bands.map((b, i) => (
              <polyline
                key={i}
                points={b.points}
                fill="none"
                stroke={b.color}
                strokeWidth={sw}
                strokeLinejoin="round"
                strokeLinecap="round"
              />
            ))}
          </svg>
        </div>
        <div className="space-y-1.5">
          {dominance.map((d) => (
            <div key={d.code} className="flex items-center gap-2 text-sm">
              <span className="h-3 w-3 rounded-sm" style={{ background: d.color }} />
              <span className="w-9 font-bold">{d.code}</span>
              <div className="h-1.5 flex-1 overflow-hidden rounded bg-panel-2">
                <div
                  className="h-full rounded"
                  style={{
                    width: `${(d.n / sectors.length) * 100}%`,
                    background: d.color,
                  }}
                />
              </div>
              <span className="tnum w-4 text-right text-muted">{d.n}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
