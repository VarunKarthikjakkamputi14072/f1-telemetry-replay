import fastf1
import pandas as pd
import warnings
import sys
import numpy as np

from similarity import build_driver_fingerprint
from tyre_model import TyreDegradationModel

warnings.filterwarnings("ignore", category=FutureWarning)


def extract_track_statuses(session):
    """Parse session track status into a timeline of status periods."""
    statuses = []
    try:
        ts_df = session.track_status
        if ts_df is None or ts_df.empty:
            return statuses
        for _, row in ts_df.iterrows():
            t = seconds_from_timedelta(row.get("Time"))
            status_code = str(row.get("Status", "1"))
            msg = str(row.get("Message", ""))
            if t is not None:
                statuses.append({"time": t, "status": status_code, "message": msg})
    except Exception:
        pass
    statuses.sort(key=lambda s: s["time"])
    return statuses


def extract_race_control_messages(session):
    """Parse race control messages (flags, penalties, SC, DRS)."""
    messages = []
    try:
        rc = getattr(session, "race_control_messages", None)
        if rc is None or rc.empty:
            return messages
        for _, row in rc.iterrows():
            t = seconds_from_timedelta(row.get("Time"))
            if t is None:
                continue
            messages.append({
                "time": t,
                "category": str(row.get("Category", "")),
                "message": str(row.get("Message", "")),
                "flag": str(row.get("Flag", "")),
                "scope": str(row.get("Scope", "")),
                "sector": str(row.get("Sector", "")),
                "driver": str(row.get("RacingNumber", "")),
            })
    except Exception:
        pass
    messages.sort(key=lambda m: m["time"])
    return messages


def extract_weather_timeline(session, global_timeline):
    """Resample weather data onto the replay timeline."""
    weather = []
    try:
        wdf = getattr(session, "weather_data", None)
        if wdf is None or wdf.empty:
            return weather
        w_times = wdf["Time"].dt.total_seconds().values
        if len(w_times) < 2:
            return weather
        order = np.argsort(w_times)
        w_times = w_times[order]
        cols = {}
        for col in ["AirTemp", "TrackTemp", "Humidity", "Pressure",
                     "WindSpeed", "WindDirection", "Rainfall"]:
            if col in wdf.columns:
                vals = pd.to_numeric(wdf[col], errors="coerce").fillna(0).values[order]
                cols[col] = vals
        tl = np.array(global_timeline)
        resampled = {}
        for col, vals in cols.items():
            resampled[col] = np.interp(tl, w_times, vals)
        for i, t in enumerate(tl):
            entry = {"time": float(t)}
            for col in resampled:
                entry[col] = float(resampled[col][i])
            weather.append(entry)
    except Exception as e:
        print(f"Warning: Weather data processing failed: {e}")
    return weather

def seconds_from_timedelta(value):
    if value is None or pd.isna(value):
        return None
    if hasattr(value, "total_seconds"):
        return value.total_seconds()
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def adaptive_dropout_threshold(dists: np.ndarray) -> float:
    valid = dists[dists > 0]
    if len(valid) == 0: return 150.0
    median = np.median(valid)
    return max(150.0, float(median * 3.0))

def compute_lateral_g(df: pd.DataFrame) -> pd.Series:
    if "Time" not in df.columns or "X" not in df.columns or "Y" not in df.columns:
        return pd.Series(0, index=df.index)
    dt = df["Time"].diff().dt.total_seconds().replace(0, np.nan)
    vx = df["X"].diff() / dt
    vy = df["Y"].diff() / dt
    ax = vx.diff() / dt
    ay = vy.diff() / dt
    speed_sq = vx**2 + vy**2
    lateral_g = (vx * ay - vy * ax).abs() / speed_sq.replace(0, np.nan) / 9.81
    return lateral_g.fillna(0)

def compute_overall_sector_bests(laps):
    sector_bests = {}
    for sector in (1, 2, 3):
        col = f"Sector{sector}Time"
        if col not in laps.columns:
            continue

        best = None
        for value in laps[col].dropna():
            seconds = seconds_from_timedelta(value)
            if seconds is not None and (best is None or seconds < best):
                best = seconds

        if best is not None:
            sector_bests[sector] = best

    return sector_bests


