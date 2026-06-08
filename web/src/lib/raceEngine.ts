import type { Frames, DriverFrames } from "./types";

export interface Sample {
  x: number;
  y: number;
  dist: number;
  spd: number;
  thr: number;
  brk: number;
  gear: number;
  drs: number;
}

export interface Standing {
  code: string;
  dist: number;
  gap: number; // time behind leader (s)
  interval: number; // time behind car ahead (s)
  pit: boolean;
  sample: Sample;
}

/** Interpolated state of a driver at a (possibly fractional) absolute frame index. */
export function sampleDriver(
  d: DriverFrames,
  absFrame: number,
): Sample | null {
  const local = absFrame - d.f0;
  const len = d.x.length;
  if (local < 0 || local > len - 1) return null;
  const i = Math.floor(local);
  const f = local - i;
  if (i >= len - 1) {
    const j = len - 1;
    return {
      x: d.x[j], y: d.y[j], dist: d.dist[j], spd: d.spd[j],
      thr: d.thr[j], brk: d.brk[j], gear: d.gear[j], drs: d.drs[j],
    };
  }
  const lerp = (a: number[], k: number) => a[k] + (a[k + 1] - a[k]) * f;
  return {
    x: lerp(d.x, i),
    y: lerp(d.y, i),
    dist: lerp(d.dist, i),
    spd: lerp(d.spd, i),
    thr: lerp(d.thr, i),
    brk: lerp(d.brk, i),
    gear: Math.round(d.gear[i]),
    drs: d.drs[i],
  };
}

/**
 * Session time at which a driver passed cumulative track-distance `dist`.
 *
 * Their `dist` array is monotonic, so we binary-search it and convert the
 * fractional local index back to an absolute time. This is what makes the time
 * gap correct: gap = now - timeAtDistance(leader, follower.dist).
 */
function timeAtDistance(
  d: DriverFrames,
  dist: number,
  step: number,
  t0: number,
): number | null {
  const arr = d.dist;
  const n = arr.length;
  if (n === 0) return null;
  if (dist <= arr[0]) return t0 + d.f0 * step;
  if (dist >= arr[n - 1]) return t0 + (d.f0 + n - 1) * step;
  let lo = 0;
  let hi = n - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (arr[mid] <= dist) lo = mid;
    else hi = mid;
  }
  const span = arr[hi] - arr[lo] || 1;
  const frac = (dist - arr[lo]) / span;
  return t0 + (d.f0 + lo + frac) * step;
}

/** Full timing tower at a given absolute frame: order, gap to leader, interval. */
export function computeStandings(
  frames: Frames,
  codes: string[],
  absFrame: number,
): Standing[] {
  const now = frames.t0 + absFrame * frames.step;
  const rows: { code: string; sample: Sample }[] = [];
  for (const code of codes) {
    const d = frames.drivers[code];
    if (!d) continue;
    const s = sampleDriver(d, absFrame);
    if (s) rows.push({ code, sample: s });
  }
  rows.sort((a, b) => b.sample.dist - a.sample.dist);

  const out: Standing[] = [];
  const leader = rows[0];
  for (let p = 0; p < rows.length; p++) {
    const { code, sample } = rows[p];
    let gap = 0;
    let interval = 0;
    if (p > 0 && leader) {
      const tl = timeAtDistance(
        frames.drivers[leader.code],
        sample.dist,
        frames.step,
        frames.t0,
      );
      gap = tl == null ? Infinity : Math.max(0, now - tl);
      const ahead = rows[p - 1];
      const ta = timeAtDistance(
        frames.drivers[ahead.code],
        sample.dist,
        frames.step,
        frames.t0,
      );
      interval = ta == null ? Infinity : Math.max(0, now - ta);
    }
    out.push({
      code,
      dist: sample.dist,
      gap,
      interval,
      pit: sample.spd < 35,
      sample,
    });
  }
  return out;
}

/** Approximate current lap of the leader from total distance and lap count. */
export function leaderLap(
  standings: Standing[],
  totalDist: number,
  totalLaps: number,
): number {
  if (!standings.length || totalLaps <= 0 || totalDist <= 0) return 1;
  const lapLen = totalDist / totalLaps;
  return Math.min(totalLaps, Math.floor(standings[0].dist / lapLen) + 1);
}
