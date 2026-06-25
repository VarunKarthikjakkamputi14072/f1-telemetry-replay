"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import type { Meta } from "@/lib/types";
import type { Citation } from "@/lib/strategist";

interface Msg {
  role: "user" | "assistant";
  text: string;
  citations?: Citation[];
  source?: string;
}

const SUGGESTIONS = [
  "Who won and how?",
  "What was the fastest lap?",
  "Explain the safety car strategy",
  "Who had the best tyre strategy?",
];

export default function StrategistTab({ meta }: { meta: Meta }) {
  const [input, setInput] = useState("");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const ask = async (q: string) => {
    const question = q.trim();
    if (!question || loading) return;
    setInput("");
    setMsgs((m) => [...m, { role: "user", text: question }]);
    setLoading(true);
    try {
      const res = await fetch("/api/strategist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          year: meta.year,
          round: meta.round,
          question,
          history: msgs.slice(-4).map((m) => ({ role: m.role, text: m.text })),
        }),
      });
      const data = await res.json();
      setMsgs((m) => [
        ...m,
        res.ok
          ? { role: "assistant", text: data.answer, citations: data.citations, source: data.source }
          : { role: "assistant", text: data.error ?? "Something went wrong." },
      ]);
    } catch {
      setMsgs((m) => [...m, { role: "assistant", text: "Could not reach the strategist." }]);
    } finally {
      setLoading(false);
      requestAnimationFrame(() =>
        scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight }),
      );
    }
  };

  return (
    <div className="panel flex h-[600px] flex-col p-5">
      <div className="mb-1 flex items-baseline justify-between">
        <h2 className="text-lg font-bold">Ask the Strategist</h2>
        <span className="text-xs text-muted-2">grounded in this race&apos;s data</span>
      </div>
      <p className="mb-3 text-sm text-muted-2">
        Questions are answered by retrieving facts from the race telemetry, with
        citations. Set <code className="rounded bg-panel-2 px-1">GROQ_API_KEY</code>{" "}
        for Llama-written answers; otherwise replies are extractive.
      </p>

      <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
        {msgs.length === 0 && (
          <div className="flex flex-wrap gap-2">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => ask(s)}
                className="rounded-full border border-border px-3 py-1.5 text-xs text-muted transition hover:border-accent hover:text-text"
              >
                {s}
              </button>
            ))}
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={m.role === "user" ? "text-right" : ""}>
            <div
              className={`inline-block max-w-[85%] rounded-xl px-3 py-2 text-sm ${
                m.role === "user"
                  ? "bg-accent/20 text-text"
                  : "bg-panel-2 text-text"
              }`}
            >
              <p className="leading-relaxed whitespace-pre-wrap">{m.text}</p>
              {m.citations && m.citations.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {m.citations.map((c, j) =>
                    c.kind === "driver" && c.driver ? (
                      <Link
                        key={j}
                        href={`/race/${meta.year}/${meta.round}/driver/${c.driver}`}
                        className="rounded border border-border bg-bg-elev px-1.5 py-0.5 text-[10px] text-muted transition hover:text-text"
                      >
                        {c.label} ↗
                      </Link>
                    ) : (
                      <span
                        key={j}
                        className="rounded border border-border bg-bg-elev px-1.5 py-0.5 text-[10px] text-muted-2"
                      >
                        {c.label}
                      </span>
                    ),
                  )}
                </div>
              )}
              {m.source && (
                <div className="mt-1 text-[10px] text-muted-2">
                  {m.source === "extractive"
                    ? "Extractive · from facts"
                    : `${m.source} · grounded`}
                </div>
              )}
            </div>
          </div>
        ))}
        {loading && <div className="text-sm text-muted-2">Thinking…</div>}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(input);
        }}
        className="mt-3 flex gap-2"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about strategy, pace, incidents…"
          className="flex-1 rounded-lg border border-border bg-panel-2 px-3 py-2 text-sm text-text outline-none transition focus:border-accent placeholder:text-muted-2"
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition hover:bg-accent-2 disabled:opacity-40"
        >
          Ask
        </button>
      </form>
    </div>
  );
}
