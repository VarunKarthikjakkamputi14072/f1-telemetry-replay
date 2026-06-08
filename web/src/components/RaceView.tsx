"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import type { RaceData } from "@/lib/types";
import { sampleDriver } from "@/lib/raceEngine";
import { prepTower, computeTower } from "@/lib/timingTower";
import { fmtClock } from "@/lib/format";
import { flagAt, weatherAt } from "@/lib/eventsUtil";
import ReplayCanvas, { type ReplayHandle } from "./ReplayCanvas";
import Leaderboard from "./Leaderboard";
import TelemetryBars from "./TelemetryBars";
import Timeline from "./Timeline";
import StatusBar from "./StatusBar";
import StrategyTab from "./tabs/StrategyTab";
import PaceTab from "./tabs/PaceTab";
import CompareTab from "./tabs/CompareTab";
import EngineerTab from "./tabs/EngineerTab";

type Tab = "replay" | "strategy" | "pace" | "compare" | "engineer";
const SPEEDS = [0.5, 1, 2, 4, 8];
const TABS: { id: Tab; label: string }[] = [
  { id: "replay", label: "Replay" },
  { id: "strategy", label: "Strategy" },
  { id: "pace", label: "Pace" },
  { id: "compare", label: "Compare" },
  { id: "engineer", label: "AI Engineer" },
];

const TAB_IDS = new Set<Tab>(["replay", "strategy", "pace", "compare", "engineer"]);

/** Read a shareable moment (tab / time / driver / camera) from the URL once. */
function readShareParams(codes: string[], step: number) {
  if (typeof window === "undefined") return null;
  const p = new URLSearchParams(window.location.search);
  const tab = p.get("tab");
  const t = p.get("t");
  const d = p.get("d");
  const frame = t != null && isFinite(Number(t)) ? Number(t) / step : null;
  return {
    tab: tab && TAB_IDS.has(tab as Tab) ? (tab as Tab) : null,
    frame,
    driver: d && codes.includes(d) ? d : null,
    onboard: p.get("cam") === "1",
    hasMoment: t != null,
  };
}

