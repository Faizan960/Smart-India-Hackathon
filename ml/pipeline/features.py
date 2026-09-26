"""Interval-aware feature engineering (spec sections 7, 8, 9, 10).

NOAA sampling is irregular (3-hourly synoptic at some stations, half-hourly METAR
at others, with gaps and duplicates already collapsed upstream). Every temporal
feature is therefore TIME-based, never fixed-sample-count based: rolling windows
are wall-clock ('3h', '24h') and rates are per-hour, so the same code behaves
correctly regardless of a station's cadence.

Feature groups:
  * raw sensors                      temperature, humidity, pressure
  * cyclical time                    hour_sin/cos, month_sin/cos
  * thermodynamic (physics.py)       vpd, es_hpa, dew_point_calc, thermo_*
  * baseline deviation (baseline.py) <sensor>_dev_baseline (robust z-scores)
  * rolling stats (time windows)     <sensor>_roll_mean/std_<win>
  * rate-of-change (per hour)        <sensor>_rate, dt_hours
  * pressure tendency                pressure_change_<win>

Nothing here decides anomalies; it only produces numeric evidence.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .baseline import BASELINE_COLS, DEV_COLS, deviation_features
from .config import CORE_SENSORS, DEFAULT_CONFIG
from .physics import thermodynamic_features
from .preprocessing import infer_sampling_seconds

PFX = {"temperature": "temp", "humidity": "humidity", "pressure": "pressure"}


def _cyclical_time(out: pd.DataFrame) -> pd.DataFrame:
    hour = out["timestamp"].dt.hour + out["timestamp"].dt.minute / 60.0
    month = out["timestamp"].dt.month
    out["hour_sin"] = np.sin(2 * np.pi * hour / 24.0)
    out["hour_cos"] = np.cos(2 * np.pi * hour / 24.0)
    out["month_sin"] = np.sin(2 * np.pi * month / 12.0)
    out["month_cos"] = np.cos(2 * np.pi * month / 12.0)
    return out


def _tendency(g: pd.DataFrame, col: str, hours: float) -> np.ndarray:
    """value(t) - value(t - hours), using the nearest real reading to t - hours
    (within +/- half the window). NaN where no such reading exists."""
    base = g[["timestamp", col]].dropna(subset=[col])
    now = g[col].to_numpy(dtype=float)
    if base.empty:
        return np.full(len(g), np.nan)
    target = pd.DataFrame({"t": g["timestamp"] - pd.Timedelta(hours=hours)})
    target = target.reset_index()  # keep original row order in 'index'
    m = pd.merge_asof(
        target.sort_values("t"),
        base.rename(columns={"timestamp": "bt", col: "past"}).sort_values("bt"),
        left_on="t", right_on="bt", direction="nearest",
        tolerance=pd.Timedelta(hours=hours * 0.5),
    )
    past = m.sort_values("index")["past"].to_numpy(dtype=float)
    return now - past


def _station_temporal(g: pd.DataFrame, config) -> pd.DataFrame:
    """Rate-of-change, time-based rolling stats and pressure tendency for one
    station. ``g`` must be sorted by timestamp with a clean RangeIndex."""
    interval_s = infer_sampling_seconds(g["timestamp"])
    dt_h = g["timestamp"].diff().dt.total_seconds() / 3600.0
    g["dt_hours"] = dt_h

    for sensor in CORE_SENSORS:
        g[f"{PFX[sensor]}_rate"] = g[sensor].diff() / dt_h

    gi = g.set_index("timestamp")
    for win in config.rolling_windows:
        win_s = pd.Timedelta(win).total_seconds()
        expected = win_s / interval_s if interval_s and np.isfinite(interval_s) and interval_s > 0 else 1.0
        min_p = max(2, int(config.min_periods_frac * expected))
        roll = gi[list(CORE_SENSORS)].rolling(win, min_periods=min_p)
        mean, std = roll.mean(), roll.std()
        for sensor in CORE_SENSORS:
            g[f"{PFX[sensor]}_roll_mean_{win}"] = mean[sensor].to_numpy()
            g[f"{PFX[sensor]}_roll_std_{win}"] = std[sensor].to_numpy()

    for win in config.pressure_tendency_windows:
        hours = pd.Timedelta(win).total_seconds() / 3600.0
        g[f"pressure_change_{win}"] = _tendency(g, "pressure", hours)
    return g


def build_features(df: pd.DataFrame, baselines=None, config=None) -> pd.DataFrame:
    """Produce the full evidence-feature frame (rows aligned to the input, sorted
    by station then time). ``baselines`` (from baseline.compute_baselines) enables
    the deviation features; if omitted they are filled neutrally (dev=0)."""
    config = config or DEFAULT_CONFIG
    out = df.sort_values(["station_id", "timestamp"]).reset_index(drop=True)

    out = _cyclical_time(out)
    out = thermodynamic_features(out)

    parts = []
    for _sid, g in out.groupby("station_id", sort=False):
        parts.append(_station_temporal(g.reset_index(drop=True), config))
    out = pd.concat(parts, ignore_index=True)

    if baselines is not None:
        out = deviation_features(out, baselines, config)
    else:
        for sensor in CORE_SENSORS:
            out[BASELINE_COLS[sensor]] = out[sensor]
            out[DEV_COLS[sensor]] = 0.0

    return out


def to_model_matrix(feat_df: pd.DataFrame, config=None, features=None):
    """Select the Isolation Forest feature columns as a float matrix.

    Returns ``(X, complete_mask)`` where ``complete_mask`` marks rows that have
    all raw core sensors present (the honest training/scoring population — rows
    missing a raw sensor are handled by imputation upstream, never silently
    zero-filled into the model as if observed). Engineered NaNs (window edges,
    undefined rates) are filled with 0.0, a neutral "no-evidence" value.

    ``features`` overrides the column list (e.g. the persisted training features),
    so a loaded model always scores on exactly the columns it was trained on.
    """
    config = config or DEFAULT_CONFIG
    cols = list(features) if features is not None else list(config.if_features)
    missing = [c for c in cols if c not in feat_df.columns]
    if missing:
        raise KeyError(f"feature frame missing required IF columns: {missing}")
    X = feat_df.reindex(columns=cols).astype(float)
    X = X.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    complete = feat_df[list(CORE_SENSORS)].notna().all(axis=1).to_numpy()
    return X, complete

