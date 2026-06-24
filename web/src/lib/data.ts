import type {
  Analytics,
  Engineer,
  Events,
  Frames,
  Laps,
  Manifest,
  Meta,
  RaceData,
  Traces,
} from "./types";

async function getJSON<T>(url: string, cache: RequestCache): Promise<T> {
  const res = await fetch(url, { cache });
  if (!res.ok) throw new Error(`Failed to load ${url} (${res.status})`);
  return res.json() as Promise<T>;
}

export async function getModel(): Promise<import("./types").PaceModel | null> {
  try {
    const res = await fetch("/data/model.json", { cache: "default" });
    return res.ok ? await res.json() : null;
  } catch {
    return null;
  }
}

export function getManifest(): Promise<Manifest> {
  // The manifest grows as races are exported, so always fetch it fresh; the
  // per-race files below are immutable per path and safe to hard-cache.
  return getJSON<Manifest>("/data/manifest.json", "no-store");
}

export async function getRaceData(
  year: string | number,
  round: string | number,
): Promise<RaceData> {
  const base = `/data/${year}/${round}`;
  // "default" lets the browser/CDN revalidate via ETag — instant on repeat
  // visits in production, but never serves a stale file after a re-export.
  const hard: RequestCache = "default";
  const [meta, frames, laps, traces, analytics, events, engineer] =
    await Promise.all([
      getJSON<Meta>(`${base}/meta.json`, hard),
      getJSON<Frames>(`${base}/frames.json`, hard),
      getJSON<Laps>(`${base}/laps.json`, hard),
      getJSON<Traces>(`${base}/traces.json`, hard),
      getJSON<Analytics>(`${base}/analytics.json`, hard),
      getJSON<Events>(`${base}/events.json`, hard),
      getJSON<Engineer>(`${base}/engineer.json`, hard),
    ]);
  return { meta, frames, laps, traces, analytics, events, engineer };
}
