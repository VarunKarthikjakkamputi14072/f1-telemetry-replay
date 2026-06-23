import { promises as fs } from "fs";
import path from "path";
import type { Analytics, Engineer, Events, Laps, Meta } from "./types";
import type { FactsInput } from "./strategist";

// Server-only loader (used by the API route and the eval script). Reads just the
// files the strategist needs — not the multi-MB frames — straight from disk.

export async function loadFactsInput(
  year: number,
  round: number,
): Promise<FactsInput> {
  const base = path.join(
    process.cwd(),
    "public",
    "data",
    String(year),
    String(round),
  );
  const read = async <T>(name: string): Promise<T> =>
    JSON.parse(await fs.readFile(path.join(base, name), "utf8")) as T;
  const [meta, laps, analytics, events, engineer] = await Promise.all([
    read<Meta>("meta.json"),
    read<Laps>("laps.json"),
    read<Analytics>("analytics.json"),
    read<Events>("events.json"),
    read<Engineer>("engineer.json"),
  ]);
  return { meta, laps, analytics, events, engineer };
}
