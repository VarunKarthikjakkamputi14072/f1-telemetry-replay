import numpy as np
import random
import time
from dtw import dtw_distance

def prepare_lap_signal(telemetry, lap_number, channels, n_points=500):
    df_lap = telemetry[telemetry["LapNumber"] == lap_number]
    if len(df_lap) < 10:
        return None
        
    cum_dist = df_lap["CumDist"].values
    if len(cum_dist) < 2 or cum_dist[-1] == cum_dist[0]:
        return None
        
    target_dist = np.linspace(cum_dist[0], cum_dist[-1], n_points)
    
    signals = {}
    for ch in channels:
        val = df_lap[ch].values
        # Handle constant values (e.g., Throttle = 1.0 the whole way or nan)
        std_val = np.nanstd(val)
        if std_val == 0 or np.isnan(std_val):
            norm_val = np.zeros_like(val)
        else:
            norm_val = (val - np.nanmean(val)) / std_val
            
        resampled = np.interp(target_dist, cum_dist, norm_val)
        signals[ch] = resampled
        
    return signals

def lap_similarity(tel_a, tel_b, lap_a, lap_b, channels):
    sig_a = prepare_lap_signal(tel_a, lap_a, channels)
    sig_b = prepare_lap_signal(tel_b, lap_b, channels)
    
    if sig_a is None or sig_b is None:
        return None
        
    total_dist = 0
    for ch in channels:
        dist, _ = dtw_distance(sig_a[ch], sig_b[ch], window=50)
        total_dist += dist
        
    return total_dist / len(channels)

def build_driver_fingerprint(telemetry_dict):
    drivers = list(telemetry_dict.keys())
    n_drivers = len(drivers)
    matrix = {d: {other: np.nan for other in drivers} for d in drivers}
    
    channels = ["Speed", "Throttle", "Brake"]
    
    # Identify valid clean laps per driver (not 0, not 1, not last)
    valid_laps = {}
    for d, df in telemetry_dict.items():
        if df.empty:
            valid_laps[d] = []
            continue
        laps = sorted(df["LapNumber"].unique())
        if len(laps) <= 3:
            valid_laps[d] = []
        else:
            # exclude first two and last lap
            valid_laps[d] = laps[2:-1]
            
    pairs = [(d1, d2) for i, d1 in enumerate(drivers) for d2 in drivers[i+1:]]
    
    start_time = time.time()
    max_pairs = 50
    if len(pairs) > max_pairs:
        random.shuffle(pairs)
        pairs = pairs[:max_pairs]
        print(f"⚠️ Sampling {max_pairs} driver pairs to maintain performance constraint.")
        
    for d1, d2 in pairs:
        laps_1 = valid_laps[d1]
        laps_2 = valid_laps[d2]
        
        if not laps_1 or not laps_2:
            continue
            
        # Sample up to 10 laps
        n_samples = min(10, len(laps_1), len(laps_2))
        
        # Take evenly spaced laps
        idx_1 = np.linspace(0, len(laps_1)-1, n_samples, dtype=int)
        idx_2 = np.linspace(0, len(laps_2)-1, n_samples, dtype=int)
        
        distances = []
        for i1, i2 in zip(idx_1, idx_2):
            lap_a = laps_1[i1]
            lap_b = laps_2[i2]
            
            d = lap_similarity(telemetry_dict[d1], telemetry_dict[d2], lap_a, lap_b, channels)
            if d is not None:
                distances.append(d)
                
        if distances:
            avg_dist = np.mean(distances)
            matrix[d1][d2] = avg_dist
            matrix[d2][d1] = avg_dist
            print(f"[{d1}] vs [{d2}]: {avg_dist:.4f}")
            
    return matrix
