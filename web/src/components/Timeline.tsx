"use client";

import { useRef, useState } from "react";
import type { Events } from "@/lib/types";
import { FLAG_COLOR, MOMENT_COLOR } from "@/lib/eventsUtil";

interface Props {
  t0: number;
  step: number;
  n: number;
  events: Events;
  uiFrame: number;
  onSeek: (frame: number) => void;
}

export default function Timeline({ t0, step, n, events, uiFrame, onSeek }: Props) {
  const barRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);
  const [hover, setHover] = useState<{ x: number; label: string } | null>(null);

  const span = (n - 1) * step || 1;
  const frac = (t: number) => Math.max(0, Math.min(1, (t - t0) / span));
  const progress = Math.max(0, Math.min(1, uiFrame / (n - 1)));

  const seekToClientX = (clientX: number) => {
    const el = barRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const f = Math.max(0, Math.min(1, (clientX - r.left) / r.width));
    onSeek(f * (n - 1));
  };

  return (
    <div className="select-none">
      <div
        ref={barRef}
        className="relative h-7 cursor-pointer"
        onPointerDown={(e) => {
          dragging.current = true;
          try {
            (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
          } catch {
            /* ignore unsupported / synthetic pointers */
          }
          seekToClientX(e.clientX);
        }}
        onPointerMove={(e) => dragging.current && seekToClientX(e.clientX)}
        onPointerUp={() => (dragging.current = false)}
        onPointerLeave={() => setHover(null)}
      >
        {/* Track */}
        <div className="absolute inset-x-0 top-1/2 h-1.5 -translate-y-1/2 rounded bg-panel-2" />

        {/* Safety car / flag bands */}
        {events.trackStatus.map((b, i) => {
          const left = frac(b.start) * 100;
          const width = Math.max(0.4, (frac(b.end) - frac(b.start)) * 100);
          return (
            <div
              key={i}
              className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-sm opacity-80"
              style={{
                left: `${left}%`,
                width: `${width}%`,
                background: FLAG_COLOR[b.type],
              }}
              title={b.type}
            />
          );
        })}

        {/* Progress */}
        <div
          className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-l bg-accent/70"
          style={{ width: `${progress * 100}%` }}
        />

        {/* Moment markers */}
        {events.moments.map((m, i) => (
          <button
            key={i}
            className="absolute top-1/2 h-3 w-[3px] -translate-x-1/2 -translate-y-1/2 rounded-full transition-transform hover:scale-y-150"
            style={{ left: `${frac(m.t) * 100}%`, background: MOMENT_COLOR[m.type] ?? "#888" }}
            onPointerDown={(e) => {
              e.stopPropagation();
              onSeek((m.t - t0) / step);
            }}
            onMouseEnter={() => setHover({ x: frac(m.t) * 100, label: m.label })}
            onMouseLeave={() => setHover(null)}
            aria-label={m.label}
          />
        ))}

        {/* Playhead */}
        <div
          className="pointer-events-none absolute top-1/2 h-4 w-0.5 -translate-x-1/2 -translate-y-1/2 bg-white"
          style={{ left: `${progress * 100}%` }}
        />

        {hover && (
          <div
            className="pointer-events-none absolute -top-7 z-10 -translate-x-1/2 whitespace-nowrap rounded border border-border bg-bg-elev px-2 py-0.5 text-[11px] text-text"
            style={{ left: `${hover.x}%` }}
          >
            {hover.label}
          </div>
        )}
      </div>
    </div>
  );
}
