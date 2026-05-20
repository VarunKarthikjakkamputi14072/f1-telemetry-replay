import fastf1
import pandas as pd
import warnings
import sys

# Suppress technical warnings for a cleaner console
warnings.filterwarnings("ignore", category=FutureWarning)

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
        session.load(telemetry=True, laps=True, weather=False)
    except Exception as e:
        print(f"❌ Error downloading data: {e}")
        sys.exit(1)

    print("⚙️ Processing driver telemetry...")
    drivers_data = {}
    driver_info = {}

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

            driver_info[driver] = {
                "Abbreviation": drv_details["Abbreviation"],
                "TeamColor": f"#{color}",
                "TeamName": drv_details["TeamName"],
                "BestLapTime": best_lap_time,
                "BestLapNumber": best_lap_number
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

    bounds = compute_bounds(drivers_data)
    timeline = build_global_timeline(drivers_data)

    fastest_driver = None
    fastest_lap_time = None
    for driver, info in driver_info.items():
        lap_time = info.get("BestLapTime")
        if lap_time is not None and (fastest_lap_time is None or lap_time < fastest_lap_time):
            fastest_driver = driver
            fastest_lap_time = lap_time

    return {
        "drivers": drivers_data,
        "track": {
            "bounds": bounds,
            "timeline": timeline
        },
        "metadata": {
            "year": year,
            "race_name": session.event["EventName"],
            "session": session.name,
            "total_laps": total_laps,
            "driver_info": driver_info,
            "fastest_driver": fastest_driver,
            "fastest_lap_time": fastest_lap_time
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
