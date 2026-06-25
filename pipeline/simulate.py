"""
Monte Carlo race-strategy simulator (what real strategy teams run).

    python -m pipeline.simulate            # simulate every exported race

For each race it builds a clear-air pace model from the trained tyre model
(compound offsets + learned degradation + fuel burn-off), enumerates plausible
1- and 2-stop strategies, and Monte-Carlo-simulates each one thousands of times
with random safety-car events (which make a stop cheap). It ranks strategies by
mean race time and writes the optimal plan + a finish-time distribution to each
race's simulation.json, alongside how the actual winner's strategy fares.
"""
from __future__ import annotations

import glob
import json
import os

import numpy as np

WEB_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "web", "public", "data")

DRY = ["SOFT", "MEDIUM", "HARD"]
COMPOUND_OFFSET = {"SOFT": -0.7, "MEDIUM": 0.0, "HARD": 0.45}  # fresh-tyre pace, s/lap
DEFAULT_DEG = {"SOFT": 0.09, "MEDIUM": 0.055, "HARD": 0.04}     # linear deg, s/lap
TYRE_LIFE = {"SOFT": 18, "MEDIUM": 30, "HARD": 42}             # cliff onset (laps)
CLIFF = 0.06                                                    # s/lap² past the cliff
PIT_LOSS = 22.0
SC_PIT_LOSS = 11.0
P_SC = 0.55          # chance a race sees at least one safety car
SC_LEN = 4           # laps a safety car neutralises
N_SIMS = 4000
RNG = np.random.default_rng(42)  # seeded -> reproducible


def _deg_rates(model):
    rates = {}
    slopes = (model or {}).get("slopes", {})
    for c in DRY:
        s = slopes.get(c)
        rates[c] = float(np.clip(s, 0.02, 0.12)) if (s and s > 0) else DEFAULT_DEG[c]
    return rates


def _stint_time(compound, n_laps, start_lap, total, base, deg, fuel_k):
    """Deterministic time for a stint of n_laps starting on `start_lap` (relative)."""
    laps = np.arange(n_laps)
    age = laps + 1
    lap_no = start_lap + laps
    life = TYRE_LIFE.get(compound, 30)
    # Tyres "fall off" past their life; cap so a freak long stint (e.g. a
    # red-flag race) doesn't blow up to an absurd time.
    cliff = np.minimum(CLIFF * np.maximum(0, age - life) ** 2, 4.0)
    pace = (base + COMPOUND_OFFSET.get(compound, 0.0) + deg.get(compound, 0.05) * age
            + cliff + fuel_k * (total - lap_no) / total)
    return float(pace.sum())


def _candidates(total):
    """Plausible 1- and 2-stop strategies (compound sequences must use 2 compounds)."""
    cands = []
    # 1-stop
    for pit in range(int(total * 0.3), int(total * 0.7), 2):
        for a in DRY:
            for b in DRY:
                if a == b:
                    continue
                cands.append([(a, 1, pit), (b, pit + 1, total)])
    # 2-stop
    for p1 in range(int(total * 0.2), int(total * 0.45), 3):
        for p2 in range(p1 + 8, int(total * 0.8), 3):
            for seq in [("SOFT", "MEDIUM", "HARD"), ("MEDIUM", "HARD", "SOFT"),
                        ("SOFT", "HARD", "MEDIUM"), ("MEDIUM", "SOFT", "MEDIUM"),
                        ("HARD", "MEDIUM", "SOFT")]:
                cands.append([(seq[0], 1, p1), (seq[1], p1 + 1, p2), (seq[2], p2 + 1, total)])
    return cands


def _simulate(strategy, total, base, deg, fuel_k):
    """Return (mean_time, std_time, samples) over N_SIMS with random safety cars."""
    # Deterministic green-running time.
    green = 0.0
    pit_laps = []
    for compound, start, end in strategy:
        green += _stint_time(compound, end - start + 1, start, total, base, deg, fuel_k)
        if end < total:
            pit_laps.append(end)
    n_stops = len(pit_laps)

    # Monte Carlo over safety-car occurrence/timing.
    has_sc = RNG.random(N_SIMS) < P_SC
    sc_lap = RNG.integers(1, total, N_SIMS)
    times = np.full(N_SIMS, green)
    for pl in pit_laps:
        cheap = has_sc & (np.abs(sc_lap - pl) <= SC_LEN)
        times += np.where(cheap, SC_PIT_LOSS, PIT_LOSS)
    # A safety car also slows the field a little regardless (neutralised laps).
    times += np.where(has_sc, SC_LEN * 1.5, 0.0)
    return float(times.mean()), float(times.std()), times, n_stops


