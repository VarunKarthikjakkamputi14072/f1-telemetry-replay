import {
  buildFacts,
  extractiveAnswer,
  retrieve,
  type Citation,
  type FactsInput,
  type Retrieved,
} from "@/lib/strategist";

export const runtime = "nodejs";

// Load just the files the strategist needs from the deployment's own static
// assets — robust on Vercel (no fs tracing) and in local dev alike.
async function loadFacts(origin: string, year: number, round: number): Promise<FactsInput> {
  const base = `${origin}/data/${year}/${round}`;
  const get = async (name: string) => {
    const r = await fetch(`${base}/${name}`);
    if (!r.ok) throw new Error(`missing ${name}`);
    return r.json();
  };
  const [meta, laps, analytics, events, engineer] = await Promise.all([
    get("meta.json"), get("laps.json"), get("analytics.json"),
    get("events.json"), get("engineer.json"),
  ]);
  return { meta, laps, analytics, events, engineer };
}

// Grounded answer from an LLM, constrained to the retrieved facts. Returns null
// on any failure so the caller can fall back to the extractive answer.
async function llmAnswer(
  question: string,
  retrieved: Retrieved[],
  key: string,
): Promise<string | null> {
  const facts = retrieved.map((r) => `- ${r.fact.text}`).join("\n");
  const body = {
    model: process.env.GROQ_MODEL ?? "llama-3.3-70b-versatile",
    temperature: 0.3,
    max_tokens: 260,
    messages: [
      {
        role: "system",
        content:
          "You are a Formula 1 race strategist. Answer the user's question using ONLY " +
          "the supplied facts. Cite lap numbers and 3-letter driver codes. Keep it to " +
          "2-4 sentences. If the facts don't cover it, say you don't have that data.",
      },
      { role: "user", content: `Question: ${question}\n\nFacts:\n${facts}` },
    ],
  };
  try {
    const res = await fetch("https://api.groq.com/openai/v1/chat/completions", {
      method: "POST",
      headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) return null;
    const data = await res.json();
    return data.choices?.[0]?.message?.content?.trim() ?? null;
  } catch {
    return null;
  }
}

export async function POST(request: Request) {
  let payload: { year?: unknown; round?: unknown; question?: unknown };
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: "bad request" }, { status: 400 });
  }
  const year = Number(payload.year);
  const round = Number(payload.round);
  const question = String(payload.question ?? "").slice(0, 300);
  if (!Number.isInteger(year) || !Number.isInteger(round) || !question.trim()) {
    return Response.json({ error: "year, round and question required" }, { status: 400 });
  }

  let facts;
  try {
    const origin = new URL(request.url).origin;
    facts = buildFacts(await loadFacts(origin, year, round));
  } catch {
    return Response.json({ error: "race not found" }, { status: 404 });
  }

  const retrieved = retrieve(facts, question, 6);
  const key = process.env.GROQ_API_KEY;

  let answer: string;
  let citations: Citation[];
  let source: "llama" | "extractive";
  const llm = key ? await llmAnswer(question, retrieved, key) : null;
  if (llm) {
    answer = llm;
    citations = retrieved
      .slice(0, 4)
      .map((r) => r.fact.cite)
      .filter((c): c is Citation => !!c);
    source = "llama";
  } else {
    ({ answer, citations } = extractiveAnswer(retrieved));
    source = "extractive";
  }

  return Response.json({ answer, citations, source, retrieved: retrieved.length });
}
