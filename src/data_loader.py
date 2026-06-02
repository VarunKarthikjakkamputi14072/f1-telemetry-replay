import fastf1
import pandas as pd
import numpy as np
import warnings
import sys

warnings.filterwarnings("ignore", category=FutureWarning)


def _safe_col(telemetry, col, default=0):
    """Return column if present in telemetry, else a constant Series."""
    if col in telemetry.columns:
        return telemetry[col].ffill().fillna(default)
    return pd.Series(default, index=telemetry.index)


def _extract_sector_times(laps_df):
    """Build per-lap sector time records from the laps dataframe."""
    records = []
    for _, lap in laps_df.iterrows():
        lap_num = lap.get("LapNumber", 0)
        for sec_i in (1, 2, 3):
            col = f"Sector{sec_i}Time"
            val = lap.get(col, pd.NaT)
            if pd.notna(val):
                secs = val.total_seconds() if hasattr(val, "total_seconds") else float(val)
                records.append({"LapNumber": int(lap_num), "Sector": sec_i, "Time": secs})
    return records


def _extract_lap_times(laps_df):
    """Build per-lap time records."""
    records = []
    for _, lap in laps_df.iterrows():
        lap_num = lap.get("LapNumber", 0)
        lt = lap.get("LapTime", pd.NaT)
        if pd.notna(lt):
            secs = lt.total_seconds() if hasattr(lt, "total_seconds") else float(lt)
            records.append({"LapNumber": int(lap_num), "LapTime": secs})
    return records


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

    try:
        total_laps = int(session.laps["LapNumber"].max())
    except Exception:
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

            drv_details = session.get_driver(driver)
            color = drv_details.get("TeamColor", "CCCCCC")
            if not color or color == "":
                color = "CCCCCC"

            sector_times = _extract_sector_times(laps)
            lap_times = _extract_lap_times(laps)

            driver_info[driver] = {
                "Abbreviation": drv_details["Abbreviation"],
                "TeamColor": f"#{color}",
                "TeamName": drv_details["TeamName"],
                "SectorTimes": sector_times,
                "LapTimes": lap_times,
            }

            telemetry = laps.get_telemetry()

            required_cols = ["Time", "X", "Y"]
            if not all(col in telemetry.columns for col in required_cols):
                continue

            if "LapNumber" not in telemetry.columns:
                telemetry["LapNumber"] = 0
            else:
                telemetry["LapNumber"] = telemetry["LapNumber"].ffill().fillna(0)

            telemetry["Speed"] = _safe_col(telemetry, "Speed", 0)
            telemetry["DRS"] = _safe_col(telemetry, "DRS", 0)
            telemetry["Throttle"] = _safe_col(telemetry, "Throttle", 0)
            telemetry["Brake"] = _safe_col(telemetry, "Brake", 0)
            telemetry["nGear"] = _safe_col(telemetry, "nGear", 0)

            keep_cols = ["Time", "X", "Y", "LapNumber",
                         "Speed", "DRS", "Throttle", "Brake", "nGear"]
            telemetry = telemetry[keep_cols]

            telemetry = telemetry.dropna(subset=["Time", "X", "Y"])
            telemetry.sort_values(by="Time", inplace=True)

            if len(telemetry) < 2:
                continue

            telemetry["X"] = telemetry["X"] / 10.0
            telemetry["Y"] = telemetry["Y"] / 10.0

            telemetry["Time"] = telemetry["Time"].dt.total_seconds()
            telemetry.reset_index(drop=True, inplace=True)

            drivers_data[driver] = telemetry

        except Exception as e:
            print(f"\n⚠️ Warning: skipped driver {driver} due to error: {e}")
            continue

    print("\n✅ Telemetry processing complete.")

    if not drivers_data:
        print("\n❌ ERROR: No valid driver data could be loaded.")
        sys.exit(1)

    bounds = compute_bounds(drivers_data)
    timeline = build_global_timeline(drivers_data)

    return {
        "drivers": drivers_data,
        "track": {
            "bounds": bounds,
            "timeline": timeline,
        },
        "metadata": {
            "year": year,
            "race_name": session.event["EventName"],
            "session": session.name,
            "total_laps": total_laps,
            "driver_info": driver_info,
        },
    }


def compute_bounds(drivers_data):
    xs, ys = [], []
    for telemetry in drivers_data.values():
        if not telemetry.empty:
            xs.extend(telemetry["X"].values)
            ys.extend(telemetry["Y"].values)

    if not xs:
        return (0, 100, 0, 100)
    return min(xs), max(xs), min(ys), max(ys)


def build_global_timeline(drivers_data):
    times = set()
    for telemetry in drivers_data.values():
        if not telemetry.empty:
            times.update(telemetry["Time"].values)
    return sorted(list(times))