export default function RaceView({ data }: { data: RaceData }) {
  const { meta, frames, laps, traces, analytics, events, engineer } = data;
  const init = useMemo(
    () => readShareParams(meta.drivers.map((d) => d.code), frames.step),
    [meta.drivers, frames.step],
  );

  const [tab, setTab] = useState<Tab>(init?.tab ?? "replay");
  const [playing, setPlaying] = useState(!init?.hasMoment); // open paused at a shared moment
  const [speed, setSpeed] = useState(2);
  const [uiFrame, setUiFrame] = useState(init?.frame ?? 0);
  const [focused, setFocused] = useState<string | null>(init?.driver ?? null);
  const [gapMode, setGapMode] = useState<"leader" | "interval">("leader");
  const [onboard, setOnboard] = useState(init?.onboard ?? false);
  const [copied, setCopied] = useState(false);

  const replayRef = useRef<ReplayHandle>(null);
  const onboardRef = useRef(onboard);
  const frameRef = useRef(init?.frame ?? 0);
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
    onboardRef.current = onboard;
  }, [playing, speed, focused, tab, onboard]);

  // Per-driver official timing timelines (built once).
  const towerPrep = useMemo(() => prepTower(laps, analytics), [laps, analytics]);

  // When the fastest lap of the race changes hands, in order of session time.
  // Lets the FL crown appear only once that lap has actually been set, rather
  // than spoiling the eventual holder from the start.
  const flTimeline = useMemo(() => {
    const all: { t: number; code: string; lapTime: number }[] = [];
    for (const [code, recs] of Object.entries(laps)) {
      for (const r of recs) {
        if (r.t != null && r.lapTime && r.lapTime > 0) {
          all.push({ t: r.t, code, lapTime: r.lapTime });
        }
      }
    }
    all.sort((p, q) => p.t - q.t);
    const timeline: { t: number; code: string }[] = [];
    let bestTime = Infinity;
    for (const l of all) {
      if (l.lapTime < bestTime) {
        bestTime = l.lapTime;
        timeline.push({ t: l.t, code: l.code });
      }
    }
    return timeline;
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
        replayRef.current?.draw(
          frameRef.current,
          focusedRef.current,
          onboardRef.current,
        );
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
  const standings = computeTower(towerPrep, frames, uiFrame);

  // Leader's current lap = laps they've completed + 1.
  const leaderCode = standings[0]?.code;
  const completed = leaderCode
    ? (towerPrep.byCode[leaderCode] ?? []).filter((p) => p.t <= tNow).length
    : 0;
  const curLap = Math.min(meta.totalLaps, completed + 1);
  const elapsed = uiFrame * frames.step;

  // Fastest-lap holder as of the current replay time (last change at or before now).
  let fastestLap: string | null = null;
  for (const fl of flTimeline) {
    if (fl.t <= tNow) fastestLap = fl.code;
    else break;
  }

  const focusedSample =
    focused && frames.drivers[focused]
      ? sampleDriver(frames.drivers[focused], uiFrame)
      : null;
  const focusedMeta = meta.drivers.find((d) => d.code === focused);

  // Race control + weather at the current replay moment.
  const flag = flagAt(events.trackStatus, tNow);
  const weather = weatherAt(events.weather, tNow);

  // Live battle context for the focused driver (car ahead / behind right now).
  const focusIdx = standings.findIndex((s) => s.code === focused);
  const carAhead = focusIdx > 0 ? standings[focusIdx - 1] : null;
  const carBehind =
    focusIdx >= 0 && focusIdx < standings.length - 1
      ? standings[focusIdx + 1]
      : null;
  const focusStanding = focusIdx >= 0 ? standings[focusIdx] : null;

  const seek = (frame: number) => {
    frameRef.current = frame;
    setUiFrame(frame);
    // Redraw at once so scrubbing is responsive even while paused.
    replayRef.current?.draw(frame, focusedRef.current, onboardRef.current);
  };

  // Copy a deep link to the current tab / moment / driver / camera.
  const share = async () => {
    const p = new URLSearchParams();
    if (tab !== "replay") p.set("tab", tab);
    p.set("t", String(Math.round(uiFrame * frames.step)));
    if (focused) p.set("d", focused);
    if (onboard) p.set("cam", "1");
    const url = `${window.location.origin}${window.location.pathname}?${p}`;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      window.prompt("Copy this link:", url);
    }
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
        <div className="flex items-center gap-2">
          <button
            onClick={share}
            title="Copy a link to this exact moment"
            className={`rounded-lg border px-3 py-2 text-sm font-medium transition ${
              copied
                ? "border-good text-good"
                : "border-border text-muted hover:text-text"
            }`}
          >
            {copied ? "Copied ✓" : "Share"}
          </button>
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
              <div className="absolute right-3 top-3 z-10 flex items-center gap-2">
                <StatusBar flag={flag} weather={weather} />
                <button
                  onClick={() => setOnboard((o) => !o)}
                  disabled={!focused}
                  title={
                    focused
                      ? "Follow the focused car"
                      : "Focus a car to enable onboard"
                  }
                  className={`rounded-md border px-2 py-1 text-xs transition disabled:opacity-40 ${
                    onboard && focused
                      ? "border-accent bg-accent/20 text-text"
                      : "border-border text-muted hover:text-text"
                  }`}
                >
                  Onboard
                </button>
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
              <div className="flex-1">
                <Timeline
                  t0={frames.t0}
                  step={frames.step}
                  n={frames.n}
                  events={events}
                  uiFrame={uiFrame}
                  onSeek={seek}
                />
              </div>
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
              <div className="flex flex-col gap-2">
                <TelemetryBars driver={focusedMeta} sample={focusedSample} />
                {focusStanding && (
                  <div className="panel flex items-center justify-between px-3 py-2 text-xs">
                    <span className="text-muted-2">
                      Ahead:{" "}
                      {carAhead ? (
                        <span className="tnum text-text">
                          {carAhead.code}{" "}
                          {focusStanding.intLaps > 0
                            ? `+${focusStanding.intLaps}L`
                            : `+${focusStanding.interval.toFixed(2)}s`}
                        </span>
                      ) : (
                        <span className="text-good">Race leader</span>
                      )}
                    </span>
                    <span className="tnum font-bold text-text">
                      P{focusStanding.pos}
                    </span>
                    <span className="text-muted-2">
                      Behind:{" "}
                      {carBehind ? (
                        <span className="tnum text-text">
                          {carBehind.code}{" "}
                          {carBehind.intLaps > 0
                            ? `+${carBehind.intLaps}L`
                            : `+${carBehind.interval.toFixed(2)}s`}
                        </span>
                      ) : (
                        <span className="text-muted-2">—</span>
                      )}
                    </span>
                  </div>
                )}
              </div>
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
      {tab === "engineer" && (
        <EngineerTab engineer={engineer} totalLaps={meta.totalLaps} />
      )}
    </main>
  );
}