def _describe(strategy):
    return [{"compound": c, "lapStart": s, "lapEnd": e} for c, s, e in strategy]


def simulate_race(d):
    meta = json.load(open(os.path.join(d, "meta.json")))
    laps = json.load(open(os.path.join(d, "laps.json")))
    analytics = json.load(open(os.path.join(d, "analytics.json")))
    model = None
    mp = os.path.join(WEB_DATA, "model.json")
    if os.path.exists(mp):
        model = json.load(open(mp))

    total = meta["totalLaps"]
    deg = _deg_rates(model)
    fuel_k = abs((model or {}).get("fuelEffect", 6.0))
    green_laps = [r["lapTime"] for recs in laps.values() for r in recs
                  if r.get("lapTime") and r["lapTime"] > 0 and not r.get("pitIn") and not r.get("pitOut")]
    base = float(np.median(green_laps)) if green_laps else 90.0

    results = []
    for strat in _candidates(total):
        mean, std, _, n_stops = _simulate(strat, total, base, deg, fuel_k)
        results.append((mean, std, n_stops, strat))
    results.sort(key=lambda r: r[0])

    best_mean = results[0][0]
    top = [{
        "stints": _describe(s), "stops": n, "meanTime": round(m, 1),
        "deltaToOptimal": round(m - best_mean, 1),
    } for (m, sd, n, s) in results[:5]]

    # Distribution for the optimal strategy.
    _, _, samples, _ = _simulate(results[0][3], total, base, deg, fuel_k)
    lo, hi = float(samples.min()), float(samples.max())
    bins = np.linspace(lo, hi, 21)
    hist, edges = np.histogram(samples, bins=bins)
    dist = [{"t": round(float((edges[i] + edges[i + 1]) / 2 - best_mean), 1),
             "count": int(hist[i])} for i in range(len(hist))]

    # How did the actual winner's strategy fare in the same simulator?
    winner = None
    final = {c: p[max(p, key=lambda k: int(k))] for c, p in analytics["positionByLap"].items() if p}
    if final:
        wc = min(final, key=final.get)
        wstints = analytics["stints"].get(wc, [])
        # The simulator models dry running only; skip wet-race winners.
        if wstints and all(s["compound"] in DRY for s in wstints):
            strat = [(s["compound"], s["lapStart"], s["lapEnd"]) for s in wstints]
            wm, _, _, wn = _simulate(strat, total, base, deg, fuel_k)
            delta = wm - best_mean
            # Skip anomalous races (e.g. red-flagged) the clear-air sim can't model.
            if delta <= 120:
                winner = {"code": wc, "stints": _describe(strat), "stops": wn,
                          "meanTime": round(wm, 1), "deltaToOptimal": round(delta, 1)}

    out = {
        "totalLaps": total, "nSims": N_SIMS, "baseLap": round(base, 2),
        "degRates": {k: round(v, 3) for k, v in deg.items()},
        "optimal": top[0], "alternatives": top[1:], "distribution": dist,
        "winner": winner,
    }
    write = os.path.join(d, "simulation.json")
    with open(write, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    return meta, out


def main():
    races = sorted(glob.glob(os.path.join(WEB_DATA, "*", "*", "meta.json")))
    for mp in races:
        d = os.path.dirname(mp)
        meta, out = simulate_race(d)
        opt = out["optimal"]
        seq = " ".join(s["compound"][0] for s in opt["stints"])
        w = out["winner"]
        print(f"   {meta['year']} {meta['race']:<26} optimal {opt['stops']}-stop [{seq}]"
              + (f"  winner +{w['deltaToOptimal']}s" if w else ""))


if __name__ == "__main__":
    main()
