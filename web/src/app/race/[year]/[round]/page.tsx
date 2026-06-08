"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { getRaceData } from "@/lib/data";
import type { RaceData } from "@/lib/types";
import RaceView from "@/components/RaceView";

export default function RacePage({
  params,
}: {
  params: Promise<{ year: string; round: string }>;
}) {
  const { year, round } = use(params);
  const [data, setData] = useState<RaceData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getRaceData(year, round)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(String(e)));
    return () => {
      alive = false;
    };
  }, [year, round]);

  if (error) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-20">
        <p className="text-accent-2">Could not load race data: {error}</p>
        <Link href="/" className="mt-4 inline-block text-muted hover:text-text">
          ← Back
        </Link>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="mx-auto max-w-6xl px-6 py-10">
        <div className="skeleton mb-4 h-8 w-64 rounded" />
        <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
          <div className="skeleton h-[560px] rounded-xl" />
          <div className="skeleton h-[560px] rounded-xl" />
        </div>
      </main>
    );
  }

  return <RaceView data={data} />;
}
