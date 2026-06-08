"use client";

import Link from "next/link";
import type { TowerEntry } from "@/lib/timingTower";
import type { Meta } from "@/lib/types";

interface Props {
  meta: Meta;
  standings: TowerEntry[];
  focused: string | null;
  fastestLap: string | null;
  gapMode: "leader" | "interval";
  onPick: (code: string | null) => void;
  onToggleMode: () => void;
}

export default function Leaderboard({
  meta,
  standings,
  focused,
  fastestLap,
  gapMode,
  onPick,
  onToggleMode,
}: Props) {
  const byCode = Object.fromEntries(meta.drivers.map((d) => [d.code, d]));

  return (
    <div className="panel flex h-full flex-col overflow-hidden">
      <div className="flex items-center justify-between border-b border-border-soft px-3 py-2">
        <span className="text-xs font-semibold uppercase tracking-widest text-muted-2">
          Timing
        </span>
        <button
          onClick={onToggleMode}
          className="rounded-md border border-border px-2 py-0.5 text-[11px] text-muted transition hover:border-accent hover:text-text"
        >
          {gapMode === "leader" ? "Gap to leader" : "Interval"}
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {standings.map((s, i) => {
          const d = byCode[s.code];
          if (!d) return null;
          const isFocus = focused === s.code;
          const laps = gapMode === "leader" ? s.gapLaps : s.intLaps;
          const secs = gapMode === "leader" ? s.gap : s.interval;
          const label =
            i === 0 ? "Leader" : laps > 0 ? `+${laps}L` : `+${secs.toFixed(3)}`;
          return (
            <div
              key={s.code}
              role="button"
              tabIndex={0}
              onClick={() => onPick(isFocus ? null : s.code)}
              className={`group flex w-full cursor-pointer items-center gap-2 px-2 py-[7px] text-left transition ${
                isFocus
                  ? "bg-panel-2"
                  : i % 2
                    ? "bg-white/[0.012]"
                    : ""
              } hover:bg-panel-2`}
            >
              <span className="tnum w-5 text-right text-sm font-bold text-muted">
                {i + 1}
              </span>
              <span
                className="h-5 w-[3px] rounded"
                style={{ background: d.color }}
              />
              <span className="w-9 text-sm font-bold tracking-tight">
                {d.code}
              </span>
              <span className="flex-1 truncate text-xs text-muted-2">
                {d.team}
              </span>
              <Link
                href={`/race/${meta.year}/${meta.round}/driver/${s.code}`}
                onClick={(e) => e.stopPropagation()}
                title={`${d.code} race report`}
                className="text-muted-2 opacity-0 transition hover:text-text group-hover:opacity-100"
              >
                ↗
              </Link>
              {fastestLap === s.code && (
                <span className="rounded bg-purple/20 px-1 text-[9px] font-bold text-purple">
                  FL
                </span>
              )}
              {s.pit && (
                <span className="rounded bg-accent/20 px-1 text-[9px] font-bold text-accent-2">
                  PIT
                </span>
              )}
              <span
                className={`tnum w-16 text-right text-xs ${
                  i === 0 ? "text-good" : "text-muted"
                }`}
              >
                {label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
