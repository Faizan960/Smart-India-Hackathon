"""Sensor health tracking tests (spec section 22)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ml.pipeline.config import DEFAULT_CONFIG
from ml.pipeline.health import _status, rolling_health, station_health_summary

_STATUSES = {"HEALTHY", "WATCH", "DEGRADED", "CRITICAL", "UNKNOWN"}


def test_status_thresholds():
    assert _status(0.0, DEFAULT_CONFIG) == "HEALTHY"
    assert _status(0.10, DEFAULT_CONFIG) == "WATCH"
    assert _status(0.20, DEFAULT_CONFIG) == "DEGRADED"
    assert _status(0.50, DEFAULT_CONFIG) == "CRITICAL"
    assert _status(float("nan"), DEFAULT_CONFIG) == "UNKNOWN"


def test_rolling_health_all_normal_is_healthy():
    n = 30
    feat = pd.DataFrame({
        "station_id": "S",
        "timestamp": pd.date_range("2021-06-01", periods=n, freq="1h"),
    })
    anom = pd.DataFrame({
        "is_anomaly": np.zeros(n, dtype=bool),
        "core_complete": np.ones(n, dtype=bool),
    }, index=feat.index)
    rh = rolling_health(feat, anom)
    assert (rh["health_status"] == "HEALTHY").all()
    assert (rh["health_coverage"].dropna() <= 1.0).all()


def test_rolling_health_high_rate_is_critical():
    n = 30
    feat = pd.DataFrame({
        "station_id": "S",
        "timestamp": pd.date_range("2021-06-01", periods=n, freq="1h"),
    })
    anom = pd.DataFrame({
        "is_anomaly": np.ones(n, dtype=bool),   # every recent point flagged
        "core_complete": np.ones(n, dtype=bool),
    }, index=feat.index)
    rh = rolling_health(feat, anom)
    assert rh["health_status"].iloc[-1] == "CRITICAL"


def test_station_summary_one_row_per_station(feat_all, anom_all, cls_all):
    summ = station_health_summary(feat_all, anom_all, cls_all)
    assert set(summ["station_id"]) == {"AAA", "BBB"}
    assert len(summ) == 2
    assert set(summ["health_status"]).issubset(_STATUSES)
    assert "dominant_fault_in_range" in summ.columns
