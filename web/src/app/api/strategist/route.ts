import {
  buildFacts,
  extractiveAnswer,
  retrieve,
  type Citation,
  type Fact,
  type FactsInput,
} from "@/lib/strategist";
import { searchWeb, type WebResult } from "@/lib/webSearch";

// Questions that reach beyond this one race — answered with live web results.
const GENERAL_RE =
  /\b(now|current|currently|today|latest|recent|this season|next season|20(2[3-9]|[3-9]\d)|transfer|moved|signed|contract|retire|retired|career|all[- ]?time|greatest|best of|legacy|champion|championship|titles?|record|standings|who is|where is|history|compare|versus|\bvs\b)\b/i;

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

// Grounded answer from an LLM, constrained to the retrieved facts. Tries the
// Groq -> Gemini -> Cohere waterfall (VaultMind-style); returns null when none is
// configured/working so the caller falls back to the extractive answer.
async function llmAnswer(
  question: string,
  contextFacts: Fact[],
  history: { role: string; text: string }[] = [],
  web: WebResult[] = [],
): Promise<{ text: string; provider: string } | null> {
  // Give the model the whole race's facts (capped) so it can reason about
  // anything — penalties, incidents, who pitted most — not just a few cards.
  const facts = contextFacts.slice(0, 140).map((f) => `- ${f.text}`).join("\n");
  const webBlock = web.length
    ? "\n\nLive web results (current/general info — prefer these for anything beyond " +
      "this race; cite the source):\n" +
      web.map((w, i) => `[${i + 1}] ${w.title}: ${w.snippet} (${w.url})`).join("\n")
    : "";
  const system =
    "You are a sharp, friendly Formula 1 expert having an ongoing conversation " +
    "with a fan. The supplied facts are the GROUND TRUTH for THIS race: rely on " +
    "them for anything about this race, cite lap numbers and 3-letter driver " +
    "codes, and never invent race-specific details that aren't in them. " +
    "For broader questions — a driver's career, championships, records, history, " +
    "the greatest of an era, comparisons — draw on your own knowledge of Formula 1 " +
    "and answer naturally; do NOT refuse just because it's outside this race, and " +
    "feel free to connect it back to what happened here. Build on the earlier " +
    "messages so the chat flows. " +
    "CRITICAL — be accurate, not merely agreeable. For anything about THIS race, use " +
    "only the supplied race facts and never invent laps, penalties or results. For " +
    "current or recent real-world facts (a driver's CURRENT team, the latest season, " +
    "transfers, standings, records): if 'Live web results' are included below, treat " +
    "them as up to date and answer confidently, citing them like [1]; if NO web " +
    "results are given, say plainly you don't have live data rather than guessing or " +
    "relying on possibly-stale training. Don't just agree with the user's claim " +
    "unless the race facts or web results actually support it. Keep answers to a few " +
    "sentences unless more detail is clearly wanted.";
  const convo = history.length
    ? "Conversation so far:\n" +
      history.map((m) => `${m.role === "user" ? "Q" : "A"}: ${m.text}`).join("\n") +
      "\n\n"
    : "";
  const user = `${convo}Question: ${question}\n\nFacts about this race:\n${facts}${webBlock}`;

  // 1) NVIDIA NIM (OpenAI-compatible) — primary.
  const nim = process.env.NVIDIA_API_KEY;
  if (nim) {
    try {
      const model = process.env.NIM_MODEL ?? "meta/llama-3.3-70b-instruct";
      const res = await fetch("https://integrate.api.nvidia.com/v1/chat/completions", {
        method: "POST",
        headers: { Authorization: `Bearer ${nim}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          model, temperature: 0.4, max_tokens: 450,
          messages: [
            { role: "system", content: system },
            { role: "user", content: user },
          ],
        }),
      });
      if (res.ok) {
        const d = await res.json();
        const text = d.choices?.[0]?.message?.content?.trim();
        if (text) return { text, provider: `nim:${model.split("/").pop()}` };
      }
    } catch {
      /* fall through */
    }
  }

  const groq = process.env.GROQ_API_KEY;
  if (groq) {
    try {
      const model = process.env.GROQ_MODEL ?? "llama-3.3-70b-versatile";
      const res = await fetch("https://api.groq.com/openai/v1/chat/completions", {
        method: "POST",
        headers: { Authorization: `Bearer ${groq}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          model, temperature: 0.3, max_tokens: 260,
          messages: [
            { role: "system", content: system },
            { role: "user", content: user },
          ],
        }),
      });
      if (res.ok) {
        const d = await res.json();
        const text = d.choices?.[0]?.message?.content?.trim();
        if (text) return { text, provider: `groq:${model}` };
      }
    } catch {
      /* fall through */
    }
  }

  const gemini = process.env.GEMINI_API_KEY;
  if (gemini) {
    try {
      const model = process.env.GEMINI_MODEL ?? "gemini-2.5-flash";
      const res = await fetch(
        `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${gemini}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            contents: [{ parts: [{ text: `${system}\n\n${user}` }] }],
            generationConfig: { temperature: 0.3, maxOutputTokens: 260 },
          }),
        },
      );
      if (res.ok) {
        const d = await res.json();
        const text = d.candidates?.[0]?.content?.parts?.[0]?.text?.trim();
        if (text) return { text, provider: `gemini:${model}` };
      }
    } catch {
      /* fall through */
    }
  }

  const cohere = process.env.COHERE_API_KEY;
  if (cohere) {
    try {
      const model = process.env.COHERE_MODEL ?? "command-r-08-2024";
      const res = await fetch("https://api.cohere.com/v2/chat", {
        method: "POST",
        headers: { Authorization: `Bearer ${cohere}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          model, temperature: 0.3, max_tokens: 260,
          messages: [
            { role: "system", content: system },
            { role: "user", content: user },
          ],
        }),
      });
      if (res.ok) {
        const d = await res.json();
        const text = d.message?.content?.[0]?.text?.trim();
        if (text) return { text, provider: `cohere:${model}` };
      }
    } catch {
      /* fall through */
    }
  }

  return null;
}

