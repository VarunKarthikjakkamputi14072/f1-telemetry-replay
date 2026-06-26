import {
  buildFacts,
  extractiveAnswer,
  retrieve,
  type Citation,
  type Fact,
  type FactsInput,
} from "@/lib/strategist";

export const runtime = "nodejs";

// Driver name -> Wikipedia title, so questions about a driver's career or what
// they're doing *now* are grounded in live, current info rather than the model's
// stale training data. Keyless (Wikipedia REST). Add names as needed.
const DRIVER_WIKI: Record<string, string> = {
  hamilton: "Lewis_Hamilton", verstappen: "Max_Verstappen",
  leclerc: "Charles_Leclerc", norris: "Lando_Norris", russell: "George_Russell",
  sainz: "Carlos_Sainz_Jr.", perez: "Sergio_Pérez", alonso: "Fernando_Alonso",
  vettel: "Sebastian_Vettel", schumacher: "Michael_Schumacher",
  senna: "Ayrton_Senna", prost: "Alain_Prost", piastri: "Oscar_Piastri",
  gasly: "Pierre_Gasly", ocon: "Esteban_Ocon", stroll: "Lance_Stroll",
  tsunoda: "Yuki_Tsunoda", bottas: "Valtteri_Bottas", ricciardo: "Daniel_Ricciardo",
  hulkenberg: "Nico_Hülkenberg", albon: "Alexander_Albon", raikkonen: "Kimi_Räikkönen",
  rosberg: "Nico_Rosberg", button: "Jenson_Button", massa: "Felipe_Massa",
  webber: "Mark_Webber", antonelli: "Andrea_Kimi_Antonelli", colapinto: "Franco_Colapinto",
};

// Fetch a 1-paragraph Wikipedia summary for the first driver mentioned. Returns
// "" on miss/failure (best-effort live knowledge).
async function wikiBackground(text: string): Promise<string> {
  const q = text.toLowerCase();
  const title = Object.entries(DRIVER_WIKI).find(([k]) =>
    new RegExp(`\\b${k}\\b`).test(q),
  )?.[1];
  if (!title) return "";
  try {
    const res = await fetch(
      `https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(title)}`,
      { headers: { "User-Agent": "apex-f1/1.0" } },
    );
    if (!res.ok) return "";
    const d = await res.json();
    return typeof d.extract === "string" ? d.extract : "";
  } catch {
    return "";
  }
}

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
): Promise<{ text: string; provider: string } | null> {
  // Give the model the whole race's facts (capped) so it can reason about
  // anything — penalties, incidents, who pitted most — not just a few cards.
  const facts = contextFacts.slice(0, 140).map((f) => `- ${f.text}`).join("\n");
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
    "CRITICAL — accuracy over agreeableness: you have a training cutoff and NO live " +
    "data. Do NOT state current-day facts you can't be sure of — a driver's CURRENT " +
    "team, the latest/ongoing season, recent transfers or standings are beyond your " +
    "reliable knowledge. For those, say plainly that you don't have live information " +
    "and can only speak to this race and well-established history. Never just agree " +
    "with the user's claim to be polite — if you can't verify it, say so. It is " +
    "better to admit a limit than to guess. Keep answers to a few sentences unless " +
    "more detail is clearly wanted.";
  const convo = history.length
    ? "Conversation so far:\n" +
      history.map((m) => `${m.role === "user" ? "Q" : "A"}: ${m.text}`).join("\n") +
      "\n\n"
    : "";
  const user = `${convo}Question: ${question}\n\nFacts about this race:\n${facts}`;

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

  let answer: string;
  let citations: Citation[];
  let source: string;
  // LLM reasons over the whole race; retrieval drives citations + the fallback.
  const llm = await llmAnswer(question, facts, history);
  if (llm) {
    answer = llm.text;
    citations = retrieved
      .slice(0, 4)
      .map((r) => r.fact.cite)
      .filter((c): c is Citation => !!c);
    source = llm.provider;
  } else {
    ({ answer, citations } = extractiveAnswer(retrieved));
    source = "extractive";
  }

  return Response.json({ answer, citations, source, retrieved: retrieved.length });
}
