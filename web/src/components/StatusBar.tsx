"use client";

import type { FlagType, WeatherSample } from "@/lib/types";
import { FLAG_COLOR, FLAG_LABEL } from "@/lib/eventsUtil";

export default function StatusBar({
  flag,
  weather,
}: {
  flag: FlagType;
  weather: WeatherSample | null;
}) {
  return (
    <div className="flex items-center gap-2 text-xs">
      {flag !== "GREEN" && (
        <span
          className="flex items-center gap-1.5 rounded px-2 py-1 font-semibold"
          style={{ background: `${FLAG_COLOR[flag]}22`, color: FLAG_COLOR[flag] }}
        >
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ background: FLAG_COLOR[flag] }}
          />
          {FLAG_LABEL[flag]}
        </span>
      )}
      {weather && (
        <span className="tnum flex items-center gap-2 rounded bg-panel-2 px-2 py-1 text-muted">
          <span title="Track temperature">
            <span className="text-text">{weather.track.toFixed(0)}°</span> track
          </span>
          <span title="Air temperature">
            <span className="text-text">{weather.air.toFixed(0)}°</span> air
          </span>
          <span
            className={weather.rain ? "text-[#4aa3ff]" : "text-muted-2"}
            title="Conditions"
          >
            {weather.rain ? "● Wet" : "Dry"}
          </span>
        </span>
      )}
    </div>
  );
}
