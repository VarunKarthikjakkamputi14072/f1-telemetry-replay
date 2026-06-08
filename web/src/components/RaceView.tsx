"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import type { RaceData } from "@/lib/types";
import { sampleDriver } from "@/lib/raceEngine";
import { prepTower, evalTower } from "@/lib/timingTower";
import { fmtClock } from "@/lib/format";
import ReplayCanvas, { type ReplayHandle } from "./ReplayCanvas";
import Leaderboard from "./Leaderboard";
import TelemetryBars from "./TelemetryBars";
import StrategyTab from "./tabs/StrategyTab";
import PaceTab from "./tabs/PaceTab";
import CompareTab from "./tabs/CompareTab";

type Tab = "replay" | "strategy" | "pace" | "compare";
const SPEEDS = [0.5, 1, 2, 4, 8];
const TABS: { id: Tab; label: string }[] = [
  { id: "replay", label: "Replay" },
  { id: "strategy", label: "Strategy" },
  { id: "pace", label: "Pace" },
  { id: "compare", label: "Compare" },
];

export default function RaceView({ data }: { data: RaceData }) {
  const { meta, frames, laps, traces, analytics } = data;
  const [tab, setTab] = useState<Tab>("replay");
  const [playing, setPlaying] = useState(true);
  const [speed, setSpeed] = useState(2);
  const [uiFrame, setUiFrame] = useState(0);
  const [focused, setFocused] = useState<string | null>(null);
  const [gapMode, setGapMode] = useState<"leader" | "interval">("leader");

  const replayRef = useRef<ReplayHandle>(null);
  const frameRef = useRef(0);
  const playingRef = useRef(playing);
  const speedRef = useRef(speed);
  const focusedRef = useRef(focused);
  const tabRef = useRef(tab);
  // Mirror the latest UI state into refs the rAF loop / handlers read, without
  // touching refs during render.
  useEffect(() => {
    playingRef.current = playing;
    speedRef.current = speed;
    focusedRef.current = focused;
    tabRef.current = tab;
  }, [playing, speed, focused, tab]);

  // Per-driver official timing timelines (built once).
  const towerPrep = useMemo(() => prepTower(laps, analytics), [laps, analytics]);

  const fastestLap = useMemo(() => {
    let best: { code: string; t: number } | null = null;
    for (const [code, recs] of Object.entries(laps)) {
      for (const r of recs) {
        if (r.lapTime && r.lapTime > 0 && (!best || r.lapTime < best.t))
          best = { code, t: r.lapTime };
      }
    }
    return best?.code ?? null;
  }, [laps]);

  // Single animation loop: advance the clock, draw the canvas, throttle UI.
  useEffect(() => {
    let raf = 0;
    let last: number | null = null;
    let lastUi = 0;
    const loop = (ts: number) => {
      if (last == null) last = ts;
      const dt = (ts - last) / 1000;
      last = ts;
      if (playingRef.current) {
        frameRef.current += (dt * speedRef.current) / frames.step;
        if (frameRef.current >= frames.n - 1) frameRef.current = 0;
      }
      if (tabRef.current === "replay") {
        replayRef.current?.draw(frameRef.current, focusedRef.current);
      }
      if (ts - lastUi > 60) {
        lastUi = ts;
        setUiFrame(frameRef.current);
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [frames]);

  // Keyboard transport controls.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return;
      if (e.code === "Space") {
        e.preventDefault();
        setPlaying((p) => !p);
      } else if (e.code === "ArrowRight") {
        frameRef.current = Math.min(frames.n - 1, frameRef.current + 5 / frames.step);
      } else if (e.code === "ArrowLeft") {
        frameRef.current = Math.max(0, frameRef.current - 5 / frames.step);
      } else if (e.key === "r") {
        frameRef.current = 0;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [frames]);

  const tNow = frames.t0 + uiFrame * frames.step;
  const pitOf = (code: string) => {
    const d = frames.drivers[code];
    const s = d ? sampleDriver(d, uiFrame) : null;
    return s ? s.spd < 35 : false;
  };
  const standings = evalTower(towerPrep, tNow, pitOf);

  // Leader's current lap = laps they've completed + 1.
  const leaderCode = standings[0]?.code;
  const completed = leaderCode
    ? (towerPrep.byCode[leaderCode] ?? []).filter((p) => p.t <= tNow).length
    : 0;
  const curLap = Math.min(meta.totalLaps, completed + 1);
  const elapsed = uiFrame * frames.step;

  const focusedSample =
    focused && frames.drivers[focused]
      ? sampleDriver(frames.drivers[focused], uiFrame)
      : null;
  const focusedMeta = meta.drivers.find((d) => d.code === focused);

  const seek = (frame: number) => {
    frameRef.current = frame;
    setUiFrame(frame);
    // Redraw at once so scrubbing is responsive even while paused.
    replayRef.current?.draw(frame, focusedRef.current);
  };

  return (
    <main className="mx-auto w-full max-w-[1180px] px-4 py-6">
      {/* Header */}
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <Link
            href="/"
            className="text-xs text-muted-2 transition hover:text-text"
          >
            ← All races
          </Link>
          <h1 className="flex items-center gap-3 text-2xl font-black tracking-tight">
            <span className="inline-block h-5 w-1 rounded bg-accent" />
            {meta.race}
            <span className="tnum text-base font-medium text-muted-2">
              {meta.year}
            </span>
          </h1>
        </div>
        <div className="flex gap-1 rounded-lg border border-border p-1">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
                tab === t.id
                  ? "bg-accent text-white"
                  : "text-muted hover:text-text"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {tab === "replay" && (
        <div className="grid gap-4 lg:grid-cols-[1fr_330px]">
          <div className="flex flex-col gap-3">
            {/* Track */}
            <div className="panel relative aspect-[16/11] overflow-hidden">
              <div className="absolute left-3 top-3 z-10 flex gap-4 text-sm">
                <span className="tnum text-muted">
                  <span className="text-text">{fmtClock(elapsed)}</span>
                </span>
                <span className="tnum text-muted">
                  LAP{" "}
                  <span className="font-bold text-text">{curLap}</span>
                  <span className="text-muted-2"> / {meta.totalLaps}</span>
                </span>
              </div>
              <ReplayCanvas
                ref={replayRef}
                meta={meta}
                frames={frames}
                onPickDriver={(c) =>
                  setFocused((prev) => (prev === c ? null : c))
                }
              />
            </div>

            {/* Transport */}
            <div className="panel flex items-center gap-3 px-3 py-2">
              <button
                onClick={() => setPlaying((p) => !p)}
                className="flex h-9 w-9 items-center justify-center rounded-md bg-accent text-white transition hover:bg-accent-2"
                aria-label={playing ? "Pause" : "Play"}
              >
                {playing ? "❚❚" : "▶"}
              </button>
              <button
                onClick={() => seek(0)}
                className="text-xs text-muted transition hover:text-text"
              >
                ↺
              </button>
              <input
                type="range"
                min={0}
                max={frames.n - 1}
                value={Math.round(uiFrame)}
                onChange={(e) => seek(Number(e.target.value))}
                className="h-1 flex-1 cursor-pointer accent-accent"
              />
              <div className="flex gap-1">
                {SPEEDS.map((s) => (
                  <button
                    key={s}
                    onClick={() => setSpeed(s)}
                    className={`tnum rounded px-1.5 py-0.5 text-[11px] transition ${
                      speed === s
                        ? "bg-panel-2 text-text"
                        : "text-muted-2 hover:text-text"
                    }`}
                  >
                    {s}×
                  </button>
                ))}
              </div>
            </div>

            {focusedMeta && focusedSample ? (
              <TelemetryBars driver={focusedMeta} sample={focusedSample} />
            ) : (
              <div className="panel px-3 py-2.5 text-center text-xs text-muted-2">
                Click a car or a timing row to lock telemetry · Space to
                play/pause · ←/→ to seek
              </div>
            )}
          </div>

          <div className="h-[560px] lg:h-auto">
            <Leaderboard
              meta={meta}
              standings={standings}
              focused={focused}
              fastestLap={fastestLap}
              gapMode={gapMode}
              onPick={(c) => setFocused((prev) => (prev === c ? null : c))}
              onToggleMode={() =>
                setGapMode((m) => (m === "leader" ? "interval" : "leader"))
              }
            />
          </div>
        </div>
      )}

      {tab === "strategy" && (
        <StrategyTab meta={meta} analytics={analytics} />
      )}
      {tab === "pace" && <PaceTab meta={meta} analytics={analytics} />}
      {tab === "compare" && <CompareTab meta={meta} traces={traces} />}
    </main>
  );
}
