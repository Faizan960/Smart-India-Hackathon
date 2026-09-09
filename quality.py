"""
Data-quality gate — runs before anomaly detection proper.

Flags structural data problems (missing, duplicated timestamps, frozen runs,
out-of-range values) separately from statistical/behavioral anomalies, since
these need different handling (e.g. a dropout should not be fed into a
z-score detector as if it were a real reading of zero).
"""

import numpy as np
import pandas as pd

from data_gen import BOUNDS

SENSOR_COLS = ["temperature_c", "pressure_hpa", "humidity_pct"]


def run_quality_gate(df: pd.DataFrame, freeze_min_run: int = 6) -> pd.DataFrame:
    """Adds quality flag columns. Does not modify the sensor values themselves."""
    df = df.sort_values(["station_id", "timestamp"]).reset_index(drop=True)

    df["q_missing"] = df[SENSOR_COLS].isna().any(axis=1)
    df["q_duplicate_ts"] = df.duplicated(subset=["station_id", "timestamp"], keep="first")

    for col in SENSOR_COLS:
        lo, hi = BOUNDS[col]
        df[f"q_out_of_range_{col}"] = (df[col] < lo) | (df[col] > hi)

    df["q_out_of_range"] = df[[f"q_out_of_range_{c}" for c in SENSOR_COLS]].any(axis=1)

    df["q_frozen"] = False
    for station, g in df.groupby("station_id"):
        for col in SENSOR_COLS:
            frozen = _frozen_runs(g[col].values, freeze_min_run)
            df.loc[g.index, "q_frozen"] = df.loc[g.index, "q_frozen"].values | frozen

    df["q_any_flag"] = df[["q_missing", "q_duplicate_ts", "q_out_of_range", "q_frozen"]].any(axis=1)
    return df


def _frozen_runs(values: np.ndarray, min_run: int) -> np.ndarray:
    """Mark points that are part of a run of >= min_run consecutive identical values
    (a sensor reporting the exact same float repeatedly almost never happens naturally)."""
    flags = np.zeros(len(values), dtype=bool)
    n = len(values)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and _same(values[j], values[j + 1]):
            j += 1
        run_len = j - i + 1
        if run_len >= min_run:
            flags[i : j + 1] = True
        i = j + 1
    return flags


def _same(a, b, tol=1e-9):
    if np.isnan(a) or np.isnan(b):
        return False
    return abs(a - b) < tol