export async function POST(request: Request) {
  let payload: {
    year?: unknown;
    round?: unknown;
    question?: unknown;
    history?: unknown;
  };
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
  const history = (Array.isArray(payload.history) ? payload.history : [])
    .filter((m): m is { role: string; text: string } =>
      !!m && typeof m.text === "string")
    .slice(-4);

  let facts;
  try {
    const origin = new URL(request.url).origin;
    facts = buildFacts(await loadFacts(origin, year, round));
  } catch {
    return Response.json({ error: "race not found" }, { status: 404 });
  }

  // Short follow-ups ("why?", "how?") carry no terms of their own, so retrieve
  // using the previous question for context — lightweight conversational RAG.
  const prevUser = [...history].reverse().find((m) => m.role === "user")?.text;
  const retrieveQuery =
    question.trim().split(/\s+/).length <= 3 && prevUser
      ? `${prevUser} ${question}`
      : question;
  const retrieved = retrieve(facts, retrieveQuery, 6);

  // For questions that reach beyond this race, pull live web results so the
  // model answers from real current sources instead of stale guesses.
  const web = GENERAL_RE.test(question) ? await searchWeb(retrieveQuery) : [];

  let answer: string;
  let citations: Citation[];
  let source: string;
  // LLM reasons over the whole race + web; retrieval drives race citations.
  const llm = await llmAnswer(question, facts, history, web);
  if (llm) {
    answer = llm.text;
    citations = retrieved
      .slice(0, 3)
      .map((r) => r.fact.cite)
      .filter((c): c is Citation => !!c);
    for (const w of web.slice(0, 3)) {
      citations.push({ kind: "web", label: w.title.slice(0, 40), url: w.url });
    }
    source = web.length ? `${llm.provider} + web` : llm.provider;
  } else {
    ({ answer, citations } = extractiveAnswer(retrieved));
    source = "extractive";
  }

  return Response.json({ answer, citations, source, retrieved: retrieved.length });
}
