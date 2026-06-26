// Live web search for the strategist, so questions beyond the race data (a
// driver's current team, the latest season, records) can be answered from real,
// up-to-date sources instead of a static model guessing. Tiered: Tavily -> Brave
// (if a key is set) -> Wikipedia (keyless, always available). Server-only.

export interface WebResult {
  title: string;
  snippet: string;
  url: string;
}

async function tavily(query: string): Promise<WebResult[]> {
  const key = process.env.TAVILY_API_KEY;
  if (!key) return [];
  const res = await fetch("https://api.tavily.com/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      api_key: key,
      query,
      max_results: 4,
      search_depth: "basic",
    }),
  });
  if (!res.ok) return [];
  const d = await res.json();
  return (d.results ?? []).slice(0, 4).map(
    (r: { title?: string; content?: string; url?: string }) => ({
      title: r.title ?? "",
      snippet: (r.content ?? "").slice(0, 500),
      url: r.url ?? "",
    }),
  );
}

async function brave(query: string): Promise<WebResult[]> {
  const key = process.env.BRAVE_API_KEY;
  if (!key) return [];
  const res = await fetch(
    `https://api.search.brave.com/res/v1/web/search?q=${encodeURIComponent(query)}&count=4`,
    { headers: { "X-Subscription-Token": key, Accept: "application/json" } },
  );
  if (!res.ok) return [];
  const d = await res.json();
  return (d.web?.results ?? []).slice(0, 4).map(
    (r: { title?: string; description?: string; url?: string }) => ({
      title: r.title ?? "",
      snippet: (r.description ?? "").slice(0, 500),
      url: r.url ?? "",
    }),
  );
}

// Keyless fallback: full-text search Wikipedia (handles natural-language queries,
// unlike prefix opensearch) for the top page, then return its current summary.
async function wikipedia(query: string): Promise<WebResult[]> {
  const ua = { "User-Agent": "Apex-F1/1.0 (portfolio project)" };
  try {
    const sr = await fetch(
      `https://en.wikipedia.org/w/api.php?action=query&list=search&srlimit=3&format=json&origin=*&srsearch=${encodeURIComponent(query)}`,
      { headers: ua },
    );
    if (!sr.ok) return [];
    const j = await sr.json();
    const titles: string[] = (j.query?.search ?? []).map((h: { title: string }) => h.title);
    if (!titles.length) return [];
    const out = await Promise.all(
      titles.slice(0, 3).map(async (title): Promise<WebResult | null> => {
        const sum = await fetch(
          `https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(title)}`,
          { headers: ua },
        );
        if (!sum.ok) return null;
        const s = await sum.json();
        if (!s.extract) return null;
        return {
          title: s.title ?? title,
          snippet: String(s.extract).slice(0, 450),
          url: s.content_urls?.desktop?.page ?? `https://en.wikipedia.org/wiki/${encodeURIComponent(title)}`,
        };
      }),
    );
    return out.filter((r): r is WebResult => !!r);
  } catch {
    return [];
  }
}

/** Best available web results for `query`, biased to Formula 1. */
export async function searchWeb(query: string): Promise<WebResult[]> {
  const q = /formula|f1|grand prix/i.test(query) ? query : `${query} Formula 1`;
  for (const provider of [tavily, brave, wikipedia]) {
    try {
      const out = await provider(q);
      if (out.length) return out;
    } catch {
      /* try next provider */
    }
  }
  return [];
}
