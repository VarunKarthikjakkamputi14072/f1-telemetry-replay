import type { Analytics, Laps } from "./types";

// Official timing tower, driven by FastF1's per-lap Position and the
// distance-aligned gap-to-leader — not by noisy cumulative track distance,
// which jumbles the order at a standing start when every car is stacked.

export interface TowerEntry {
  code: string;
  pos: number;
  gap: number; // seconds behind leader
  interval: number; // seconds behind car ahead
  pit: boolean;
}

interface Point {
  t: number; // session time the lap was completed
  gap: number;
  pos: number;
}

export interface TowerPrep {
  byCode: Record<string, Point[]>;
}

/** Build per-driver (time, gap, position) timelines once; cheap to evaluate later. */
export function prepTower(laps: Laps, analytics: Analytics): TowerPrep {
  const byCode: Record<string, Point[]> = {};
  for (const [code, recs] of Object.entries(laps)) {
    const gapByLap = new Map<number, number>();
    for (const g of analytics.gapToLeader[code] ?? []) gapByLap.set(g.lap, g.gap);

    const pts: Point[] = [];
    let lastGap = 0;
    let lastPos = 99;
    for (const r of recs) {
      if (r.lap == null || r.t == null) continue;
      if (r.pos != null) lastPos = r.pos;
      if (gapByLap.has(r.lap)) lastGap = gapByLap.get(r.lap)!;
      pts.push({ t: r.t, gap: lastGap, pos: lastPos });
    }
    pts.sort((a, b) => a.t - b.t);
    if (pts.length) byCode[code] = pts;
  }
  return { byCode };
}

/**
 * Evaluate the tower at session time `tNow`.
 *
 * Position is taken from the last completed lap (stepwise, like a real timing
 * screen); the gap is linearly interpolated between lap crossings so it ticks
 * smoothly. `pitOf` reports whether a car is currently stopped (from telemetry).
 */
export function evalTower(
  prep: TowerPrep,
  tNow: number,
  pitOf: (code: string) => boolean,
): TowerEntry[] {
  const rows: { code: string; pos: number; gap: number }[] = [];
  for (const [code, pts] of Object.entries(prep.byCode)) {
    // Before the first crossing, fall back to the first known order (the grid).
    if (tNow <= pts[0].t) {
      rows.push({ code, pos: pts[0].pos, gap: pts[0].gap });
      continue;
    }
    // Find the bracketing lap crossings around tNow.
    let i = 0;
    while (i < pts.length - 1 && pts[i + 1].t <= tNow) i++;
    const a = pts[i];
    const b = pts[i + 1];
    let gap = a.gap;
    if (b) {
      const f = (tNow - a.t) / (b.t - a.t || 1);
      gap = a.gap + (b.gap - a.gap) * f;
    }
    rows.push({ code, pos: a.pos, gap: Math.max(0, gap) });
  }

  rows.sort((p, q) => p.pos - q.pos || p.gap - q.gap);
  return rows.map((r, idx) => ({
    code: r.code,
    pos: idx + 1,
    gap: idx === 0 ? 0 : r.gap,
    interval: idx === 0 ? 0 : Math.max(0, r.gap - rows[idx - 1].gap),
    pit: pitOf(r.code),
  }));
}
