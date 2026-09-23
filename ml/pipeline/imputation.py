"""Gap imputation for display / downstream continuity (spec section 21).

Fills ONLY short interior gaps in each sensor series, by time-linear interpolation
between the bracketing valid readings, and flags every filled value with an
``<sensor>_imputed`` boolean. Long gaps and leading/trailing gaps are left as NaN:
a genuine dropout is a fault to be reported, not silently papered over (spec
section 35). Imputation never feeds detector training; it is a convenience layer
applied after detection.
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from .config import CORE_SENSORS, DEFAULT_CONFIG


def _impute_column(vals: np.ndarray, ts_s: np.ndarray, max_gap_h: float):
    """Linear-in-time fill of interior NaN runs whose total span <= max_gap_h.

    Returns ``(filled_values, imputed_mask)``. Leading/trailing NaN and over-long
    gaps are left untouched so real dropouts remain visible.
    """
    n = len(vals)
    out = vals.astype(float).copy()
    imp = np.zeros(n, dtype=bool)
    valid = np.isfinite(vals)
    if valid.sum() < 2:
        return out, imp
    k = 0
    while k < n:
        if valid[k]:
            k += 1
            continue
        j = k
        while j < n and not valid[j]:
            j += 1
        left, right = k - 1, j
        if left >= 0 and right < n:  # interior gap only (bounded both sides)
            t0, t1 = ts_s[left], ts_s[right]
            span_h = (t1 - t0) / 3600.0
            if np.isfinite(span_h) and 0 < span_h <= max_gap_h and t1 > t0:
                v0, v1 = vals[left], vals[right]
                for m in range(k, j):
                    w = (ts_s[m] - t0) / (t1 - t0)
                    out[m] = v0 + w * (v1 - v0)
                    imp[m] = True
        k = j
    return out, imp


def impute_gaps(df: pd.DataFrame, config=None, max_gap_hours: float | None = None):
    """Impute short interior gaps per station per core sensor.

    Returns ``(df_out, report)``. ``df_out`` is a copy (sorted by station, time)
    with filled values and new ``<sensor>_imputed`` boolean columns; ``report``
    counts filled values per sensor so the imputation is fully auditable.
    """
    config = config or DEFAULT_CONFIG
    max_gap_hours = float(max_gap_hours if max_gap_hours is not None else config.impute_max_gap_hours)
    out = df.sort_values(["station_id", "timestamp"]).reset_index(drop=True).copy()
    ts_s_all = (pd.to_datetime(out["timestamp"], errors="coerce")
                .to_numpy(dtype="datetime64[ns]").astype("float64") / 1e9)
    report: Dict[str, float] = {s: 0 for s in CORE_SENSORS}

    for sensor in CORE_SENSORS:
        out[f"{sensor}_imputed"] = False

    for _sid, g in out.groupby("station_id", sort=False):
        idx = g.index.to_numpy()
        ts_s = ts_s_all[idx]
        for sensor in CORE_SENSORS:
            vals = out[sensor].to_numpy(dtype=float)[idx]
            filled, imp = _impute_column(vals, ts_s, max_gap_hours)
            if imp.any():
                out.loc[idx, sensor] = filled
                out.loc[idx, f"{sensor}_imputed"] = imp
                report[sensor] += int(imp.sum())

    report["max_gap_hours"] = max_gap_hours
    report["total_imputed"] = int(sum(report[s] for s in CORE_SENSORS))
    return out, report
