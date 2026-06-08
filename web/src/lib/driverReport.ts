import type { Events, LapRecord } from "./types";

export interface LapRange {
  lapStart: number;
  lapEnd: number;
}

/** Map safety-car / VSC time bands to the lap numbers this driver ran under them. */
export function scLapRanges(events: Events, laps: LapRecord[]): LapRange[] {
  const bands = events.trackStatus.filter(
    (b) => b.type === "SC" || b.type === "VSC",
  );
  if (!bands.length) return [];
  const timed = laps
    .filter((l) => l.lap != null && l.t != null)
    .sort((a, b) => a.lap! - b.lap!);
  const scLaps = new Set<number>();
  let prevT = timed.length ? timed[0].t! - 120 : 0;
  for (const l of timed) {
    if (bands.some((b) => b.start < l.t! && b.end > prevT)) scLaps.add(l.lap!);
    prevT = l.t!;
  }
  // Collapse consecutive lap numbers into ranges.
  const sorted = [...scLaps].sort((a, b) => a - b);
  const ranges: LapRange[] = [];
  for (const lap of sorted) {
    const last = ranges[ranges.length - 1];
    if (last && lap === last.lapEnd + 1) last.lapEnd = lap;
    else ranges.push({ lapStart: lap, lapEnd: lap });
  }
  return ranges;
}

/** Racing laps with a valid time, excluding in/out (pit) laps. */
export function racingLaps(laps: LapRecord[]): LapRecord[] {
  return laps.filter(
    (l) => l.lap != null && l.lapTime != null && l.lapTime > 0 && !l.pitIn && !l.pitOut,
  );
}

export function bestLapTime(laps: LapRecord[]): number | null {
  let best: number | null = null;
  for (const l of laps) {
    if (l.lapTime && l.lapTime > 0 && (best == null || l.lapTime < best))
      best = l.lapTime;
  }
  return best;
}

export function pitCount(laps: LapRecord[]): number {
  return laps.filter((l) => l.pitIn).length;
}
