"""
Export one race's telemetry to quantized JSON for the web app.

    python -m pipeline.export --year 2021 --race "Abu Dhabi"
    python -m pipeline.export --year 2023 --race "Brazil" --step 0.5

Heavy, browser-unfriendly work (FastF1 download, resampling, gap math) happens here
once; the front-end just reads the JSON. Output lands in web/public/data/<year>/<round>/.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings

import fastf1
import numpy as np
import pandas as pd

from .compute import (
    active_range,
    cumulative_distance,
    detect_undercuts,
    lap_gap_to_leader,
    resample,
)
from .engineer import build_engineer

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, "cache")
WEB_DATA = os.path.join(ROOT, "web", "public", "data")

# Tidy FastF1 compound names -> the tokens the web app styles.
COMPOUND = {
    "SOFT": "SOFT", "MEDIUM": "MEDIUM", "HARD": "HARD",
    "INTERMEDIATE": "INTER", "WET": "WET",
}


def _secs(series: pd.Series) -> np.ndarray:
    """Timedelta/numeric series -> float seconds array."""
    if pd.api.types.is_timedelta64_dtype(series):
        return series.dt.total_seconds().to_numpy()
    return pd.to_numeric(series, errors="coerce").to_numpy()


def _qi(arr) -> list:
    """Quantize a float array to a list of ints (NaNs -> 0)."""
    a = np.asarray(arr, dtype=float)
    a = np.nan_to_num(a, nan=0.0, posinf=0.0, neginf=0.0)
    return np.rint(a).astype(int).tolist()


def _td_secs(val):
    """A single Timedelta/NaT -> float seconds or None."""
    if val is None or pd.isna(val):
        return None
    return float(val.total_seconds()) if hasattr(val, "total_seconds") else float(val)


def load_session(year: int, race: str):
    os.makedirs(CACHE_DIR, exist_ok=True)
    fastf1.Cache.enable_cache(CACHE_DIR)
    print(f"⏳ Loading {year} {race} (Race)...")
    session = fastf1.get_session(year, race, "R")
    session.load(telemetry=True, laps=True, weather=True)
    print(f"📍 {session.event['EventName']} — round {session.event['RoundNumber']}")
    return session


def build_driver_telemetry(session):
    """
    Per driver: native-resolution arrays on the shared session clock plus lap records.

    Returns (drivers, bounds) where drivers[code] holds raw numpy traces and metadata,
    and bounds is (min_x, max_x, min_y, max_y) over all cars.
    """
    drivers = {}
    min_x = min_y = np.inf
    max_x = max_y = -np.inf

    nums = session.drivers
    for i, num in enumerate(nums):
        sys.stdout.write(f"\r   driver {i + 1}/{len(nums)} ({num})   ")
        sys.stdout.flush()
        try:
            laps = session.laps.pick_drivers(num)
            if laps.empty:
                continue
            info = session.get_driver(num)
            tel = laps.get_telemetry()
            if not {"X", "Y", "SessionTime"}.issubset(tel.columns) or len(tel) < 2:
                continue

            t = _secs(tel["SessionTime"])
            x = tel["X"].to_numpy(dtype=float) / 10.0
            y = tel["Y"].to_numpy(dtype=float) / 10.0
            ok = np.isfinite(t) & np.isfinite(x) & np.isfinite(y)
            t, x, y = t[ok], x[ok], y[ok]
            order = np.argsort(t)
            t, x, y = t[order], x[order], y[order]
            if len(t) < 2:
                continue

            def chan(name, default=0.0):
                if name in tel.columns:
                    v = pd.to_numeric(tel[name], errors="coerce").to_numpy(dtype=float)
                    v = v[ok][order]
                    return np.nan_to_num(v, nan=default)
                return np.full(len(t), default)

            brake = chan("Brake")
            if np.nanmax(brake) <= 1.0:  # boolean brake -> percent
                brake = brake * 100.0

            color = info.get("TeamColor") or "CCCCCC"
            code = info.get("Abbreviation") or str(num)
            drivers[code] = {
                "num": str(info.get("DriverNumber", num)),
                "name": info.get("FullName") or code,
                "team": info.get("TeamName") or "",
                "color": "#" + str(color).lstrip("#"),
                "t": t,
                "x": x,
                "y": y,
                "dist": cumulative_distance(x, y),
                "speed": chan("Speed"),
                "throttle": chan("Throttle"),
                "brake": brake,
                "drs": chan("DRS"),
                "gear": chan("nGear"),
                "laps": _lap_records(laps),
            }
            min_x, max_x = min(min_x, x.min()), max(max_x, x.max())
            min_y, max_y = min(min_y, y.min()), max(max_y, y.max())
        except Exception as e:  # noqa: BLE001 - one bad driver shouldn't kill the export
            print(f"\n   ⚠️ skipped {num}: {e}")
            continue

    print("\n✅ telemetry assembled")
    if not drivers:
        sys.exit("❌ no driver data")
    return drivers, (float(min_x), float(max_x), float(min_y), float(max_y))


def _lap_records(laps):
    """Per-lap records: timing, sectors, tyre compound/stint, pit, position."""
    out = []
    for _, lap in laps.iterrows():
        comp = lap.get("Compound")
        out.append({
            "lap": int(lap["LapNumber"]) if pd.notna(lap.get("LapNumber")) else None,
            "t": _td_secs(lap.get("Time")),
            "lapTime": _td_secs(lap.get("LapTime")),
            "s1": _td_secs(lap.get("Sector1Time")),
            "s2": _td_secs(lap.get("Sector2Time")),
            "s3": _td_secs(lap.get("Sector3Time")),
            "compound": COMPOUND.get(str(comp).upper(), None) if pd.notna(comp) else None,
            "stint": int(lap["Stint"]) if pd.notna(lap.get("Stint")) else None,
            "pitIn": _td_secs(lap.get("PitInTime")) is not None,
            "pitOut": _td_secs(lap.get("PitOutTime")) is not None,
            "pos": int(lap["Position"]) if pd.notna(lap.get("Position")) else None,
        })
    return out


def build_frames(drivers, step):
    """Resample every driver onto a uniform time grid; quantize and slice to active range."""
    t0 = min(d["t"][0] for d in drivers.values())
    t1 = max(d["t"][-1] for d in drivers.values())
    grid = np.arange(t0, t1 + step, step)
    out = {}
    for code, d in drivers.items():
        f0, f1 = active_range(grid, d["t"][0], d["t"][-1])
        g = grid[f0:f1 + 1]
        out[code] = {
            "f0": f0,
            "x": _qi(resample(g, d["t"], d["x"])),
            "y": _qi(resample(g, d["t"], d["y"])),
            "dist": _qi(resample(g, d["t"], d["dist"])),
            "spd": _qi(resample(g, d["t"], d["speed"])),
            "thr": _qi(resample(g, d["t"], d["throttle"])),
            "brk": _qi(resample(g, d["t"], d["brake"])),
            "gear": _qi(resample(g, d["t"], d["gear"])),
            "drs": _qi(resample(g, d["t"], d["drs"])),
        }
    return {"step": step, "t0": round(float(t0), 3), "n": len(grid), "drivers": out}


def build_meta(session, drivers, bounds, year):
    fastest = session.laps.pick_fastest()
    racing_line, start_finish = [], None
    try:
        ft = fastest.get_telemetry()
        rx = (ft["X"].to_numpy(dtype=float) / 10.0)
        ry = (ft["Y"].to_numpy(dtype=float) / 10.0)
        # Downsample the racing line to ~600 points.
        keep = np.linspace(0, len(rx) - 1, min(600, len(rx))).astype(int)
        racing_line = [[int(rx[i]), int(ry[i])] for i in keep]
        start_finish = [int(rx[0]), int(ry[0])]
    except Exception:
        pass

    corners = []
    try:
        ci = session.get_circuit_info()
        for _, c in ci.corners.iterrows():
            corners.append({
                "n": int(c["Number"]),
                "letter": str(c.get("Letter", "") or ""),
                "x": int(float(c["X"]) / 10.0),
                "y": int(float(c["Y"]) / 10.0),
            })
    except Exception:
        pass

    drv_meta = [
        {"code": code, "num": d["num"], "name": d["name"],
         "team": d["team"], "color": d["color"]}
        for code, d in sorted(drivers.items(), key=lambda kv: kv[1]["num"])
    ]
    return {
        "year": year,
        "round": int(session.event["RoundNumber"]),
        "race": session.event["EventName"],
        "circuit": session.event.get("Location", ""),
        "country": session.event.get("Country", ""),
        "totalLaps": int(session.laps["LapNumber"].max()),
        "bounds": [round(b, 1) for b in bounds],
        "racingLine": racing_line,
        "startFinish": start_finish,
        "corners": corners,
        "drivers": drv_meta,
    }


def build_traces(session, drivers):
    """Per-driver fastest-lap channels vs track distance (for the Compare view)."""
    out = {}
    for code in drivers:
        try:
            lap = session.laps.pick_drivers(_num_for(drivers, code)).pick_fastest()
            tel = lap.get_telemetry()
            dist = tel["Distance"].to_numpy(dtype=float)
            if len(dist) < 10:
                continue
            grid = np.linspace(dist.min(), dist.max(), 400)

            def ch(name):
                v = pd.to_numeric(tel[name], errors="coerce").to_numpy(dtype=float)
                v = np.nan_to_num(v)
                return _qi(np.interp(grid, dist, v))

            brk = pd.to_numeric(tel["Brake"], errors="coerce").to_numpy(dtype=float)
            brk = np.nan_to_num(brk)
            if np.nanmax(brk) <= 1.0:
                brk = brk * 100.0
            out[code] = {
                "lapTime": _td_secs(lap.get("LapTime")),
                "dist": _qi(grid),
                "spd": ch("Speed"),
                "thr": ch("Throttle"),
                "brk": _qi(np.interp(grid, dist, brk)),
                "gear": ch("nGear"),
            }
        except Exception:
            continue
    return out


def build_mini_sectors(traces, color_map, n=20):
    """
    Split the lap into `n` equal-distance mini-sectors and find, from each
    driver's fastest lap, who is quickest through each one (time = ∫ dx / v).
    Returns one entry per sector with the owning driver and their team colour —
    the classic broadcast "purple-sector dominance" map.
    """
    band_times = [dict() for _ in range(n)]
    for code, tr in traces.items():
        dist, spd = tr["dist"], tr["spd"]
        if len(dist) < 2:
            continue
        span = dist[-1] - dist[0]
        if span <= 0:
            continue
        for i in range(len(dist) - 1):
            b = min(n - 1, int((dist[i] - dist[0]) / span * n))
            v = max(10.0, (spd[i] + spd[i + 1]) / 2) / 3.6
            band_times[b][code] = band_times[b].get(code, 0.0) + (dist[i + 1] - dist[i]) / v
    sectors = []
    for bt in band_times:
        if not bt:
            sectors.append({"owner": None, "color": "#888", "t": None})
            continue
        owner = min(bt, key=bt.get)
        sectors.append({"owner": owner, "color": color_map.get(owner, "#888"),
                        "t": round(bt[owner], 3)})
    return sectors


def _num_for(drivers, code):
    return drivers[code]["num"]


# Track-status codes (F1 timing feed) -> the categories the web app renders.
TRACK_STATUS = {
    "1": "GREEN", "2": "YELLOW", "4": "SC", "5": "RED", "6": "VSC", "7": "VSC",
}


def build_events(session, drivers):
    """
    Race control + weather + key moments, all on the shared session clock.

    - trackStatus: merged [tStart, tEnd, type] bands for SC / VSC / yellow / red.
    - weather: down-sampled air/track temp, rain flag and wind.
    - moments: clickable highlights (race start, SC/VSC/red, lead changes, the
      eventual fastest lap, and pit stops).
    """
    race_end = 0.0
    for d in drivers.values():
        for r in d["laps"]:
            if r["t"]:
                race_end = max(race_end, r["t"])

    # --- Track status bands ---
    bands = []
    try:
        ts = session.track_status
        rows = [(float(t.total_seconds()), TRACK_STATUS.get(str(s), "GREEN"))
                for t, s in zip(ts["Time"], ts["Status"])]
        rows.sort(key=lambda r: r[0])
        for i, (t, kind) in enumerate(rows):
            end = rows[i + 1][0] if i + 1 < len(rows) else race_end
            if end <= t:
                continue
            if bands and bands[-1]["type"] == kind and abs(bands[-1]["end"] - t) < 0.1:
                bands[-1]["end"] = end  # merge consecutive equal statuses
            else:
                bands.append({"start": round(t, 1), "end": round(end, 1), "type": kind})
    except Exception:
        pass
    status_bands = [b for b in bands if b["type"] != "GREEN"]

    # --- Weather samples ---
    weather = []
    try:
        wd = session.weather_data
        for _, w in wd.iterrows():
            weather.append({
                "t": round(float(w["Time"].total_seconds()), 1),
                "air": round(float(w["AirTemp"]), 1),
                "track": round(float(w["TrackTemp"]), 1),
                "rain": bool(w["Rainfall"]),
                "wind": round(float(w["WindSpeed"]), 1),
            })
    except Exception:
        pass

    # --- Key moments ---
    # Race start aligns with the start of telemetry (the seek bar's left edge).
    t_start = min((float(d["t"][0]) for d in drivers.values() if len(d["t"])),
                  default=0.0)
    moments = []
    if race_end > 0:
        moments.append({"t": round(t_start, 1), "type": "start", "label": "Race start"})
    for b in status_bands:
        if b["type"] in ("SC", "VSC", "RED"):
            label = {"SC": "Safety Car", "VSC": "Virtual Safety Car",
                     "RED": "Red flag"}[b["type"]]
            moments.append({"t": b["start"], "type": b["type"].lower(), "label": label})

    # Lead changes: when whoever holds P1 at the end of a lap changes.
    lead_by_lap = {}
    for code, d in drivers.items():
        for r in d["laps"]:
            if r["lap"] is not None and r["pos"] == 1 and r["t"] is not None:
                lead_by_lap[r["lap"]] = (code, r["t"])
    prev_leader = None
    for lap in sorted(lead_by_lap):
        code, t = lead_by_lap[lap]
        if prev_leader is not None and code != prev_leader:
            moments.append({"t": round(t, 1), "type": "lead",
                            "label": f"{code} leads", "driver": code})
        prev_leader = code

    # Eventual fastest lap of the race.
    fl = None
    for code, d in drivers.items():
        for r in d["laps"]:
            if r["lapTime"] and r["lapTime"] > 0 and (fl is None or r["lapTime"] < fl[2]):
                fl = (code, r["t"], r["lapTime"])
    if fl and fl[1]:
        m, s = divmod(fl[2], 60)
        moments.append({"t": round(fl[1], 1), "type": "fl",
                        "label": f"Fastest lap {fl[0]} {int(m)}:{s:06.3f}",
                        "driver": fl[0]})

    # Pit stops.
    for code, d in drivers.items():
        for r in d["laps"]:
            if r["pitIn"] and r["t"] is not None:
                moments.append({"t": round(r["t"], 1), "type": "pit",
                                "label": f"{code} pits", "driver": code})

    moments.sort(key=lambda m: m["t"])
    return {"raceEnd": round(race_end, 1), "trackStatus": status_bands,
            "weather": weather, "moments": moments}


def build_analytics(drivers):
    """Gap-to-leader per lap, position-by-lap, sector dominance, undercut flags."""
    laps_by_driver = {
        code: [{"lap": r["lap"], "t": r["t"], "pos": r["pos"]} for r in d["laps"]
               if r["lap"] is not None]
        for code, d in drivers.items()
    }
    gaps = lap_gap_to_leader(laps_by_driver)

    pos_by_lap = {}
    for code, d in drivers.items():
        pos_by_lap[code] = {r["lap"]: r["pos"] for r in d["laps"]
                            if r["lap"] is not None and r["pos"] is not None}

    # Tyre stints: contiguous lap ranges sharing a stint id / compound.
    stints_by_driver = {}
    for code, d in drivers.items():
        stints, cur = [], None
        for r in d["laps"]:
            if r["lap"] is None or r["compound"] is None:
                continue
            if cur and r["stint"] == cur["stint"] and r["compound"] == cur["compound"]:
                cur["lap_end"] = r["lap"]
            else:
                cur = {"compound": r["compound"], "stint": r["stint"],
                       "lap_start": r["lap"], "lap_end": r["lap"]}
                stints.append(cur)
        stints_by_driver[code] = [
            {"compound": s["compound"], "lapStart": s["lap_start"], "lapEnd": s["lap_end"]}
            for s in stints
        ]

    # Sector dominance: each driver's personal best per sector + who owns it overall.
    best_sectors = {}
    for code, d in drivers.items():
        best = {}
        for r in d["laps"]:
            for s in ("s1", "s2", "s3"):
                v = r[s]
                if v and v > 0 and (s not in best or v < best[s]):
                    best[s] = v
        best_sectors[code] = best
    owners = {}
    for s in ("s1", "s2", "s3"):
        cands = [(code, b[s]) for code, b in best_sectors.items() if s in b]
        if cands:
            owners[s] = min(cands, key=lambda kv: kv[1])[0]

    undercuts = detect_undercuts(
        {c: [{"compound": s["compound"], "lap_start": s["lapStart"],
              "lap_end": s["lapEnd"]} for s in st]
         for c, st in stints_by_driver.items()},
        pos_by_lap,
    )

    return {
        "gapToLeader": gaps,
        "positionByLap": {c: {str(k): v for k, v in p.items()} for c, p in pos_by_lap.items()},
        "stints": stints_by_driver,
        "sectorBest": {c: {k: round(v, 3) for k, v in b.items()} for c, b in best_sectors.items()},
        "sectorOwners": owners,
        "undercuts": undercuts,
    }


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, separators=(",", ":"))
    return os.path.getsize(path)


def update_manifest(meta):
    os.makedirs(WEB_DATA, exist_ok=True)
    path = os.path.join(WEB_DATA, "manifest.json")
    races = []
    if os.path.exists(path):
        with open(path) as f:
            races = json.load(f).get("races", [])
    entry = {
        "id": f"{meta['year']}-{meta['round']}",
        "year": meta["year"], "round": meta["round"],
        "race": meta["race"], "circuit": meta["circuit"],
        "country": meta["country"], "totalLaps": meta["totalLaps"],
        "drivers": len(meta["drivers"]),
    }
    races = [r for r in races if r["id"] != entry["id"]] + [entry]
    races.sort(key=lambda r: (r["year"], r["round"]))
    write_json(path, {"races": races})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--race", type=str, required=True)
    ap.add_argument("--step", type=float, default=0.5, help="frame grid step (s)")
    args = ap.parse_args()

    session = load_session(args.year, args.race)
    drivers, bounds = build_driver_telemetry(session)

    rnd = int(session.event["RoundNumber"])
    out_dir = os.path.join(WEB_DATA, str(args.year), str(rnd))

    meta = build_meta(session, drivers, bounds, args.year)
    traces = build_traces(session, drivers)
    meta["miniSectors"] = build_mini_sectors(
        traces, {d["code"]: d["color"] for d in meta["drivers"]})
    analytics = build_analytics(drivers)
    events = build_events(session, drivers)
    sizes = {
        "meta.json": write_json(os.path.join(out_dir, "meta.json"), meta),
        "frames.json": write_json(os.path.join(out_dir, "frames.json"),
                                   build_frames(drivers, args.step)),
        "laps.json": write_json(os.path.join(out_dir, "laps.json"),
                                 {c: d["laps"] for c, d in drivers.items()}),
        "traces.json": write_json(os.path.join(out_dir, "traces.json"), traces),
        "analytics.json": write_json(os.path.join(out_dir, "analytics.json"),
                                      analytics),
        "events.json": write_json(os.path.join(out_dir, "events.json"), events),
        "engineer.json": write_json(os.path.join(out_dir, "engineer.json"),
                                    build_engineer(drivers, meta["totalLaps"],
                                                   analytics, meta["drivers"], events)),
    }
    update_manifest(meta)

    print(f"\n📦 {out_dir}")
    for name, size in sizes.items():
        print(f"   {name:<16} {size / 1024:8.1f} KB")
    print(f"   TOTAL            {sum(sizes.values()) / 1024 / 1024:7.2f} MB")


if __name__ == "__main__":
    main()