def build_sector_events(laps, overall_sector_bests):
    events = []
    personal_bests = {}

    for _, lap in laps.sort_values(by="LapNumber").iterrows():
        lap_number = int(lap["LapNumber"]) if not pd.isna(lap.get("LapNumber")) else 0

        for sector in (1, 2, 3):
            sector_col = f"Sector{sector}Time"
            session_col = f"Sector{sector}SessionTime"
            if sector_col not in laps.columns or session_col not in laps.columns:
                continue

            sector_seconds = seconds_from_timedelta(lap.get(sector_col))
            event_time = seconds_from_timedelta(lap.get(session_col))
            if sector_seconds is None or event_time is None:
                continue

            previous_personal = personal_bests.get(sector)
            is_personal_best = previous_personal is None or sector_seconds < previous_personal
            if is_personal_best:
                personal_bests[sector] = sector_seconds

            overall_best = overall_sector_bests.get(sector)
            is_overall_best = overall_best is not None and abs(sector_seconds - overall_best) < 0.001

            if is_overall_best:
                event_type = "overall_best"
            elif is_personal_best:
                event_type = "personal_best"
            else:
                event_type = "normal"

            events.append({
                "time": event_time,
                "sector": sector,
                "sector_time": sector_seconds,
                "lap_number": lap_number,
                "type": event_type
            })

    return sorted(events, key=lambda event: event["time"])


def build_pit_windows(laps):
    if "PitInTime" not in laps.columns or "PitOutTime" not in laps.columns:
        return []

    pit_entries = []
    pit_exits = []
    for _, lap in laps.iterrows():
        pit_in = seconds_from_timedelta(lap.get("PitInTime"))
        pit_out = seconds_from_timedelta(lap.get("PitOutTime"))
        if pit_in is not None:
            pit_entries.append(pit_in)
        if pit_out is not None:
            pit_exits.append(pit_out)

    pit_entries.sort()
    pit_exits.sort()
    windows = []
    exit_idx = 0
    for pit_in in pit_entries:
        while exit_idx < len(pit_exits) and pit_exits[exit_idx] <= pit_in:
            exit_idx += 1

        pit_out = pit_exits[exit_idx] if exit_idx < len(pit_exits) else pit_in + 90
        windows.append({"start": pit_in, "end": pit_out})
        exit_idx += 1

    return windows


def build_lap_events(laps):
    if "LapTime" not in laps.columns or "Time" not in laps.columns:
        return []

    events = []
    for _, lap in laps.sort_values(by="LapNumber").iterrows():
        lap_time = seconds_from_timedelta(lap.get("LapTime"))
        event_time = seconds_from_timedelta(lap.get("Time"))
        if lap_time is None or event_time is None:
            continue

        lap_number = int(lap["LapNumber"]) if not pd.isna(lap.get("LapNumber")) else 0
        events.append({
            "time": event_time,
            "lap_time": lap_time,
            "lap_number": lap_number
        })

    return events


