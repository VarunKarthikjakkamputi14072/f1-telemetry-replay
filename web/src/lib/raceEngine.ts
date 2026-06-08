import type { DriverFrames } from "./types";

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
