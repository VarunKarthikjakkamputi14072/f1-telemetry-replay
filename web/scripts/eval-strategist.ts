/**
 * RAGAS-style eval for "Ask the Strategist".
 *
 *   npm run eval:strategist
 *
 * For each seed race we pose questions whose gold answers are derived from the
 * data itself, then score the retrieval + extractive layer on:
 *   - context recall@k : did the relevant fact get retrieved?
 *   - answer accuracy   : does the answer contain the gold token?
 *   - faithfulness      : are the answer's content words grounded in the facts?
 * The extractive path is deterministic, so the harness runs with no API key.
 */
import { loadFactsInput } from "../src/lib/serverRaceData";
import {
  buildFacts,
  extractiveAnswer,
  retrieve,
  type Fact,
  type Retrieved,
} from "../src/lib/strategist";

interface Case {
  q: string;
  goldToken: string; // must appear in a correct answer
  relevant: (r: Retrieved) => boolean; // a retrieved fact counts as the gold context
  enabled?: boolean;
}

const RACES = [
  { year: 2019, round: 11 },
  { year: 2021, round: 22 },
  { year: 2022, round: 13 },
  { year: 2023, round: 20 },
  { year: 2024, round: 21 },
];

const content = (s: string) =>
  s.toLowerCase().replace(/[^a-z0-9 ]/g, " ").split(/\s+/).filter((t) => t.length > 3);

function buildCases(facts: Fact[]): Case[] {
  const winner = facts.find((f) => f.id === "winner")?.cite?.driver ?? "";
  const fl = facts.find((f) => f.id === "fastest-lap")?.cite?.driver ?? "";
  const hasSC = facts.some((f) => f.id.startsWith("rc-"));
  const wet = facts.find((f) => f.id === "weather")?.text.includes("rain");
  const winnerStrategy = facts.find((f) => f.id === `strategy-${winner}`);
  const stops = winnerStrategy?.text.match(/(\d+)-stop/)?.[1] ?? "";
  const cases: Case[] = [
    {
      q: "Who won the race?",
      goldToken: winner.toLowerCase(),
      relevant: (r) => r.fact.id === "winner" || r.fact.id === `finish-${winner}`,
    },
    {
      q: "What was the fastest lap of the race?",
      goldToken: fl.toLowerCase(),
      relevant: (r) => r.fact.id === "fastest-lap",
    },
    {
      q: "Was there a safety car or virtual safety car?",
      goldToken: "safety",
      relevant: (r) => r.fact.id.startsWith("rc-"),
      enabled: hasSC,
    },
    {
      q: `How many pit stops did ${winner} make?`,
      goldToken: `${stops}-stop`,
      relevant: (r) => r.fact.id === `strategy-${winner}`,
      enabled: !!stops,
    },
    {
      q: "What were the weather conditions?",
      goldToken: wet ? "rain" : "dry",
      relevant: (r) => r.fact.id === "weather",
    },
  ];
  return cases.filter((c) => c.enabled !== false);
}

function faithfulness(answer: string, retrieved: Retrieved[]): number {
  const ctx = new Set(retrieved.flatMap((r) => content(r.fact.text)));
  const toks = content(answer);
  if (!toks.length) return 0;
  return toks.filter((t) => ctx.has(t)).length / toks.length;
}

async function main() {
  const agg = { recall: 0, acc: 0, faith: 0, n: 0 };
  for (const { year, round } of RACES) {
    let facts: Fact[];
    try {
      facts = buildFacts(await loadFactsInput(year, round));
    } catch {
      console.log(`\n${year} r${round}: (not exported, skipped)`);
      continue;
    }
    const cases = buildCases(facts);
    let recall = 0;
    let acc = 0;
    let faith = 0;
    for (const c of cases) {
      const retrieved = retrieve(facts, c.q, 6);
      const { answer } = extractiveAnswer(retrieved);
      const hit = retrieved.some(c.relevant) ? 1 : 0;
      const correct = c.goldToken && answer.toLowerCase().includes(c.goldToken) ? 1 : 0;
      const f = faithfulness(answer, retrieved);
      recall += hit;
      acc += correct;
      faith += f;
      agg.recall += hit;
      agg.acc += correct;
      agg.faith += f;
      agg.n += 1;
    }
    const n = cases.length;
    console.log(
      `\n${year} r${round}  (${n} Qs)  recall@6 ${(100 * recall / n).toFixed(0)}%` +
        `  accuracy ${(100 * acc / n).toFixed(0)}%  faithfulness ${(faith / n).toFixed(2)}`,
    );
  }
  if (agg.n) {
    console.log(
      `\nOVERALL  recall@6 ${(100 * agg.recall / agg.n).toFixed(0)}%` +
        `  accuracy ${(100 * agg.acc / agg.n).toFixed(0)}%` +
        `  faithfulness ${(agg.faith / agg.n).toFixed(2)}  (n=${agg.n})`,
    );
  }
}

main();
