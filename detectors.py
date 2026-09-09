"""
Hybrid anomaly engine: three independent detectors whose signals get fused
downstream (fusion.py). Keeping them independent is what lets us later
explain *why* something was flagged (which detector fired) rather than
just handing back an opaque anomaly score.

1. Statistical: rolling z-score against a trailing window (catches spikes)
2. Temporal: short-vs-long rolling mean divergence (catches drift)
3. Multivariate consistency: residual from an expected sensor relationship
   (catches cross-sensor inconsistency that no single-sensor check would see)
"""

import numpy as np
import pandas as pd

SENSOR_COLS = ["temperature_c", "pressure_hpa", "humidity_pct"]


def statistical_zscore(df: pd.DataFrame, window: int = 24, z_thresh: float = 4.0) -> pd.DataFrame:
    """Rolling z-score per sensor per station. window=24 points * 5min = 2 hours."""
    out = df.copy()
    for col in SENSOR_COLS:
        z_col = f"z_{col}"
        out[z_col] = 0.0
        for station, g in out.groupby("station_id"):
            vals = g[col]
            roll_mean = vals.rolling(window, min_periods=window // 2).mean()
            roll_std = vals.rolling(window, min_periods=window // 2).std().replace(0, np.nan)
            z = (vals - roll_mean) / roll_std
            out.loc[g.index, z_col] = z.fillna(0)
        out[f"flag_stat_{col}"] = out[z_col].abs() > z_thresh
    out["flag_statistical"] = out[[f"flag_stat_{c}" for c in SENSOR_COLS]].any(axis=1)
    return out


def temporal_drift(
    df: pd.DataFrame, short_window: int = 12, long_window: int = 192, drift_thresh: float = 2.1
) -> pd.DataFrame:
    """Divergence between a short-term rolling mean and a long-term baseline mean.
    A sudden spike moves the short window a lot but not the long one (statistical
    detector handles that). A slow drift moves the short window gradually away from
    a long, stable baseline -- that's what this detector is tuned to catch."""
    out = df.copy()
    for col in SENSOR_COLS:
        d_col = f"drift_{col}"
        out[d_col] = 0.0
        for station, g in out.groupby("station_id"):
            vals = g[col]
            short_mean = vals.rolling(short_window, min_periods=short_window // 2).mean()
            long_mean = vals.rolling(long_window, min_periods=long_window // 2).mean()
            long_std = vals.rolling(long_window, min_periods=long_window // 2).std().replace(0, np.nan)
            divergence = (short_mean - long_mean) / long_std
            out.loc[g.index, d_col] = divergence.fillna(0)
        out[f"flag_drift_{col}"] = out[d_col].abs() > drift_thresh
    out["flag_temporal"] = out[[f"flag_drift_{c}" for c in SENSOR_COLS]].any(axis=1)
    return out


def multivariate_consistency(df: pd.DataFrame, resid_thresh: float = 2.5) -> pd.DataFrame:
    """Expected relationship: humidity should move roughly opposite to temperature
    deviation from station mean (a simple physical prior — warmer air holds more
    moisture capacity, so relative humidity tends to fall as temperature rises,
    all else equal). Large residual from this expected relationship = a reading
    combination that doesn't make physical sense, even if each sensor is
    individually "in range"."""
    out = df.copy()
    out["mv_residual"] = 0.0
    for station, g in out.groupby("station_id"):
        temp_dev = g["temperature_c"] - g["temperature_c"].rolling(96, min_periods=20).mean()
        expected_humidity_dev = -1.4 * temp_dev
        actual_humidity_dev = g["humidity_pct"] - g["humidity_pct"].rolling(96, min_periods=20).mean()
        residual = actual_humidity_dev - expected_humidity_dev
        resid_z = (residual - residual.rolling(96, min_periods=20).mean()) / residual.rolling(
            96, min_periods=20
        ).std().replace(0, np.nan)
        out.loc[g.index, "mv_residual"] = resid_z.fillna(0)
    out["flag_multivariate"] = out["mv_residual"].abs() > resid_thresh
    return out


def run_all_detectors(df: pd.DataFrame) -> pd.DataFrame:
    df = statistical_zscore(df)
    df = temporal_drift(df)
    df = multivariate_consistency(df)
    return df