def load_race(year: int, race_name: str):
    """
    Loads F1 telemetry data for a specific year and race.
    Returns a structured dictionary containing drivers, track data, and metadata.
    """
    print(f"⏳ Initializing FastF1 for {year} {race_name}...")
    fastf1.Cache.enable_cache("cache")

    try:
        session = fastf1.get_session(year, race_name, "R")
        print(f"📍 Found Session: {session.event['EventName']} - {session.name}")
    except Exception as e:
        print(f"❌ Could not find race session: {e}")
        sys.exit(1)

    print("📥 Downloading telemetry data (this may take a minute)...")
    try:
        session.load(telemetry=True, laps=True, weather=True)
    except Exception as e:
        print(f"❌ Error downloading data: {e}")
        sys.exit(1)

    print("⚙️ Processing driver telemetry...")
    drivers_data = {}
    driver_info = {}
    overall_sector_bests = compute_overall_sector_bests(session.laps)

    # Calculate official total laps
    try:
        total_laps = int(session.laps["LapNumber"].max())
    except Exception: # Fixed bare except
        total_laps = 0

    drivers_list = session.drivers
    total_drivers = len(drivers_list)

    for i, driver in enumerate(drivers_list):
        sys.stdout.write(f"\r   Processing driver {i+1}/{total_drivers} ({driver})")
        sys.stdout.flush()

        try:
            laps = session.laps.pick_drivers(driver)
            if laps.empty:
                continue

            # Extract Metadata
            drv_details = session.get_driver(driver)
            color = drv_details.get("TeamColor", "CCCCCC")
            if not color or color == "": color = "CCCCCC"

            best_lap_time = None
            best_lap_number = None
            if "LapTime" in laps.columns:
                valid_laps = laps.dropna(subset=["LapTime"])
                if not valid_laps.empty:
                    best_lap = valid_laps.loc[valid_laps["LapTime"].idxmin()]
                    best_lap_time = best_lap["LapTime"].total_seconds()
                    best_lap_number = int(best_lap["LapNumber"])

            sector_events = build_sector_events(laps, overall_sector_bests)
            pit_windows = build_pit_windows(laps)
            lap_events = build_lap_events(laps)

            lap_stints = {}
            if "Compound" in laps.columns and "TyreLife" in laps.columns:
                prev_compound = None
                stint_start_lap = 1
                for _, lap_row in laps.iterrows():
                    lap_num = int(lap_row.get("LapNumber", 0)) if not pd.isna(lap_row.get("LapNumber")) else 0
                    if not pd.isna(lap_row.get("Compound")):
                        compound = str(lap_row["Compound"])
                        tyre_life_val = float(lap_row.get("TyreLife", 0))
                        
                        if tyre_life_val == 1 or prev_compound != compound:
                            stint_start_lap = lap_num
                            
                        lap_stints[lap_num] = {
                            "Compound": compound,
                            "TyreLife": tyre_life_val,
                            "StintStartLap": stint_start_lap
                        }
                        prev_compound = compound

            driver_info[driver] = {
                "Abbreviation": drv_details["Abbreviation"],
                "TeamColor": f"#{color}",
                "TeamName": drv_details["TeamName"],
                "BestLapTime": best_lap_time,
                "BestLapNumber": best_lap_number,
                "SectorEvents": sector_events,
                "PitWindows": pit_windows,
                "LapEvents": lap_events,
                "LapStints": lap_stints
            }

            # Extract Telemetry
            telemetry = laps.get_telemetry()

            # --- ROBUST DATA CLEANING ---
            # 1. Ensure columns exist
            required_cols = ["Time", "X", "Y"]
            if not all(col in telemetry.columns for col in required_cols):
                # print(f" [Skipping {driver}: Missing columns]")
                continue

            # 2. Handle LapNumber (Fill missing with 0 or previous)
            if "LapNumber" not in telemetry.columns:
                telemetry["LapNumber"] = 0
            else:
                telemetry["LapNumber"] = telemetry["LapNumber"].ffill().fillna(0)

            # 3. Keep optional telemetry when FastF1 exposes it. These power the
            # replay overlays while staying safe for older/incomplete sessions.
            optional_defaults = {
                "Speed": 0,
                "Throttle": 0,
                "Brake": 0,
                "nGear": 0,
                "DRS": 0
            }
            for col, default in optional_defaults.items():
                if col not in telemetry.columns:
                    telemetry[col] = default

            telemetry = telemetry[[
                "Time", "X", "Y", "LapNumber",
                "Speed", "Throttle", "Brake", "nGear", "DRS"
            ]]

            # 4. Drop ONLY if coordinates/time are missing (Keep LapNumber even if 0)
            telemetry = telemetry.dropna(subset=["Time", "X", "Y"])

            for col, default in optional_defaults.items():
                telemetry[col] = pd.to_numeric(telemetry[col], errors="coerce")
                telemetry[col] = telemetry[col].ffill().bfill().fillna(default)

            # FIX 4: Sort by Time to ensure linear progression
            telemetry.sort_values(by="Time", inplace=True)

            # FIX 9: Handle datasets with insufficient data for interpolation
            if len(telemetry) < 2:
                continue

            # UNIT FIX: Convert Decimeters to Meters
            telemetry["X"] = telemetry["X"] / 10.0
            telemetry["Y"] = telemetry["Y"] / 10.0
            
            telemetry["LateralG"] = compute_lateral_g(telemetry)

            # Normalize Time
            telemetry["Time"] = telemetry["Time"].dt.total_seconds()
            telemetry.reset_index(drop=True, inplace=True)

            drivers_data[driver] = telemetry

        except Exception as e:
            print(f"\n⚠️ Warning: skipped driver {driver} due to error: {e}")
            continue

    print("\n✅ Telemetry processing complete.")

    if not drivers_data:
        print("\n❌ ERROR: No valid driver data could be loaded. The session might be empty or incompatible.")
        sys.exit(1)

    # Compute CumDist for all drivers (needed for DTW resampling and replay)
    for drv, df in drivers_data.items():
        dx = np.diff(df["X"].values, prepend=df["X"].values[0])
        dy = np.diff(df["Y"].values, prepend=df["Y"].values[0])
        dists = np.hypot(dx, dy)
        
        # --- ADAPTIVE DROPOUT GUARD ---
        threshold = adaptive_dropout_threshold(dists)
        dists[dists > threshold] = 0
        df["CumDist"] = np.cumsum(dists)

    print("⚙️ Computing driver similarity matrix...")
    similarity_matrix = build_driver_fingerprint(drivers_data)

    bounds = compute_bounds(drivers_data)
    timeline = build_global_timeline(drivers_data)

    fastest_driver = None
    fastest_lap_time = None
    for driver, info in driver_info.items():
        lap_time = info.get("BestLapTime")
        if lap_time is not None and (fastest_lap_time is None or lap_time < fastest_lap_time):
            fastest_driver = driver
            fastest_lap_time = lap_time

    # --- TRACK STATUS, RACE CONTROL, WEATHER ---
    print("Extracting track status & race control data...")
    track_statuses = extract_track_statuses(session)
    rc_messages = extract_race_control_messages(session)
    weather_timeline = extract_weather_timeline(session, timeline)

    # --- TYRE DEGRADATION MODEL ---
    tyre_deg_model = TyreDegradationModel()
    try:
        if session.laps is not None and not session.laps.empty:
            tyre_deg_model.fit(session.laps)
            if tyre_deg_model.fitted:
                print("Tyre degradation model fitted successfully")
                for cname, prof in tyre_deg_model.profiles.items():
                    print(f"  {cname}: {prof['deg']:.4f} s/lap, max stint ~{prof['max_stint']} laps")
    except Exception as e:
        print(f"Tyre model fitting skipped: {e}")

    # --- SESSION INFO ---
    session_info = {
        "event_name": session.event.get("EventName", ""),
        "circuit": session.event.get("Location", ""),
        "country": session.event.get("Country", ""),
        "date": str(session.event.get("EventDate", "")),
        "round": session.event.get("RoundNumber", ""),
    }

    return {
        "drivers": drivers_data,
        "track": {
            "bounds": bounds,
            "timeline": timeline
        },
        "similarity": similarity_matrix,
        "track_statuses": track_statuses,
        "race_control": rc_messages,
        "weather": weather_timeline,
        "tyre_model": tyre_deg_model,
        "metadata": {
            "year": year,
            "race_name": session.event["EventName"],
            "session": session.name,
            "total_laps": total_laps,
            "driver_info": driver_info,
            "fastest_driver": fastest_driver,
            "fastest_lap_time": fastest_lap_time,
            "session_info": session_info,
        }
    }

def compute_bounds(drivers_data):
    xs, ys = [], []
    for telemetry in drivers_data.values():
        if not telemetry.empty:
            xs.extend(telemetry["X"].values)
            ys.extend(telemetry["Y"].values)

    if not xs: return (0, 100, 0, 100)
    return min(xs), max(xs), min(ys), max(ys)

def build_global_timeline(drivers_data):
    times = set()
    for telemetry in drivers_data.values():
        if not telemetry.empty:
            times.update(telemetry["Time"].values)
    return sorted(list(times))
