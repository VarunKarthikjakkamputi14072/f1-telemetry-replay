"""
Correctness layer for the web export.

The desktop app approximated gaps as `metres / 70` and inferred position from a
cumulative-distance sort. Here we do it properly: every driver is resampled onto
one shared session clock, and time gaps are derived by asking *when the car ahead
was at the position the car behind is now* — the same thing a real timing screen does.

All functions are pure (numpy in, numpy/plain-python out) so they're easy to test.
"""
from __future__ import annotations

import numpy as np


def cumulative_distance(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Monotonic distance travelled along the (x, y) path, in the same units as x/y."""
    if len(x) == 0:
        return np.zeros(0)
    dx = np.diff(x)
    dy = np.diff(y)
    step = np.sqrt(dx * dx + dy * dy)
    return np.concatenate([[0.0], np.cumsum(step)])


def resample(grid: np.ndarray, t: np.ndarray, values: np.ndarray) -> np.ndarray:
    """
    Linear-interpolate `values` (sampled at times `t`) onto `grid`.

    np.interp clamps outside the range, so callers must mask frames where a driver
    has no data (see active_range). `t` must be sorted ascending.
    """
    if len(t) == 0:
        return np.zeros_like(grid)
    return np.interp(grid, t, values)


def active_range(grid: np.ndarray, t_start: float, t_end: float) -> tuple[int, int]:
    """First/last grid indices (inclusive) covered by a driver's data window."""
    f0 = int(np.searchsorted(grid, t_start, side="left"))
    f1 = int(np.searchsorted(grid, t_end, side="right")) - 1
    f0 = max(0, min(f0, len(grid) - 1))
    f1 = max(0, min(f1, len(grid) - 1))
    return f0, f1


def time_at_distance(leader_dist: np.ndarray, leader_t: np.ndarray, d: float) -> float:
    """
    Interpolate the time at which a (monotonic) leader trace passed track-distance `d`.

    This is the heart of a correct time gap: the gap from a follower to the leader is
    `t_now - time_at_distance(leader, follower_distance_now)`.
    """
    if d <= leader_dist[0]:
        return float(leader_t[0])
    if d >= leader_dist[-1]:
        return float(leader_t[-1])
    return float(np.interp(d, leader_dist, leader_t))


def lap_gap_to_leader(laps_by_driver: dict) -> dict:
    """
    Time gap to the lap leader at the completion of each lap, per driver.

    laps_by_driver[code] = list of {"lap": int, "t": float, "pos": int|None}
    where `t` is the session time (seconds) the car crossed the line to end that lap.
    Gap = driver's crossing time - the crossing time of whoever was P1 on that lap.
    Returns {code: [{"lap": L, "gap": seconds}, ...]} (leader gap == 0).
    """
    # Index: lap number -> {code: t} and find the P1 crossing time per lap.
    per_lap: dict[int, dict[str, float]] = {}
    leader_t: dict[int, float] = {}
    for code, rows in laps_by_driver.items():
        for r in rows:
            L = r["lap"]
            if r["t"] is None:
                continue
            per_lap.setdefault(L, {})[code] = r["t"]
            if r.get("pos") == 1:
                leader_t[L] = r["t"]

    # Fallback: if no explicit P1 flag for a lap, the earliest crossing time leads.
    for L, times in per_lap.items():
        if L not in leader_t and times:
            leader_t[L] = min(times.values())

    out: dict[str, list] = {code: [] for code in laps_by_driver}
    for code, rows in laps_by_driver.items():
        for r in rows:
            L, t = r["lap"], r["t"]
            if t is None or L not in leader_t:
                continue
            out[code].append({"lap": L, "gap": round(t - leader_t[L], 3)})
    return out


def detect_undercuts(stints_by_driver: dict, pos_by_lap: dict) -> list:
    """
    Flag likely undercut / overcut successes around pit stops.

    A driver who pits and emerges ahead of a rival they were behind a couple of laps
    earlier (and stays ahead) is credited with an undercut; pitting later and still
    coming out ahead is an overcut. Heuristic, but grounded in real position deltas.

    stints_by_driver[code] = list of {"compound", "lap_start", "lap_end"}
    pos_by_lap[code] = {lap: position}
    Returns [{"driver", "rival", "lap", "kind", "gained"}].
    """
    events = []
    pit_laps = {}
    for code, stints in stints_by_driver.items():
        # A new stint (after the first) starts the lap after a pit stop.
        laps = sorted(s["lap_start"] for s in stints)
        pit_laps[code] = laps[1:] if len(laps) > 1 else []

    def pos(code, lap):
        return pos_by_lap.get(code, {}).get(lap)

    for code, plaps in pit_laps.items():
        for pl in plaps:
            before, after = pl - 2, pl + 2
            for rival in pos_by_lap:
                if rival == code:
                    continue
                pb, pa = pos(code, before), pos(code, after)
                rb, ra = pos(rival, before), pos(rival, after)
                if None in (pb, pa, rb, ra):
                    continue
                # Was behind the rival, now ahead and holding it.
                if pb > rb and pa < ra:
                    rival_pits = pit_laps.get(rival, [])
                    kind = "undercut" if any(abs(rp - pl) <= 3 and rp >= pl for rp in rival_pits) or not rival_pits else "overcut"
                    # If the rival pitted clearly earlier, our man stayed out longer -> overcut.
                    if rival_pits and min(rival_pits, key=lambda rp: abs(rp - pl)) < pl - 1:
                        kind = "overcut"
                    events.append({
                        "driver": code, "rival": rival, "lap": int(pl),
                        "kind": kind, "gained": int(pb - pa),
                    })
    # De-dup: keep the strongest gain per (driver, lap).
    best = {}
    for e in events:
        key = (e["driver"], e["lap"])
        if key not in best or e["gained"] > best[key]["gained"]:
            best[key] = e
    return sorted(best.values(), key=lambda e: (e["lap"], e["driver"]))
