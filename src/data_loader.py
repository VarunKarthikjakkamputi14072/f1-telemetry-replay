import fastf1
import pandas as pd


def load_race(year: int, race_name: str):
    fastf1.Cache.enable_cache("cache")

    session = fastf1.get_session(year, race_name, "R")
    session.load()

    drivers_data = {}

    for driver in session.drivers:
        laps = session.laps.pick_driver(driver)
        if laps.empty:
            continue

        telemetry = laps.get_telemetry()
        telemetry = telemetry[["Time", "X", "Y"]].dropna()

        telemetry["Time"] = telemetry["Time"].dt.total_seconds()
        telemetry.reset_index(drop=True, inplace=True)

        drivers_data[driver] = telemetry

    bounds = compute_bounds(drivers_data)
    timeline = build_global_timeline(drivers_data)

    return drivers_data, bounds, timeline


def compute_bounds(drivers_data):
    xs, ys = [], []

    for telemetry in drivers_data.values():
        xs.extend(telemetry["X"].values)
        ys.extend(telemetry["Y"].values)

    return min(xs), max(xs), min(ys), max(ys)


def build_global_timeline(drivers_data):
    times = []

    for telemetry in drivers_data.values():
        times.extend(telemetry["Time"].values)

    times = sorted(set(times))
    return times

