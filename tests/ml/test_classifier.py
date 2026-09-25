"""Signature-based fault classifier tests (spec sections 12-14).

These build minimal, hand-crafted single-station feature frames so each typing
branch and priority rule can be exercised deterministically, independent of the
detector's learned scores.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ml.pipeline.classifier import classify_faults


def _mk_feat(n, station="S", **overrides):
    """Minimal single-station feature frame with NORMAL defaults for every column
    the signature stage reads. Defaults vary each sensor by more than its
    resolution so nothing is accidentally seen as frozen."""
    ts = pd.date_range("2021-06-01", periods=n, freq="1h")
    data = {
        "station_id": station,
        "timestamp": ts,
        "temperature": np.linspace(20.0, 25.0, n),
        "humidity": np.linspace(40.0, 60.0, n),
        "pressure": np.linspace(1010.0, 1012.0, n),
        "dt_hours": np.r_[np.nan, np.full(n - 1, 1.0)],
        "temp_rate": np.zeros(n),
        "humidity_rate": np.zeros(n),
        "pressure_rate": np.zeros(n),
        "temp_dev_baseline": np.zeros(n),
        "humidity_dev_baseline": np.zeros(n),
        "pressure_dev_baseline": np.zeros(n),
        "thermo_inconsistency": np.zeros(n, dtype=bool),
        "thermo_inconsistency_score": np.zeros(n),
    }
    df = pd.DataFrame(data)
    for k, v in overrides.items():
        df[k] = v
    return df


def _anom(scores):
    scores = np.asarray(scores, dtype=float)
    return pd.DataFrame({"anomaly_score": scores}, index=range(len(scores)))


def test_dropout_reported_on_own_evidence():
    n = 10
    pressure = np.linspace(1010.0, 1012.0, n)
    pressure[4] = np.nan  # an expected sensor goes missing in one row
    feat = _mk_feat(n, pressure=pressure)
    cls = classify_faults(feat, _anom(np.zeros(n)), {})
    assert cls["fault_type"].iloc[4] == "SENSOR_DROPOUT"
    assert cls["fault_confidence"].iloc[4] <= 0.97  # hedged, never fabricated certainty


def test_physical_inconsistency_typed():
    n = 8
    phys = np.zeros(n, dtype=bool); phys[3] = True
    feat = _mk_feat(n, thermo_inconsistency=phys,
                    thermo_inconsistency_score=np.where(phys, 0.6, 0.0))
    cls = classify_faults(feat, _anom(np.zeros(n)), {})
    assert cls["fault_type"].iloc[3] == "PHYSICAL_INCONSISTENCY"


def test_temperature_freeze_fires_without_detector_flag():
    n = 10
    temp = np.linspace(20.0, 25.0, n).copy()
    temp[:7] = 22.0  # 7 identical hourly readings => >=6h flat run
    feat = _mk_feat(n, temperature=temp)
    cls = classify_faults(feat, _anom(np.zeros(n)), {})  # score low => is_anom False
    assert "SENSOR_FREEZE" in set(cls["fault_type"].tolist())


def test_pressure_freeze_requires_detector_flag():
    n = 10
    press = np.linspace(1010.0, 1012.0, n).copy()
    press[:7] = 1011.0  # flat pressure run (often just calm real weather)
    feat = _mk_feat(n, pressure=press)
    low = classify_faults(feat, _anom(np.zeros(n)), {})
    assert "SENSOR_FREEZE" not in set(low["fault_type"].tolist())
    hot = np.zeros(n); hot[6] = 0.9
    high = classify_faults(feat, _anom(hot), {})
    assert high["fault_type"].iloc[6] == "SENSOR_FREEZE"


def test_multivariate_resolved_before_spike():
    n = 3
    thr = {"rate_abs_threshold": {"temperature": 5.0, "humidity": 1e9, "pressure": 1e9}}
    temp = np.array([20.0, 30.0, 20.0])
    temp_rate = np.array([np.nan, 10.0, -10.0])  # big excursion + reversal
    feat = _mk_feat(n, temperature=temp, temp_rate=temp_rate,
                    temp_dev_baseline=np.array([0.0, 4.0, 0.0]),
                    humidity_dev_baseline=np.array([0.0, 4.0, 0.0]))
    cls = classify_faults(feat, _anom(np.array([0.0, 0.9, 0.9])), thr)
    # a multi-sensor anomaly is more specific than a single-sensor spike
    assert cls["fault_type"].iloc[1] == "MULTIVARIATE_ANOMALY"
    # the provisional single-sensor spike is typed and mapped to a legacy label
    assert cls["fault_type"].iloc[2] == "TRANSIENT_SPIKE"
    assert cls["legacy_label"].iloc[2] == "TEMPERATURE_DROP"


def test_calibration_drift_typed_when_flagged():
    n = 12
    feat = _mk_feat(n, temp_dev_baseline=np.full(n, 2.0))  # sustained one-sided dev
    score = np.zeros(n); score[-1] = 0.9  # detector flags the latest point
    cls = classify_faults(feat, _anom(score), {})
    assert cls["fault_type"].iloc[-1] == "CALIBRATION_DRIFT"


def test_taxonomy_and_hedged_confidence_on_real_scores(cls_all):
    # the 0.97 hedge cap applies to ASSERTED faults; NORMAL rows carry a
    # "confidence it is normal" of (1 - score), which may exceed 0.97 on very
    # clean points -- that is not a fabricated fault certainty.
    nonnormal = cls_all[cls_all["fault_type"] != "NORMAL"]
    if len(nonnormal):
        assert nonnormal["fault_confidence"].max() <= 0.97
    allowed = {"NORMAL", "SENSOR_DROPOUT", "SENSOR_FREEZE", "TRANSIENT_SPIKE",
               "CALIBRATION_DRIFT", "PHYSICAL_INCONSISTENCY", "MULTIVARIATE_ANOMALY",
               "UNKNOWN_ANOMALY"}
    assert set(cls_all["fault_type"].unique()).issubset(allowed)
