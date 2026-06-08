import type { Analytics, Frames, Laps } from "./types";
import { sampleDriver } from "./raceEngine";

// Timing tower. Order AND gap come from the same FastF1 official timing, so they
// can never disagree: the running order is the per-lap Position, and the gap is
// the distance-aligned gap-to-leader (interpolated over time so it ticks
// smoothly). Lapped cars are shown as whole laps down ("+1L"), exactly as a
// broadcast timing screen does, rather than a meaningless seconds figure.

export interface TowerEntry {
  code: string;
  pos: number;
  gap: number; // seconds behind leader (valid when gapLaps === 0)
  gapLaps: number; // whole laps down to the leader
  interval: number; // seconds behind car ahead (valid when intLaps === 0)
  intLaps: number; // whole laps down to the car ahead
  pit: boolean;
}

interface Point {
  t: number; // session time the lap was completed
  gap: number; // official gap to leader at that lap
  pos: number;
}

export interface TowerPrep {
  byCode: Record<string, Point[]>;
}

/** Build each driver's official (time, gap, position) timeline once. */
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
 * Position, interpolated gap, and *fractional* race progress for a driver at
 * `tNow`. Progress = laps crossed + fraction through the current lap; comparing
 * two drivers' progress and flooring the difference gives a stable laps-down
 * count that doesn't flicker to "+1L" just because the leader crossed the line
 * a few seconds before a same-lap car behind.
 */
function evalAt(pts: Point[], tNow: number, raceStart: number) {
  // Before the first line crossing there is no earlier data point, so grow the
  // gap from 0 at the start to the lap-1 gap rather than holding it constant
  // (which froze the whole field for the entire opening lap).
  if (tNow <= pts[0].t) {
    const span = pts[0].t - raceStart;
    const f = span > 0 ? Math.max(0, Math.min(1, (tNow - raceStart) / span)) : 0;
    return { pos: pts[0].pos, gap: pts[0].gap * f, prog: f };
  }
  let i = 0;
  while (i < pts.length - 1 && pts[i + 1].t <= tNow) i++;
  const a = pts[i];
  const b = pts[i + 1];
  let gap = a.gap;
  let frac = 0;
  if (b) {
    frac = (tNow - a.t) / (b.t - a.t || 1);
    gap = a.gap + (b.gap - a.gap) * frac;
  }
  return { pos: a.pos, gap, prog: i + 1 + frac };
}

/** Full tower at an absolute frame index. */
export function computeTower(
  prep: TowerPrep,
  frames: Frames,
  absFrame: number,
): TowerEntry[] {
  const tNow = frames.t0 + absFrame * frames.step;

  const rows: {
    code: string;
    pos: number;
    gap: number;
    prog: number;
    pit: boolean;
  }[] = [];
  for (const [code, pts] of Object.entries(prep.byCode)) {
    const df = frames.drivers[code];
    if (!df) continue;
    const s = sampleDriver(df, absFrame);
    if (!s) continue; // retired / not yet on track
    const e = evalAt(pts, tNow, frames.t0);
    rows.push({ code, pos: e.pos, gap: e.gap, prog: e.prog, pit: s.spd < 35 });
  }
  rows.sort((a, b) => a.pos - b.pos);

  const leader = rows[0];
  return rows.map((r, idx) => {
    if (idx === 0) {
      return { code: r.code, pos: 1, gap: 0, gapLaps: 0, interval: 0, intLaps: 0, pit: r.pit };
    }
    const ahead = rows[idx - 1];
    return {
      code: r.code,
      pos: idx + 1,
      gap: Math.max(0, r.gap),
      gapLaps: Math.max(0, Math.floor(leader.prog - r.prog)),
      interval: Math.max(0, r.gap - ahead.gap),
      intLaps: Math.max(0, Math.floor(ahead.prog - r.prog)),
      pit: r.pit,
    };
  });
}
