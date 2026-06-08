import type { Events, FlagType, StatusBand, WeatherSample } from "./types";

export const FLAG_COLOR: Record<FlagType, string> = {
  GREEN: "#2ee06a",
  YELLOW: "#f4d03f",
  SC: "#ff8c1a",
  VSC: "#ffd12e",
  RED: "#e10600",
};

export const FLAG_LABEL: Record<FlagType, string> = {
  GREEN: "Green",
  YELLOW: "Yellow",
  SC: "Safety Car",
  VSC: "Virtual SC",
  RED: "Red Flag",
};

export const MOMENT_COLOR: Record<string, string> = {
  start: "#2ee06a",
  lead: "#e8eaf0",
  fl: "#b14bff",
  pit: "#4aa3ff",
  sc: "#ff8c1a",
  vsc: "#ffd12e",
  red: "#e10600",
};

/** Active flag at session time `t` (GREEN if no band covers it). */
export function flagAt(bands: StatusBand[], t: number): FlagType {
  for (const b of bands) {
    if (t >= b.start && t < b.end) return b.type;
  }
  return "GREEN";
}

/** Nearest weather sample to session time `t`. */
export function weatherAt(
  weather: WeatherSample[],
  t: number,
): WeatherSample | null {
  if (!weather.length) return null;
  let lo = 0;
  let hi = weather.length - 1;
  if (t <= weather[lo].t) return weather[lo];
  if (t >= weather[hi].t) return weather[hi];
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (weather[mid].t <= t) lo = mid;
    else hi = mid;
  }
  return t - weather[lo].t <= weather[hi].t - t ? weather[lo] : weather[hi];
}

/** Whether any weather sample reports rain (so we can flag a wet race). */
export function raceHasRain(events: Events): boolean {
  return events.weather.some((w) => w.rain);
}
