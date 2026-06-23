import type { RaceData } from "./types";
import { fmtLapTime } from "./format";

// "Ask the Strategist" retrieval layer. We turn each race's structured data into
// natural-language fact-cards, then answer questions with BM25-lite hybrid
// retrieval over them — no vector DB, runs anywhere. The LLM (or the extractive
// fallback) is only allowed to use the retrieved cards, and every card carries a
// citation back to a lap / driver / event.

export interface Citation {
  kind: "lap" | "driver" | "event";
  label: string;
  lap?: number;
  driver?: string;
}

export interface Fact {
  id: string;
  text: string;
  tags: string[]; // lowercased keywords + driver codes for retrieval boosting
  cite?: Citation;
}

const COMPOUND_FULL: Record<string, string> = {
  SOFT: "soft", MEDIUM: "medium", HARD: "hard", INTER: "intermediate", WET: "wet",
};

export type FactsInput = Pick<
  RaceData,
  "meta" | "laps" | "analytics" | "events" | "engineer"
>;

/** Build the fact corpus for one race from data the app already has. */
export function buildFacts(data: FactsInput): Fact[] {
  const { meta, laps, analytics, events, engineer } = data;
  const facts: Fact[] = [];
  const nameOf = Object.fromEntries(meta.drivers.map((d) => [d.code, d.name]));
  const teamOf = Object.fromEntries(meta.drivers.map((d) => [d.code, d.team]));
  const add = (id: string, text: string, tags: string[], cite?: Citation) =>
    facts.push({ id, text, tags: tags.map((t) => t.toLowerCase()), cite });

  // Final classification.
  const finalByCode: Record<string, number> = {};
  for (const [code, m] of Object.entries(analytics.positionByLap)) {
    const lks = Object.keys(m).map(Number);
    if (lks.length) finalByCode[code] = m[String(Math.max(...lks))];
  }
  const order = Object.entries(finalByCode).sort((a, b) => a[1] - b[1]);
  for (const [code, pos] of order) {
    add(
      `finish-${code}`,
      `${nameOf[code] ?? code} (${code}, ${teamOf[code]}) finished P${pos} at the ${meta.race}.`,
      [code, nameOf[code] ?? "", teamOf[code], "finish", "result", "position", "classified"],
      { kind: "driver", driver: code, label: `${code} P${pos}` },
    );
  }
  if (order.length) {
    const podium = order.slice(0, 3).map(([c, p]) => `P${p} ${c}`).join(", ");
    add("podium", `The podium was ${podium}.`, ["podium", "winner", "won", "top three", ...order.slice(0, 3).map((o) => o[0])]);
    add("winner", `${nameOf[order[0][0]] ?? order[0][0]} (${order[0][0]}) won the ${meta.race}.`,
      ["winner", "won", "victory", "win", order[0][0]],
      { kind: "driver", driver: order[0][0], label: `${order[0][0]} won` });
  }

  // Strategy: stints + pit laps.
  for (const [code, stints] of Object.entries(analytics.stints)) {
    if (!stints.length) continue;
    const desc = stints
      .map((s) => `${COMPOUND_FULL[s.compound] ?? s.compound} (laps ${s.lapStart}-${s.lapEnd})`)
      .join(", then ");
    const nStops = stints.length - 1;
    add(`strategy-${code}`,
      `${code} ran a ${nStops}-stop strategy: ${desc}.`,
      [code, "strategy", "stops", "stint", "tyre", "tire", "plan", "pit"],
      { kind: "driver", driver: code, label: `${code} strategy` });
    for (let i = 1; i < stints.length; i++) {
      add(`pit-${code}-${i}`,
        `${code} pitted on lap ${stints[i].lapStart} and switched to the ${COMPOUND_FULL[stints[i].compound] ?? stints[i].compound} tyre.`,
        [code, "pit", "stop", "box", "tyre", "tire", "change", `lap${stints[i].lapStart}`],
        { kind: "lap", lap: stints[i].lapStart, driver: code, label: `${code} pit L${stints[i].lapStart}` });
    }
  }

  // Fastest lap.
  let fl: { code: string; t: number } | null = null;
  for (const [code, recs] of Object.entries(laps)) {
    for (const r of recs) {
      if (r.lapTime && r.lapTime > 0 && (!fl || r.lapTime < fl.t)) fl = { code, t: r.lapTime };
    }
  }
  if (fl) {
    add("fastest-lap",
      `The fastest lap of the race was set by ${fl.code} (${nameOf[fl.code] ?? fl.code}), a ${fmtLapTime(fl.t)}.`,
      [fl.code, "fastest", "lap", "quickest", "pace"],
      { kind: "driver", driver: fl.code, label: `FL ${fl.code}` });
  }

  // Gap snapshots every ~10 laps.
  const gapAt = (lap: number) => {
    const rows = Object.entries(analytics.gapToLeader)
      .map(([code, gs]) => {
        const g = gs.filter((x) => x.lap <= lap).slice(-1)[0];
        return g ? { code, gap: g.gap } : null;
      })
      .filter((x): x is { code: string; gap: number } => !!x)
      .sort((a, b) => a.gap - b.gap)
      .slice(0, 5);
    return rows;
  };
  for (let lap = 10; lap < meta.totalLaps; lap += 10) {
    const rows = gapAt(lap);
    if (rows.length < 2) continue;
    const desc = rows
      .map((r, i) => (i === 0 ? `${r.code} led` : `${r.code} +${r.gap.toFixed(1)}s`))
      .join(", ");
    add(`gap-${lap}`, `On lap ${lap}: ${desc}.`,
      ["gap", "interval", "lead", "behind", `lap${lap}`, ...rows.map((r) => r.code)],
      { kind: "lap", lap, label: `Lap ${lap} gaps` });
  }

  // Race control moments.
  for (const m of events.moments) {
    if (m.type === "sc" || m.type === "vsc" || m.type === "red") {
      const lapApprox = Math.round((m.t - events.moments[0].t) / 1); // not exact; label only
      add(`rc-${m.t}`, `${m.label} during the race.`,
        ["safety car", "vsc", "virtual", "red flag", "incident", "neutralised", m.type],
        { kind: "event", label: m.label, lap: lapApprox > 0 ? undefined : undefined });
    }
  }
  if (events.weather.length) {
    const wet = events.weather.some((w) => w.rain);
    const tk = events.weather[Math.floor(events.weather.length / 2)];
    add("weather",
      `The race was ${wet ? "affected by rain (wet running)" : "dry"}; track temperature around ${tk.track.toFixed(0)}°C.`,
      ["weather", "rain", "wet", "dry", "conditions", "temperature"]);
  }

  // Mini-sector dominance.
  if (meta.miniSectors?.length) {
    const counts = new Map<string, number>();
    for (const s of meta.miniSectors) if (s.owner) counts.set(s.owner, (counts.get(s.owner) ?? 0) + 1);
    const top = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3);
    if (top.length) {
      add("dominance",
        `Mini-sector dominance (fastest through each of ${meta.miniSectors.length} sectors): ${top.map(([c, n]) => `${c} ${n}`).join(", ")}.`,
        ["sector", "dominance", "fastest", "quickest", ...top.map((t) => t[0])]);
    }
  }

  // AI engineer verdicts.
  for (const e of engineer.drivers) {
    add(`engineer-${e.code}`, `Strategy verdict for ${e.code}: ${e.verdict}`,
      [e.code, "strategy", "engineer", "verdict", "should", "could", "undercut", "overcut", "mistake"],
      { kind: "driver", driver: e.code, label: `${e.code} verdict` });
  }

  return facts;
}

