"""
Tyre degradation model — estimates tyre health from stint data.

Uses a compound-specific exponential decay model fitted from actual session
lap times.  Falls back to tuned priors when data is sparse.
"""
import math
import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple

# Prior degradation rates (seconds-per-lap) and expected max stint lengths
_COMPOUND_PRIORS = {
    "SOFT":         {"deg": 0.065, "max_stint": 22, "warmup": 0.4},
    "MEDIUM":       {"deg": 0.042, "max_stint": 34, "warmup": 0.25},
    "HARD":         {"deg": 0.028, "max_stint": 50, "warmup": 0.15},
    "INTERMEDIATE": {"deg": 0.050, "max_stint": 30, "warmup": 0.35},
    "WET":          {"deg": 0.055, "max_stint": 25, "warmup": 0.30},
}

_COMPOUND_COLORS = {
    "SOFT": (220, 40, 40),
    "MEDIUM": (220, 190, 30),
    "HARD": (240, 240, 240),
    "INTERMEDIATE": (60, 180, 60),
    "WET": (60, 100, 220),
    "UNKNOWN": (150, 150, 150),
}


def compound_color(name: str) -> Tuple[int, int, int]:
    return _COMPOUND_COLORS.get(str(name).upper(), (150, 150, 150))


class TyreDegradationModel:
    """Per-compound exponential lap-time degradation model."""

    def __init__(self):
        self._profiles: Dict[str, dict] = {}
        self._fitted = False

    def fit(self, laps_df: pd.DataFrame) -> bool:
        """Fit degradation curves from session laps."""
        if laps_df is None or laps_df.empty:
            return False

        required = {"LapTime", "Compound", "TyreLife", "LapNumber"}
        if not required.issubset(set(laps_df.columns)):
            return False

        for compound in laps_df["Compound"].dropna().unique():
            cname = str(compound).upper()
            subset = laps_df[laps_df["Compound"] == compound].copy()
            subset = subset.dropna(subset=["LapTime", "TyreLife"])

            lap_secs = subset["LapTime"].apply(
                lambda v: v.total_seconds() if hasattr(v, "total_seconds") else float(v)
            )
            tyre_life = subset["TyreLife"].astype(float)

            valid = (lap_secs > 30) & (lap_secs < 300) & (tyre_life > 0)
            lap_secs = lap_secs[valid].values
            tyre_life = tyre_life[valid].values

            prior = _COMPOUND_PRIORS.get(cname, _COMPOUND_PRIORS["MEDIUM"])

            if len(lap_secs) < 5:
                self._profiles[cname] = dict(prior)
                continue

            # FIX 2: Filter outlier laps (SC/VSC/formation) before fitting.
            # Keep only laps within 110% of the median lap time.
            median_lap = float(np.median(lap_secs))
            clean_mask = lap_secs <= median_lap * 1.10
            lap_secs_clean = lap_secs[clean_mask]
            tyre_life_clean = tyre_life[clean_mask]

            if len(lap_secs_clean) < 3:
                # Not enough clean laps — fall back to prior
                self._profiles[cname] = dict(prior)
                continue

            try:
                coeffs = np.polyfit(tyre_life_clean, lap_secs_clean, 1)
                deg_rate = max(0.005, float(coeffs[0]))
            except Exception:
                deg_rate = prior["deg"]

            # Cap deg_rate at 3× the prior to prevent SC-corrupted fits
            deg_rate = min(deg_rate, prior["deg"] * 3.0)

            max_stint = int(tyre_life_clean.max()) if len(tyre_life_clean) > 0 else prior["max_stint"]

            self._profiles[cname] = {
                "deg": deg_rate,
                "max_stint": max(max_stint, 5),
                "warmup": prior["warmup"],
            }

        # Ensure all compounds have a profile
        for cname, prior in _COMPOUND_PRIORS.items():
            if cname not in self._profiles:
                self._profiles[cname] = dict(prior)

        self._fitted = True
        return True

    def get_health(self, compound: str, laps_on_tyre: int) -> dict:
        """Return health info for a given compound and stint age."""
        cname = str(compound).upper().strip()
        profile = self._profiles.get(
            cname, _COMPOUND_PRIORS.get(cname, _COMPOUND_PRIORS["MEDIUM"])
        )

        deg = profile["deg"]
        max_stint = profile["max_stint"]
        warmup = profile["warmup"]

        age = max(0, laps_on_tyre)

        # FIX 1: Pure exponential decay only.
        # k is tuned so that health reaches ~20% at max_stint.
        # Solving: 0.20 = exp(-k * max_stint)  →  k = ln(5) / max_stint
        k = math.log(5.0) / max(max_stint, 1)
        health = 100.0 * math.exp(-k * age)
        health = max(0.0, min(100.0, health))

        # Warmup penalty: first 2 laps cost extra time (cold tyres)
        expected_delta = deg * age
        if age <= 2:
            expected_delta += warmup * (1.0 - age / 2.0)

        # FIX 3: Single cliff condition — don't fire from two paths
        cliff_warning = age >= max_stint * 0.82   # ~82% of max stint

        return {
            "health": int(round(health)),
            "deg_rate": round(deg, 4),
            "expected_delta": round(expected_delta, 2),
            "cliff_warning": cliff_warning,
            "compound": cname,
            "laps_on_tyre": age,
        }

    @property
    def fitted(self) -> bool:
        return self._fitted

    @property
    def profiles(self) -> Dict[str, dict]:
        return dict(self._profiles)
