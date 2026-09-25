"""Deterministic data-quality control + leakage-free chronological split
(spec sections 4 & 5).

QC adds inspectable evidence flag columns; it NEVER mutates observations. The
split is strictly chronological (no shuffling) so validation/test data always
stays in the future relative to training data.
"""
from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pandas as pd

from .config import CORE_SENSORS, DEFAULT_CONFIG, SENSOR_BOUNDS


def infer_sampling_seconds(timestamps: pd.Series) -> float:
    """Median spacing between consecutive observations, in seconds (interval-aware
    features rely on this instead of assuming a fixed sample rate)."""
    ts = pd.to_datetime(timestamps).sort_values()
    diffs = ts.diff().dropna().dt.total_seconds()
    diffs = diffs[diffs > 0]
    return float(diffs.median()) if len(diffs) else np.nan


def station_intervals(df: pd.DataFrame) -> Dict[str, float]:
    return {str(sid): infer_sampling_seconds(g["timestamp"]) for sid, g in df.groupby("station_id")}


def run_quality_control(df: pd.DataFrame, config=None) -> Tuple[pd.DataFrame, Dict]:
    """Add q_* evidence columns. Returns (annotated_df, summary_dict)."""
    config = config or DEFAULT_CONFIG
    out = df.sort_values(["station_id", "timestamp"]).reset_index(drop=True)

    for col in CORE_SENSORS:
        out[f"q_missing_{col}"] = out[col].isna()
        lo, hi = SENSOR_BOUNDS[col]
        out[f"q_out_of_range_{col}"] = ((out[col] < lo) | (out[col] > hi)) & out[col].notna()
    out["q_missing"] = out[[f"q_missing_{c}" for c in CORE_SENSORS]].any(axis=1)
    out["q_out_of_range"] = out[[f"q_out_of_range_{c}" for c in CORE_SENSORS]].any(axis=1)

    arr = out[list(CORE_SENSORS)].to_numpy(dtype=float)
    out["q_nonfinite"] = (~np.isfinite(arr)).any(axis=1) & ~out["q_missing"].to_numpy()
    out["q_duplicate_ts"] = out.duplicated(subset=["station_id", "timestamp"], keep="first")

    out["gap_hours"] = np.nan
    out["q_gap"] = False
    for _sid, g in out.groupby("station_id"):
        gap = g["timestamp"].diff().dt.total_seconds() / 3600.0
        out.loc[g.index, "gap_hours"] = gap.values
        med_s = infer_sampling_seconds(g["timestamp"])
        if med_s and np.isfinite(med_s):
            med_h = med_s / 3600.0
            out.loc[g.index, "q_gap"] = (gap > config.dropout_gap_factor * med_h).values

    out["q_any"] = out[["q_missing", "q_out_of_range", "q_nonfinite", "q_duplicate_ts", "q_gap"]].any(axis=1)

    summary = {
        "rows": int(len(out)),
        "q_missing": int(out["q_missing"].sum()),
        "q_out_of_range": int(out["q_out_of_range"].sum()),
        "q_nonfinite": int(out["q_nonfinite"].sum()),
        "q_duplicate_ts": int(out["q_duplicate_ts"].sum()),
        "q_gap": int(out["q_gap"].sum()),
        "per_sensor_missing": {c: int(out[f"q_missing_{c}"].sum()) for c in CORE_SENSORS},
    }
    return out, summary


def chronological_split(df: pd.DataFrame, config=None):
    """Split into (train, val, test) strictly by time. No shuffling."""
    config = config or DEFAULT_CONFIG
    out = df.sort_values("timestamp")
    ts = out["timestamp"]
    if config.explicit_split:
        def _sel(key):
            s, e = config.explicit_split[key]
            return out[(ts >= pd.Timestamp(s)) & (ts <= pd.Timestamp(e))].copy()
        return _sel("train"), _sel("validation"), _sel("test")
    t1 = ts.quantile(config.train_frac)
    t2 = ts.quantile(config.train_frac + config.val_frac)
    return out[ts < t1].copy(), out[(ts >= t1) & (ts < t2)].copy(), out[ts >= t2].copy()


def split_bounds(df: pd.DataFrame, config=None):
    """The (train_end, val_end) timestamps used by the split, for logging."""
    config = config or DEFAULT_CONFIG
    if config.explicit_split:
        return config.explicit_split["train"][1], config.explicit_split["validation"][1]
    ts = df["timestamp"]
    return ts.quantile(config.train_frac), ts.quantile(config.train_frac + config.val_frac)
