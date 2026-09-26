"""Latest-observation inference regression tests (spec section 36, phase 10).

Covers the reported workflow issue: an ad-hoc ``groupby(...).tail(200)`` can end
on an incomplete reading, for which the pipeline CORRECTLY refuses to fabricate a
score. These tests pin down (A) a complete latest observation is scored for real,
(B) an incomplete latest observation is handled safely and stays strictly JSON
serializable, and (C) historical health is independent of the current row's
scoring status. All hermetic -- they use the shared temp-trained ``models_dir``.
"""
from __future__ import annotations

import json

import numpy as np
import pytest

from ml.pipeline.inference import SentinelInference, latest_complete_window

_HEALTH = {"HEALTHY", "WATCH", "DEGRADED", "CRITICAL", "UNKNOWN"}


def _aaa(synthetic_frame):
    """Station AAA history (hourly, fully complete clean data)."""
    return synthetic_frame[synthetic_frame["station_id"] == "AAA"].copy()


def _drop_last_core(hist, sensor="pressure"):
    """Make the final (latest-timestamp) reading incomplete: a core sensor value
    has not arrived yet. This mimics real streaming telemetry, not corruption."""
    hist = hist.copy()
    hist.iloc[-1, hist.columns.get_loc(sensor)] = np.nan
    return hist


# --- window selection helper -------------------------------------------------

def test_latest_complete_window_ends_on_complete_row(synthetic_frame):
    hist = _drop_last_core(_aaa(synthetic_frame))
    win = latest_complete_window(hist, station_id="AAA", history_rows=100)
    assert 2 <= len(win) <= 100
    assert win[["temperature", "humidity", "pressure"]].iloc[-1].notna().all()
    # it skipped the trailing incomplete row rather than fabricating its sensors
    assert win["timestamp"].iloc[-1] < hist["timestamp"].iloc[-1]


def test_latest_complete_window_raises_when_none(synthetic_frame):
    hist = _aaa(synthetic_frame)
    hist["pressure"] = np.nan  # a core sensor is never present
    with pytest.raises(ValueError):
        latest_complete_window(hist, station_id="AAA")


def test_latest_complete_window_refuses_mixed_stations(synthetic_frame):
    with pytest.raises(ValueError):
        latest_complete_window(synthetic_frame)  # >1 station, no station_id


# --- A. complete latest observation -> a real, sourced assessment ------------

def test_complete_latest_observation_gets_real_score(models_dir, synthetic_frame):
    eng = SentinelInference(models_dir=models_dir)
    res = eng.predict_latest_complete(_aaa(synthetic_frame), station_id="AAA")

    assert isinstance(res["anomaly_score"], float)
    assert 0.0 <= res["anomaly_score"] <= 1.0
    assert res["verification"]["isolation_forest_score"] is not None
    # SHAP (or the labelled fallback) is populated when scoring succeeds
    assert res["explanation"]["score"] is not None
    assert res["explanation"]["top_features"]
    # a Laya-typed decision is produced, explicitly pipeline-sourced
    assert res["laya_decision"]["source"] == "aws_sentinel_pipeline"
    json.dumps(res)  # strict


def test_predict_latest_complete_skips_trailing_incomplete(models_dir, synthetic_frame):
    eng = SentinelInference(models_dir=models_dir)
    res = eng.predict_latest_complete(_drop_last_core(_aaa(synthetic_frame)),
                                      station_id="AAA", history_rows=120)
    # the incomplete final row was skipped; the prior complete row scored for real
    assert isinstance(res["anomaly_score"], float)
    assert res["verification"]["isolation_forest_score"] is not None
    json.dumps(res)


# --- B. incomplete latest observation -> safe, never fabricated --------------

def test_incomplete_latest_observation_is_safe(models_dir, synthetic_frame):
    eng = SentinelInference(models_dir=models_dir)
    res = eng.predict_observation(_drop_last_core(_aaa(synthetic_frame)), station_id="AAA")

    # 1. no fabricated Isolation Forest score (this is the correct missing-data guard)
    assert res["anomaly_score"] is None
    assert res["is_anomaly"] is False
    # 2. the verification score is null, not NaN (strict-JSON quality fix)
    assert res["verification"]["isolation_forest_score"] is None
    # 3. no fabricated SHAP attribution
    assert res["explanation"]["score"] is None
    assert res["explanation"]["top_features"] == []
    # 4. missing data is never dressed up as a confirmed hardware failure: any fault
    #    reported is only the hedged probable-dropout signature, with hedged numbers
    assert res["fault_confidence"] <= 0.97
    assert res["fault_present"] <= 0.8
    if res["fault_type"] != "NORMAL":
        assert res["fault_type"] == "SENSOR_DROPOUT"
    # 5. strictly JSON serializable (no default=str)
    json.dumps(res)


# --- C. health is independent of the current row's scoring status ------------

def test_health_independent_of_current_scoring_status(models_dir, synthetic_frame):
    eng = SentinelInference(models_dir=models_dir)
    res = eng.predict_observation(_drop_last_core(_aaa(synthetic_frame)), station_id="AAA")

    health = res["health"]
    assert health["station_id"] == "AAA"
    assert health["n_observations"] >= 1
    # recent-window health status is still reported though the latest row is unscored
    assert health["health_status"] in _HEALTH
    # the historical typed-fault signature is a distinct dimension from current score
    assert "dominant_fault_in_range" in health
