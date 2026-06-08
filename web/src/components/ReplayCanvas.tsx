"use client";

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
} from "react";
import type { Meta, Frames } from "@/lib/types";
import { sampleDriver } from "@/lib/raceEngine";

export interface ReplayHandle {
  draw: (frame: number, focused: string | null) => void;
}

interface Props {
  meta: Meta;
  frames: Frames;
  onPickDriver: (code: string | null) => void;
}

const TRAIL_FRAMES = 16; // how far back the comet tail reaches
const TRACK_W = 9;

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  const v =
    h.length === 3
      ? h
          .split("")
          .map((c) => c + c)
          .join("")
      : h;
  return [
    parseInt(v.slice(0, 2), 16) || 200,
    parseInt(v.slice(2, 4), 16) || 200,
    parseInt(v.slice(4, 6), 16) || 200,
  ];
}

const ReplayCanvas = forwardRef<ReplayHandle, Props>(function ReplayCanvas(
  { meta, frames, onPickDriver },
  ref,
) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sizeRef = useRef({ w: 0, h: 0, dpr: 1 });
  const colorsRef = useRef<Record<string, [number, number, number]>>({});
  // Screen positions of cars from the last draw, for click hit-testing.
  const hitRef = useRef<{ code: string; sx: number; sy: number }[]>([]);
  // Last drawn state, so we can redraw on resize / mount without the rAF loop.
  const lastRef = useRef<{ frame: number; focused: string | null }>({
    frame: 0,
    focused: null,
  });
  const drawRef = useRef<(frame: number, focused: string | null) => void>(
    () => {},
  );

  useEffect(() => {
    const colors: Record<string, [number, number, number]> = {};
    for (const d of meta.drivers) colors[d.code] = hexToRgb(d.color);
    colorsRef.current = colors;
  }, [meta]);

  // Keep the backing store sized to the container at device resolution.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const parent = canvas.parentElement!;
    const ro = new ResizeObserver(() => {
      const r = parent.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const bw = Math.round(r.width * dpr);
      const bh = Math.round(r.height * dpr);
      // Only touch the backing store when it actually changes. The canvas is
      // position:absolute (out of flow), so we never set its CSS size here —
      // that previously fed back into the aspect-ratio parent and made the
      // view zoom unboundedly. CSS sizing is left to the stylesheet.
      if (canvas.width !== bw || canvas.height !== bh) {
        canvas.width = bw;
        canvas.height = bh;
      }
      sizeRef.current = { w: r.width, h: r.height, dpr };
      // Redraw immediately so the scene survives resizes and shows before
      // the first animation frame (and in environments that throttle rAF).
      drawRef.current(lastRef.current.frame, lastRef.current.focused);
    });
    ro.observe(parent);
    return () => ro.disconnect();
  }, []);

  const project = useCallback(() => {
    const { w, h } = sizeRef.current;
    const [minX, maxX, minY, maxY] = meta.bounds;
    const pad = 42;
    const rangeX = Math.max(1, maxX - minX);
    const rangeY = Math.max(1, maxY - minY);
    const scale = Math.min((w - 2 * pad) / rangeX, (h - 2 * pad) / rangeY);
    const offX = (w - rangeX * scale) / 2;
    const offY = (h - rangeY * scale) / 2;
    return {
      sx: (x: number) => offX + (x - minX) * scale,
      sy: (y: number) => h - (offY + (y - minY) * scale),
    };
  }, [meta.bounds]);

  const draw = useCallback(
    (frame: number, focused: string | null) => {
      const canvas = canvasRef.current;
      const { w, h, dpr } = sizeRef.current;
      if (!canvas || w === 0) return;
      lastRef.current = { frame, focused };
      const ctx = canvas.getContext("2d")!;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      const { sx, sy } = project();

      // --- Track (racing line of the fastest lap) ---
      if (meta.racingLine.length > 1) {
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
        ctx.beginPath();
        meta.racingLine.forEach(([x, y], i) => {
          const px = sx(x);
          const py = sy(y);
          if (i === 0) ctx.moveTo(px, py);
          else ctx.lineTo(px, py);
        });
        ctx.closePath();
        ctx.strokeStyle = "#000";
        ctx.lineWidth = TRACK_W + 6;
        ctx.stroke();
        ctx.strokeStyle = "#2b2f3a";
        ctx.lineWidth = TRACK_W;
        ctx.stroke();
        ctx.strokeStyle = "#3a3f4d";
        ctx.lineWidth = 1.5;
        ctx.setLineDash([2, 9]);
        ctx.stroke();
        ctx.setLineDash([]);
      }

      // --- Start / finish line ---
      if (meta.startFinish) {
        const [fx, fy] = meta.startFinish;
        const px = sx(fx);
        const py = sy(fy);
        ctx.fillStyle = "#e8eaf0";
        ctx.fillRect(px - 2, py - 9, 4, 18);
        ctx.fillStyle = "rgba(255,255,255,0.5)";
        ctx.font = "700 10px var(--font-geist-mono), monospace";
        ctx.fillText("S/F", px + 6, py - 6);
      }

      // --- Corner numbers ---
      ctx.fillStyle = "rgba(160,168,185,0.55)";
      ctx.font = "600 10px var(--font-geist-mono), monospace";
      for (const c of meta.corners) {
        ctx.fillText(String(c.n), sx(c.x) + 4, sy(c.y) + 3);
      }

      // --- Cars: trails then dots ---
      const hits: { code: string; sx: number; sy: number }[] = [];
      for (const d of meta.drivers) {
        const df = frames.drivers[d.code];
        if (!df) continue;
        const cur = sampleDriver(df, frame);
        if (!cur) continue;
        const [r, g, b] = colorsRef.current[d.code] ?? [200, 200, 200];
        const faded = focused != null && focused !== d.code;

        // Comet trail sampled directly from the path (seek-safe).
        ctx.lineCap = "round";
        for (let k = TRAIL_FRAMES; k > 0; k--) {
          const s0 = sampleDriver(df, frame - k);
          const s1 = sampleDriver(df, frame - k + 1);
          if (!s0 || !s1) continue;
          const a = (1 - k / TRAIL_FRAMES) * (faded ? 0.12 : 0.85);
          ctx.strokeStyle = `rgba(${r},${g},${b},${a})`;
          ctx.lineWidth = (faded ? 1.2 : 1.5) + (1 - k / TRAIL_FRAMES) * 3;
          ctx.beginPath();
          ctx.moveTo(sx(s0.x), sy(s0.y));
          ctx.lineTo(sx(s1.x), sy(s1.y));
          ctx.stroke();
        }

        const px = sx(cur.x);
        const py = sy(cur.y);
        hits.push({ code: d.code, sx: px, sy: py });
        const am = faded ? 0.28 : 1;

        // DRS open indicator.
        if (cur.drs >= 10 && !faded) {
          ctx.fillStyle = "rgba(46,224,106,0.9)";
          ctx.beginPath();
          ctx.moveTo(px, py - 13);
          ctx.lineTo(px + 4, py - 9);
          ctx.lineTo(px, py - 5);
          ctx.lineTo(px - 4, py - 9);
          ctx.fill();
        }

        ctx.beginPath();
        ctx.arc(px, py, faded ? 4.5 : 6.5, 0, Math.PI * 2);
        ctx.fillStyle = "#05060a";
        ctx.fill();
        ctx.beginPath();
        ctx.arc(px, py, faded ? 3.2 : 5, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${r},${g},${b},${am})`;
        ctx.fill();

        if (!faded) {
          ctx.beginPath();
          ctx.arc(px, py, 1.6, 0, Math.PI * 2);
          ctx.fillStyle = "#fff";
          ctx.fill();
          ctx.fillStyle = "rgba(232,234,240,0.92)";
          ctx.font = "700 10px var(--font-geist-sans), sans-serif";
          ctx.fillText(d.code, px + 9, py - 7);
        }
      }
      hitRef.current = hits;
    },
    [meta, frames, project],
  );

  drawRef.current = draw;
  useImperativeHandle(ref, () => ({ draw }), [draw]);

  // Initial paint once the canvas has been measured.
  useEffect(() => {
    const id = requestAnimationFrame(() =>
      draw(lastRef.current.frame, lastRef.current.focused),
    );
    return () => cancelAnimationFrame(id);
  }, [draw]);

  const handleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    let best: string | null = null;
    let bestD = 196; // 14px radius²
    for (const hit of hitRef.current) {
      const dx = mx - hit.sx;
      const dy = my - hit.sy;
      const d2 = dx * dx + dy * dy;
      if (d2 < bestD) {
        bestD = d2;
        best = hit.code;
      }
    }
    onPickDriver(best);
  };

  return (
    <canvas
      ref={canvasRef}
      onClick={handleClick}
      className="absolute inset-0 h-full w-full cursor-pointer"
    />
  );
});

export default ReplayCanvas;
