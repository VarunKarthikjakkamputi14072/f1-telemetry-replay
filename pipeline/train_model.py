"""
Tyre-degradation / pace model (the Meridian-style MLOps step).

    python -m pipeline.train_model

Reads every race already exported under web/public/data, assembles a green-flag
lap dataset (tyre age, compound, fuel load proxy, track temp), and trains a
gradient-boosted regressor to predict lap-time pace (seconds above the race
median). Writes a self-contained "model card" to web/public/data/model.json:
metrics, feature importances, the learned per-compound degradation curves, and a
lightweight per-race drift check (the kind of thing Evidently/MLflow would track).
"""
from __future__ import annotations

import glob
import json
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DATA = os.path.join(ROOT, "web", "public", "data")
DRY = ["SOFT", "MEDIUM", "HARD"]
COMPOUNDS = DRY + ["INTER", "WET"]


def _sc_laps(events, ref_laps):
    bands = [(b["start"], b["end"]) for b in events.get("trackStatus", [])
             if b["type"] in ("SC", "VSC")]
    if not bands:
        return set()
    laps = sorted((r["lap"], r["t"]) for r in ref_laps if r["lap"] and r["t"])
    sc, prev = set(), (laps[0][1] - 120 if laps else 0)
    for lap, t in laps:
        if any(bs < t and be > prev for bs, be in bands):
            sc.add(lap)
        prev = t
    return sc


def _track_temp_fn(weather):
    if not weather:
        return lambda t: 30.0
    ts = np.array([w["t"] for w in weather])
    tk = np.array([w["track"] for w in weather])
    return lambda t: float(np.interp(t, ts, tk))


def build_dataset():
    rows = []
    for meta_path in glob.glob(os.path.join(WEB_DATA, "*", "*", "meta.json")):
        d = os.path.dirname(meta_path)
        try:
            meta = json.load(open(meta_path))
            laps = json.load(open(os.path.join(d, "laps.json")))
            analytics = json.load(open(os.path.join(d, "analytics.json")))
            events = json.load(open(os.path.join(d, "events.json")))
        except FileNotFoundError:
            continue
        total = meta["totalLaps"]
        race_id = f"{meta['year']} {meta['race']}"
        # compound + age per (driver, lap) from stints
        comp_age = {}
        for code, stints in analytics["stints"].items():
            for s in stints:
                for lap in range(s["lapStart"], s["lapEnd"] + 1):
                    comp_age[(code, lap)] = (s["compound"], lap - s["lapStart"] + 1)
        ref = max(laps.values(), key=lambda L: sum(1 for r in L if r["t"]), default=[])
        sc = _sc_laps(events, ref)
        temp_fn = _track_temp_fn(events.get("weather", []))

        race_rows = []
        for code, recs in laps.items():
            for r in recs:
                lap = r.get("lap")
                lt = r.get("lapTime")
                if lap is None or not lt or lt <= 0 or r.get("pitIn") or r.get("pitOut"):
                    continue
                if lap in sc or (code, lap) not in comp_age:
                    continue
                comp, age = comp_age[(code, lap)]
                if comp not in COMPOUNDS:
                    continue
                race_rows.append({
                    "race": race_id, "lapTime": lt, "age": age,
                    "compound": comp, "fuelFrac": lap / total,
                    "trackTemp": round(temp_fn(r["t"]) if r["t"] else 30.0, 1),
                })
        if not race_rows:
            continue
        med = np.median([x["lapTime"] for x in race_rows])
        for x in race_rows:
            if x["lapTime"] <= med * 1.07:  # drop traffic / out-of-position laps
                x["pace"] = round(x["lapTime"] - med, 3)  # seconds above race median
                rows.append(x)
    return pd.DataFrame(rows)


