// Mirrors the JSON contract emitted by pipeline/export.py.

export interface DriverMeta {
  code: string;
  num: string;
  name: string;
  team: string;
  color: string;
}

export interface Corner {
  n: number;
  letter: string;
  x: number;
  y: number;
}

export interface Meta {
  year: number;
  round: number;
  race: string;
  circuit: string;
  country: string;
  totalLaps: number;
  bounds: [number, number, number, number]; // minX, maxX, minY, maxY
  racingLine: [number, number][];
  startFinish: [number, number] | null;
  corners: Corner[];
  drivers: DriverMeta[];
}

export interface DriverFrames {
  f0: number; // absolute index of this driver's first frame on the global grid
  x: number[];
  y: number[];
  dist: number[];
  spd: number[];
  thr: number[];
  brk: number[];
  gear: number[];
  drs: number[];
}

export interface Frames {
  step: number; // seconds between frames
  t0: number; // session time of frame 0
  n: number; // number of frames on the global grid
  drivers: Record<string, DriverFrames>;
}

export interface LapRecord {
  lap: number | null;
  t: number | null;
  lapTime: number | null;
  s1: number | null;
  s2: number | null;
  s3: number | null;
  compound: string | null;
  stint: number | null;
  pitIn: boolean;
  pitOut: boolean;
  pos: number | null;
}

export type Laps = Record<string, LapRecord[]>;

export interface Trace {
  lapTime: number | null;
  dist: number[];
  spd: number[];
  thr: number[];
  brk: number[];
  gear: number[];
}

export type Traces = Record<string, Trace>;

export interface Stint {
  compound: string;
  lapStart: number;
  lapEnd: number;
}

export interface Undercut {
  driver: string;
  rival: string;
  lap: number;
  kind: string;
  gained: number;
}

export interface Analytics {
  gapToLeader: Record<string, { lap: number; gap: number }[]>;
  positionByLap: Record<string, Record<string, number>>;
  stints: Record<string, Stint[]>;
  sectorBest: Record<string, Record<string, number>>;
  sectorOwners: Record<string, string>;
  undercuts: Undercut[];
}

export interface RaceSummary {
  id: string;
  year: number;
  round: number;
  race: string;
  circuit: string;
  country: string;
  totalLaps: number;
  drivers: number;
}

export interface Manifest {
  races: RaceSummary[];
}

export interface RaceData {
  meta: Meta;
  frames: Frames;
  laps: Laps;
  traces: Traces;
  analytics: Analytics;
}
