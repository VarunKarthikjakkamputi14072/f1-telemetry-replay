"use client";

import { useEffect, useState } from "react";
import type {
  Engineer,
  EngineerDriver,
  PaceModel,
  PitStop,
  Stint,
} from "@/lib/types";
import { COMPOUND_COLOR, COMPOUND_LABEL } from "@/lib/format";
import { getModel } from "@/lib/data";
import ModelPanel from "../ModelPanel";

function aiStints(
  startCompound: string,
  stops: PitStop[],
  totalLaps: number,
): Stint[] {
  const out: Stint[] = [];
  let compound = startCompound;
  let start = 1;
  for (const s of stops) {
    out.push({ compound, lapStart: start, lapEnd: s.lap - 1 });
    compound = s.compound;
    start = s.lap;
  }
  out.push({ compound, lapStart: start, lapEnd: totalLaps });
  return out.filter((s) => s.lapEnd >= s.lapStart);
}

function StintRow({
  label,
  stints,
  total,
}: {
  label: string;
  stints: Stint[];
  total: number;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-14 shrink-0 text-[10px] uppercase tracking-wider text-muted-2">
        {label}
      </span>
      <div className="flex h-5 flex-1 overflow-hidden rounded">
        {stints.map((s, i) => {
          const w = ((s.lapEnd - s.lapStart + 1) / total) * 100;
          const col = COMPOUND_COLOR[s.compound] ?? "#888";
          return (
            <div
              key={i}
              title={`${s.compound}: laps ${s.lapStart}–${s.lapEnd}`}
              className="flex items-center justify-center border-r border-black/40 text-[10px] font-bold"
              style={{
                width: `${w}%`,
                background: col,
                color: s.compound === "HARD" ? "#000" : "#0008",
              }}
            >
              {w > 5 ? COMPOUND_LABEL[s.compound] : ""}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function agreementTone(pct: number) {
  if (pct >= 80) return "text-good";
  if (pct >= 50) return "text-[#f4d03f]";
  return "text-accent-2";
}

function DriverCard({ d, total }: { d: EngineerDriver; total: number }) {
  const ai = aiStints(d.startCompound, d.aiStops, total);
  return (
    <div className="panel p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="h-5 w-1 rounded" style={{ background: d.color }} />
          <span className="text-sm font-bold">{d.code}</span>
          <span className="text-xs text-muted-2">P{d.finishPos} finish</span>
        </div>
        <span className={`tnum text-xs font-semibold ${agreementTone(d.agreement.pct)}`}>
          {d.agreement.pct}% match
          <span className="ml-1 font-normal text-muted-2">
            ({d.agreement.stopsMatched}/{d.agreement.actualStops} stops)
          </span>
        </span>
      </div>

      <div className="space-y-1.5">
        <StintRow label="Reality" stints={d.actualStints} total={total} />
        <StintRow label="Engineer" stints={ai} total={total} />
      </div>

      {d.decisions.length > 0 && (
        <ul className="mt-3 space-y-1">
          {d.decisions.map((dec, i) => (
            <li key={i} className="flex gap-2 text-xs text-muted">
              <span className="tnum shrink-0 text-muted-2">L{dec.lap}</span>
              <span
                className="shrink-0 font-bold"
                style={{ color: COMPOUND_COLOR[dec.compound] }}
              >
                BOX {COMPOUND_LABEL[dec.compound]}
              </span>
              <span>{dec.reason}</span>
            </li>
          ))}
        </ul>
      )}

      <p className="mt-3 border-t border-border-soft pt-2 text-xs leading-relaxed text-muted">
        {d.verdict}
      </p>
    </div>
  );
}

export default function EngineerTab({
  engineer,
  totalLaps,
}: {
  engineer: Engineer;
  totalLaps: number;
}) {
  const [showAll, setShowAll] = useState(false);
  const [model, setModel] = useState<PaceModel | null>(null);
  const drivers = showAll ? engineer.drivers : engineer.drivers.slice(0, 4);
  const isLlm = engineer.source !== "heuristic";

  useEffect(() => {
    getModel().then(setModel);
  }, []);

  return (
    <div className="space-y-4">
      {model && <ModelPanel model={model} />}
      <div className="panel p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-bold">AI Race Engineer</h2>
          <span
            className={`rounded-md px-2 py-1 text-xs font-semibold ${
              isLlm
                ? "bg-purple/20 text-purple"
                : "bg-panel-2 text-muted"
            }`}
          >
            {isLlm ? `LLM · ${engineer.model}` : "Deterministic strategist"}
          </span>
        </div>
        <p className="mt-2 max-w-3xl text-sm text-muted-2">
          An independent strategist works the race lap by lap — tyre life, pit
          loss, undercuts and the box-under-safety-car call — without seeing the
          future. Its calls are then graded against what each driver actually
          did. {engineer.note}
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {drivers.map((d) => (
          <DriverCard key={d.code} d={d} total={totalLaps} />
        ))}
      </div>

      {engineer.drivers.length > 4 && (
        <button
          onClick={() => setShowAll((s) => !s)}
          className="mx-auto block rounded-md border border-border px-4 py-2 text-sm text-muted transition hover:border-accent hover:text-text"
        >
          {showAll ? "Show fewer" : `Show all ${engineer.drivers.length} drivers`}
        </button>
      )}
    </div>
  );
}