def main():
    df = build_dataset()
    if len(df) < 200:
        raise SystemExit(f"❌ not enough data ({len(df)} laps) — export more races first")
    print(f"📊 {len(df)} green-flag laps from {df['race'].nunique()} races")

    # Quantify the fuel-burn effect (reported, not removed): per-race slope of
    # pace vs fuel fraction — cars get lighter and faster through the race.
    fuel_slopes = [np.polyfit(sub["fuelFrac"], sub["pace"], 1)[0]
                   for _, sub in df.groupby("race")]
    fuel_effect = round(float(np.mean(fuel_slopes)), 2)  # s across a full fuel load
    print(f"⛽ mean fuel effect {fuel_effect:.2f}s over a full fuel load")

    feat = pd.get_dummies(df["compound"]).reindex(columns=COMPOUNDS, fill_value=0)
    X = pd.concat([df[["age", "fuelFrac", "trackTemp"]].reset_index(drop=True),
                   feat.reset_index(drop=True)], axis=1)
    y = df["pace"].to_numpy()

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42)
    model = GradientBoostingRegressor(n_estimators=250, max_depth=3,
                                      learning_rate=0.05, random_state=42)
    model.fit(X_tr, y_tr)
    pred = model.predict(X_te)
    mae = float(mean_absolute_error(y_te, pred))
    r2 = float(r2_score(y_te, pred))
    print(f"🎯 test MAE {mae:.3f}s  R² {r2:.3f}")

    importances = dict(zip(X.columns, model.feature_importances_))
    importances = {k: round(float(v), 3) for k, v in
                   sorted(importances.items(), key=lambda kv: -kv[1])}

    # Estimated tyre-age effect: predicted pace vs age per dry compound, with
    # fuel load and track temp held at their means.
    mean_fuel = float(df["fuelFrac"].mean())
    mean_temp = float(df["trackTemp"].mean())
    curves, slopes = {}, {}
    for comp in DRY:
        sub = df[df["compound"] == comp]
        if len(sub) < 40:
            continue
        max_age = int(np.percentile(sub["age"], 95))
        ages = list(range(1, max(6, max_age) + 1))
        grid = pd.DataFrame({"age": ages})
        grid["fuelFrac"] = mean_fuel
        grid["trackTemp"] = mean_temp
        for c in COMPOUNDS:
            grid[c] = 1 if c == comp else 0
        grid = grid[X.columns]
        preds = model.predict(grid)
        base = preds[0]
        curves[comp] = [{"age": a, "pace": round(float(p - base), 3)}
                        for a, p in zip(ages, preds)]
        slopes[comp] = round(float((preds[-1] - preds[0]) / max(1, ages[-1] - 1)), 3)

    # Drift: per-race feature/target shift vs the global distribution.
    g_temp, g_temp_sd = df["trackTemp"].mean(), df["trackTemp"].std() or 1.0
    drift = []
    for race, sub in df.groupby("race"):
        z = abs(sub["trackTemp"].mean() - g_temp) / g_temp_sd
        drift.append({
            "race": race, "n": int(len(sub)),
            "trackTempMean": round(float(sub["trackTemp"].mean()), 1),
            "paceSpread": round(float(sub["pace"].std()), 2),
            "drift": round(float(z), 2),
            "drifted": bool(z > 1.0),
        })
    drift.sort(key=lambda d: -d["drift"])

    card = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "model": "GradientBoostingRegressor",
        "target": "lap-time pace (s above race median)",
        "features": list(X.columns),
        "fuelEffect": fuel_effect,
        "nSamples": int(len(df)),
        "races": sorted(df["race"].unique().tolist()),
        "metrics": {"mae": round(mae, 3), "r2": round(r2, 3)},
        "importances": importances,
        "curves": curves,
        "slopes": slopes,
        "drift": drift,
    }
    out = os.path.join(WEB_DATA, "model.json")
    with open(out, "w") as f:
        json.dump(card, f, separators=(",", ":"))
    print(f"📦 wrote {out} ({os.path.getsize(out) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
