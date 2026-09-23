"""Sensor health tracking (spec section 22).

A rolling, per-station view of how often the detector is flagging anomalies,
mapped to a hedged health status (HEALTHY / WATCH / DEGRADED / CRITICAL) using the
rate thresholds in config. A high recent anomaly rate is evidence a sensor MAY be
degrading — it is never asserted as a confirmed hardware failure (spec section
35). Health is a maintenance-prioritisation signal computed from real model
outputs, not a verdict.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import DEFAULT_CONFIG


def _status(rate: float, config) -> str:
    if not np.isfinite(rate):
        return "UNKNOWN"
    if rate >= config.health_critical_anomaly_rate:
        return "CRITICAL"
    if rate >= config.health_degraded_anomaly_rate:
        return "DEGRADED"
    if rate >= config.health_watch_anomaly_rate:
        return "WATCH"
    return "HEALTHY"


def rolling_health(feat_df: pd.DataFrame, anomaly_df: pd.DataFrame, config=None) -> pd.DataFrame:
    """Per-row rolling anomaly rate + health status over ``config.health_window``.

    Returns a frame indexed like ``feat_df`` with ``health_anomaly_rate``,
    ``health_coverage`` (fraction of window rows that were scorable) and
    ``health_status``.
    """
    config = config or DEFAULT_CONFIG
    is_anom = anomaly_df["is_anomaly"].reindex(feat_df.index).fillna(False).astype(float)
    scored = anomaly_df["core_complete"].reindex(feat_df.index).fillna(False).astype(float)
    work = pd.DataFrame({
        "station_id": feat_df["station_id"].to_numpy(),
        "timestamp": pd.to_datetime(feat_df["timestamp"], errors="coerce").to_numpy(),
        "is_anom": is_anom.to_numpy(),
        "scored": scored.to_numpy(),
    }, index=feat_df.index)

    rate = pd.Series(np.nan, index=feat_df.index)
    cover = pd.Series(np.nan, index=feat_df.index)
    for _sid, g in work.groupby("station_id", sort=False):
        g = g.sort_values("timestamp")
        ts = pd.DatetimeIndex(g["timestamp"])
        rate.loc[g.index] = pd.Series(g["is_anom"].to_numpy(), index=ts).rolling(config.health_window).mean().to_numpy()
        cover.loc[g.index] = pd.Series(g["scored"].to_numpy(), index=ts).rolling(config.health_window).mean().to_numpy()

    out = pd.DataFrame(index=feat_df.index)
    out["health_anomaly_rate"] = rate.round(4)
    out["health_coverage"] = cover.round(4)
    out["health_status"] = [_status(x, config) for x in rate.to_numpy()]
    return out


def station_health_summary(feat_df: pd.DataFrame, anomaly_df: pd.DataFrame,
                            class_df: pd.DataFrame | None = None, config=None) -> pd.DataFrame:
    """Latest-window health per station, for dashboards / maintenance triage.

    ``health_status`` reflects the rolling anomaly rate at each station's most
    recent observation (the trailing ``health_window``). ``dominant_fault_in_range``
    is the most common non-normal classifier label over the rows supplied — scope
    the input frame to the window you care about.
    """
    config = config or DEFAULT_CONFIG
    rh = rolling_health(feat_df, anomaly_df, config)
    base = pd.DataFrame({
        "station_id": feat_df["station_id"].to_numpy(),
        "timestamp": pd.to_datetime(feat_df["timestamp"], errors="coerce").to_numpy(),
        "rate": rh["health_anomaly_rate"].to_numpy(),
        "status": rh["health_status"].to_numpy(),
    }, index=feat_df.index)

    rows = []
    for sid, g in base.groupby("station_id", sort=False):
        g = g.sort_values("timestamp")
        last = g.iloc[-1]
        rec = {
            "station_id": sid,
            "n_observations": int(len(g)),
            "latest_timestamp": last["timestamp"],
            "latest_anomaly_rate": None if not np.isfinite(last["rate"]) else float(last["rate"]),
            "health_status": last["status"],
        }
        if class_df is not None and "fault_type" in class_df.columns:
            ft = class_df["fault_type"].reindex(g.index)
            nonnormal = ft[ft != "NORMAL"]
            rec["dominant_fault_in_range"] = (str(nonnormal.value_counts().idxmax())
                                              if len(nonnormal) else "NORMAL")
        rows.append(rec)
    return pd.DataFrame(rows)