// ---- Retrieval (BM25-lite) ----

const STOP = new Set(["the", "a", "an", "of", "in", "on", "to", "and", "did", "was", "is", "what", "who", "how", "why", "for", "at", "by", "with", "vs", "their", "his", "her"]);

function tokenize(s: string): string[] {
  return s.toLowerCase().replace(/[^a-z0-9 ]/g, " ").split(/\s+/).filter((t) => t && !STOP.has(t));
}

export interface Retrieved {
  fact: Fact;
  score: number;
}

/** Hybrid keyword retrieval: IDF-weighted term overlap + tag/driver boosting. */
export function retrieve(facts: Fact[], query: string, k = 6): Retrieved[] {
  const qTokens = tokenize(query);
  if (!qTokens.length) return [];
  // IDF over the corpus.
  const df = new Map<string, number>();
  const factTokens = facts.map((f) => {
    const toks = new Set(tokenize(f.text).concat(f.tags));
    for (const t of toks) df.set(t, (df.get(t) ?? 0) + 1);
    return toks;
  });
  const N = facts.length;
  const idf = (t: string) => Math.log(1 + N / (1 + (df.get(t) ?? 0)));

  const scored = facts.map((f, i) => {
    let score = 0;
    for (const qt of qTokens) {
      if (factTokens[i].has(qt)) score += idf(qt);
      // tag boost (driver codes / strong keywords matter more)
      if (f.tags.includes(qt)) score += 0.6 * idf(qt);
    }
    return { fact: f, score };
  });
  return scored
    .filter((s) => s.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, k);
}

/** Deterministic answer from the top facts (used when no LLM key is configured). */
export function extractiveAnswer(retrieved: Retrieved[]): {
  answer: string;
  citations: Citation[];
} {
  if (!retrieved.length) {
    return { answer: "I don't have data on that for this race.", citations: [] };
  }
  const top = retrieved.slice(0, 3);
  const answer = top.map((r) => r.fact.text).join(" ");
  const citations = top.map((r) => r.fact.cite).filter((c): c is Citation => !!c);
  return { answer, citations };
}
