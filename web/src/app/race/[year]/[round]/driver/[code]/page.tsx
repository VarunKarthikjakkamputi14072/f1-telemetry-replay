"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { getRaceData } from "@/lib/data";
import type { RaceData } from "@/lib/types";
import DriverReport from "@/components/DriverReport";

export default function DriverPage({
  params,
}: {
  params: Promise<{ year: string; round: string; code: string }>;
}) {
  const { year, round, code } = use(params);
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
      <main className="mx-auto max-w-[1100px] px-4 py-10">
        <div className="skeleton mb-4 h-8 w-64 rounded" />
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="skeleton h-[260px] rounded-xl lg:col-span-2" />
          <div className="skeleton h-[240px] rounded-xl" />
          <div className="skeleton h-[240px] rounded-xl" />
        </div>
      </main>
    );
  }

  return <DriverReport data={data} code={decodeURIComponent(code)} />;
}
