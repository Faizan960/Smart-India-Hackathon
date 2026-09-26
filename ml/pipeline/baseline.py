"""Diurnal baseline normals (spec section 6).

Robust per (station, month, hour) climatology built from TRAINING data only,
with hierarchical fallback to coarser groupings (station x month, then station,
then global) for sparse cells. Deviations are robust z-scores computed against
median / MAD, so a value is judged against what is normal *for that station,
month and hour* — a hot monsoon afternoon is not flagged merely for being hot.

Baselines are pure evidence: they never label anything, they only quantify how
far an observation sits from its own climatological normal.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd

from .config import CORE_SENSORS, DEFAULT_CONFIG, SENSOR_RESOLUTION

_MAD_TO_SIGMA = 1.4826  # scales MAD to a std-dev estimate for a normal distribution

# deviation column produced per core sensor
DEV_COLS = {
    "temperature": "temp_dev_baseline",
    "humidity": "humidity_dev_baseline",
    "pressure": "pressure_dev_baseline",
}
# baseline-median column produced per core sensor (used by imputation / explainability)
BASELINE_COLS = {
    "temperature": "temp_baseline",
    "humidity": "humidity_baseline",
    "pressure": "pressure_baseline",
}


def _with_time_parts(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["month"] = out["timestamp"].dt.month.astype(int)
    out["hour"] = out["timestamp"].dt.hour.astype(int)
    return out


def _mad(s: pd.Series) -> float:
    x = s.dropna().to_numpy(dtype=float)
    if x.size == 0:
        return np.nan
    return float(np.median(np.abs(x - np.median(x))))


def _level_dicts(df: pd.DataFrame, keys, sensors, min_samples: int, enforce_min: bool):
    """Return {sensor: {"median": {key: v}, "sigma": {key: v}}} for a grouping.

    Cells with fewer than ``min_samples`` valid readings are omitted when
    ``enforce_min`` is set, so lookups fall through to the next coarser level.
    """
    grouped = df.groupby(list(keys), sort=False)
    out: Dict[str, Dict[str, Dict]] = {}
    for sensor in sensors:
        med = grouped[sensor].median()
        cnt = grouped[sensor].apply(lambda s: int(s.notna().sum()))
        mad = grouped[sensor].apply(_mad) * _MAD_TO_SIGMA
        keep = cnt >= min_samples if enforce_min else cnt > 0
        med, mad = med[keep], mad[keep]

        def _key(idx):
            return "|".join(str(p) for p in idx) if isinstance(idx, tuple) else str(idx)

        out[sensor] = {
            "median": {_key(k): float(v) for k, v in med.items() if np.isfinite(v)},
            "sigma": {_key(k): float(v) for k, v in mad.items() if np.isfinite(v)},
        }
    return out


def compute_baselines(train_df: pd.DataFrame, config=None) -> Dict:
    """Build the hierarchical robust baseline from TRAINING rows only."""
    config = config or DEFAULT_CONFIG
    sensors = list(CORE_SENSORS)
    df = _with_time_parts(train_df)
    mn = config.baseline_min_samples

    smh = _level_dicts(df, ("station_id", "month", "hour"), sensors, mn, enforce_min=True)
    sm = _level_dicts(df, ("station_id", "month"), sensors, mn, enforce_min=True)
    s = _level_dicts(df, ("station_id",), sensors, mn, enforce_min=False)
    glob = {
        sensor: {
            "median": float(df[sensor].median()) if df[sensor].notna().any() else 0.0,
            "sigma": float(_mad(df[sensor]) * _MAD_TO_SIGMA) or float(SENSOR_RESOLUTION[sensor]),
        }
        for sensor in sensors
    }
    return {
        "meta": {
            "keys": ["station_id", "month", "hour"],
            "sensors": sensors,
            "min_samples": mn,
            "n_train_rows": int(len(train_df)),
            "generated_utc": datetime.now(timezone.utc).isoformat(),
        },
        "smh": smh,
        "sm": sm,
        "s": s,
        "global": glob,
    }


def save_baselines(baselines: Dict, path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(baselines, f, indent=2)
    return path


def load_baselines(path) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def deviation_features(df: pd.DataFrame, baselines: Dict, config=None) -> pd.DataFrame:
    """Append <sensor>_baseline (median) and <sensor>_dev_baseline (robust z-score).

    Lookup is hierarchical: finest (station,month,hour) cell first, then
    station x month, then station, then global. Robust z = (x - median) / sigma,
    with sigma floored at the sensor resolution to avoid blow-ups in ultra-stable
    cells, and clipped to +/- config.zscore_clip.
    """
    config = config or DEFAULT_CONFIG
    out = _with_time_parts(df)
    k_smh = (out["station_id"].astype(str) + "|" + out["month"].astype(str) + "|" + out["hour"].astype(str))
    k_sm = (out["station_id"].astype(str) + "|" + out["month"].astype(str))
    k_s = out["station_id"].astype(str)

    for sensor in CORE_SENSORS:
        med = k_smh.map(baselines["smh"][sensor]["median"])
        med = med.fillna(k_sm.map(baselines["sm"][sensor]["median"]))
        med = med.fillna(k_s.map(baselines["s"][sensor]["median"]))
        med = med.fillna(baselines["global"][sensor]["median"])

        sig = k_smh.map(baselines["smh"][sensor]["sigma"])
        sig = sig.fillna(k_sm.map(baselines["sm"][sensor]["sigma"]))
        sig = sig.fillna(k_s.map(baselines["s"][sensor]["sigma"]))
        sig = sig.fillna(baselines["global"][sensor]["sigma"])
        sig = sig.clip(lower=float(SENSOR_RESOLUTION[sensor]))

        dev = (out[sensor] - med) / sig
        out[BASELINE_COLS[sensor]] = med
        out[DEV_COLS[sensor]] = dev.clip(-config.zscore_clip, config.zscore_clip)

    return out.drop(columns=["month", "hour"])

