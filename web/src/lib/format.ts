// Tyre compound colours follow the Pirelli / F1 broadcast palette.
export const COMPOUND_COLOR: Record<string, string> = {
  SOFT: "#ef4444",
  MEDIUM: "#f4d03f",
  HARD: "#e8eaf0",
  INTER: "#22c55e",
  WET: "#3b82f6",
};

export const COMPOUND_LABEL: Record<string, string> = {
  SOFT: "S",
  MEDIUM: "M",
  HARD: "H",
  INTER: "I",
  WET: "W",
};

export function fmtClock(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  const cs = Math.floor((seconds % 1) * 100);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}.${String(
    cs,
  ).padStart(2, "0")}`;
}

export function fmtLapTime(seconds: number | null): string {
  if (seconds == null || !isFinite(seconds)) return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toFixed(3).padStart(6, "0")}`;
}

export function fmtGap(seconds: number): string {
  if (!isFinite(seconds)) return "—";
  if (seconds <= 0) return "Leader";
  return `+${seconds.toFixed(3)}`;
}
