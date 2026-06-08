import type {
  Analytics,
  Events,
  Frames,
  Laps,
  Manifest,
  Meta,
  RaceData,
  Traces,
} from "./types";

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url, { cache: "force-cache" });
  if (!res.ok) throw new Error(`Failed to load ${url} (${res.status})`);
  return res.json() as Promise<T>;
}

export function getManifest(): Promise<Manifest> {
  return getJSON<Manifest>("/data/manifest.json");
}

export async function getRaceData(
  year: string | number,
  round: string | number,
): Promise<RaceData> {
  const base = `/data/${year}/${round}`;
  const [meta, frames, laps, traces, analytics, events] = await Promise.all([
    getJSON<Meta>(`${base}/meta.json`),
    getJSON<Frames>(`${base}/frames.json`),
    getJSON<Laps>(`${base}/laps.json`),
    getJSON<Traces>(`${base}/traces.json`),
    getJSON<Analytics>(`${base}/analytics.json`),
    getJSON<Events>(`${base}/events.json`),
  ]);
  return { meta, frames, laps, traces, analytics, events };
}
