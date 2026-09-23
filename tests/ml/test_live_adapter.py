"""Live-adapter integration tests (branch ``feature/live-weather-demo``).

Exercises :mod:`ml.pipeline.live_adapter` -- the thin bridge from the browser's
rolling live-weather history (a list of plain observation dicts) to the real-data
Sentinel inference pipeline. Covers the 12 scenarios required by the integration
spec (valid obs; each missing core sensor; short vs sufficient history; normal vs
anomalous; Laya reached; explanation JSON-serializable; no NaN/Inf ever reaches
JSON; existing frontend contract preserved) plus adapter specifics (camelCase
``windSpeed`` aliasing, empty->degraded, missing values never fabricated,
timestamp-less rows dropped, station-specific vs global baseline source).

Hermetic: uses the shared temp-trained ``models_dir`` + ``synthetic_frame``
fixtures, so it needs neither the real NOAA CSV nor the committed artifacts.
"""
from __future__ import annotations

import json
import math

import pandas as pd
import pytest

from ml.pipeline.inference import SentinelInference
from ml.pipeline.live_adapter import (
    assess_live,
    baseline_source,
    normalize_live_history,
)

# The response contract the updated dashboard relies on (legacy 4 + richer set).
_CONTRACT_KEYS = {
    "station_id", "timestamp", "anomaly_score", "is_anomaly", "severity",
    "fault_type", "fault_confidence", "confidence", "fused_status", "reasons",
    "explanation", "laya_decision", "verification", "health",
    "baseline_source", "data_complete", "n_history",
}


def _engine(models_dir):
    return SentinelInference(models_dir=models_dir)


def _history_dicts(frame, station_id="AAA", n=300):
    """Synthetic Sentinel rows -> browser-normalized live observation dicts.

    Deliberately emits the camelCase ``windSpeed`` key (to exercise the adapter's
    field aliasing) and omits station_id/lat/lon from each point -- the live
    frontend history does not carry them; the adapter supplies them per call.
    """
    rows = frame[frame["station_id"] == station_id].tail(n)
    out = []
    for _, r in rows.iterrows():
        out.append({
            "timestamp": pd.Timestamp(r["timestamp"]).isoformat(),
            "temperature": None if pd.isna(r["temperature"]) else float(r["temperature"]),
            "humidity": None if pd.isna(r["humidity"]) else float(r["humidity"]),
            "pressure": None if pd.isna(r["pressure"]) else float(r["pressure"]),
            "windSpeed": None if pd.isna(r["wind_speed"]) else float(r["wind_speed"]),
        })
    return out


# --- 1, 6, 7. a valid, complete latest observation with sufficient history --

def test_valid_normal_observation_scored(models_dir, synthetic_frame):
    hist = _history_dicts(synthetic_frame, "AAA", 300)
    res = assess_live(hist, station_id="AAA", engine=_engine(models_dir))
    assert isinstance(res["anomaly_score"], float)
    assert 0.0 <= res["anomaly_score"] <= 1.0
    assert res["is_anomaly"] is False
    assert res["fault_type"] == "NORMAL"
    assert res["data_complete"] is True
    assert res["n_history"] == 300
    json.dumps(res, allow_nan=False)


# --- 8. an anomalous latest observation is flagged and typed non-NORMAL -----

def test_anomalous_observation_flagged(models_dir, synthetic_frame):
    hist = _history_dicts(synthetic_frame, "AAA", 300)
    hist[-1]["temperature"] = 120.0  # physically impossible spike on the latest read
    res = assess_live(hist, station_id="AAA", engine=_engine(models_dir))
    assert res["anomaly_score"] is not None
    assert res["is_anomaly"] is True or res["fault_type"] != "NORMAL"
    assert res["severity"] in {"WARNING", "CRITICAL"}
    json.dumps(res, allow_nan=False)


# --- 2, 3, 4. a missing core sensor on the latest reading is handled safely --

@pytest.mark.parametrize("sensor", ["temperature", "humidity", "pressure"])
def test_missing_core_sensor_is_safe(models_dir, synthetic_frame, sensor):
    hist = _history_dicts(synthetic_frame, "AAA", 300)
    hist[-1][sensor] = None  # a value simply has not arrived (real streaming gap)
    res = assess_live(hist, station_id="AAA", engine=_engine(models_dir))
    # no fabricated score / attribution when the row cannot be scored
    assert res["anomaly_score"] is None
    assert res["is_anomaly"] is False
    assert res["verification"]["isolation_forest_score"] is None
    assert res["explanation"]["score"] is None
    assert res["data_complete"] is False
    # a missing value is never dressed up as a confirmed hardware failure
    assert res["fault_confidence"] <= 0.97
    if res["fault_type"] != "NORMAL":
        assert res["fault_type"] == "SENSOR_DROPOUT"
    json.dumps(res, allow_nan=False)


# --- 5. a very short history is handled explicitly, never crashes -----------

def test_short_history_handled(models_dir, synthetic_frame):
    hist = _history_dicts(synthetic_frame, "AAA", 3)  # only 3 readings available
    res = assess_live(hist, station_id="AAA", engine=_engine(models_dir))
    assert res["n_history"] == 3
    assert isinstance(res["is_anomaly"], bool)
    # score is either a real float (latest row complete) or None -- never NaN
    assert res["anomaly_score"] is None or isinstance(res["anomaly_score"], float)
    json.dumps(res, allow_nan=False)


# --- 9. the Laya decision layer is reached and explicitly pipeline-sourced --

def test_laya_decision_reached(models_dir, synthetic_frame):
    hist = _history_dicts(synthetic_frame, "AAA", 200)
    res = assess_live(hist, station_id="AAA", engine=_engine(models_dir))
    laya = res["laya_decision"]
    assert laya["source"] == "aws_sentinel_pipeline"
    assert "decision" in laya and "confidence" in laya
    json.dumps(res, allow_nan=False)


# --- 10. the SHAP (or labelled fallback) explanation is JSON serializable ---

def test_explanation_json_serializable(models_dir, synthetic_frame):
    hist = _history_dicts(synthetic_frame, "AAA", 200)
    res = assess_live(hist, station_id="AAA", engine=_engine(models_dir))
    expl = res["explanation"]
    assert expl["score"] is not None          # scored row -> attribution present
    assert isinstance(expl["top_features"], list) and expl["top_features"]
    json.dumps(expl, allow_nan=False)          # strictly serializable on its own


# --- 11. NaN / Infinity never reaches JSON on ANY path ----------------------

def test_no_nan_infinity_reaches_json(models_dir, synthetic_frame):
    eng = _engine(models_dir)
    complete = _history_dicts(synthetic_frame, "AAA", 100)
    incomplete = _history_dicts(synthetic_frame, "AAA", 100)
    incomplete[-1]["pressure"] = None
    spike = _history_dicts(synthetic_frame, "AAA", 100)
    spike[-1]["temperature"] = 120.0
    for hist in (complete, incomplete, spike, []):
        res = assess_live(hist, station_id="AAA", engine=eng)
        json.dumps(res, allow_nan=False)       # raises on any NaN/Inf -> guard holds


# --- 12. the existing frontend API response contract is preserved -----------

def test_frontend_contract_preserved(models_dir, synthetic_frame):
    hist = _history_dicts(synthetic_frame, "AAA", 100)
    res = assess_live(hist, station_id="AAA", engine=_engine(models_dir))
    for k in ("is_anomaly", "anomaly_score", "fault_type", "confidence"):
        assert k in res                        # the four legacy dashboard fields
    assert _CONTRACT_KEYS.issubset(res.keys())  # plus the richer Sentinel superset
    assert res["confidence"] == res["fault_confidence"]  # documented alias


# --- adapter specifics ------------------------------------------------------

def test_empty_history_degrades_safely(models_dir):
    res = assess_live([], station_id="DL-001", engine=_engine(models_dir))
    assert res["anomaly_score"] is None
    assert res["severity"] == "UNKNOWN"
    assert res["fault_type"] == "NORMAL"
    assert res["data_complete"] is False
    assert res["n_history"] == 0
    json.dumps(res, allow_nan=False)


def test_camelcase_windspeed_alias_mapped(synthetic_frame):
    hist = _history_dicts(synthetic_frame, "AAA", 5)  # points carry ``windSpeed``
    df = normalize_live_history(hist, station_id="AAA")
    assert "wind_speed" in df.columns
    assert df["wind_speed"].notna().all()       # camelCase key was picked up
    assert df["station_id"].eq("AAA").all()      # per-call id applied to every row


def test_missing_value_not_fabricated(synthetic_frame):
    hist = _history_dicts(synthetic_frame, "AAA", 5)
    hist[-1]["pressure"] = None
    df = normalize_live_history(hist, station_id="AAA")
    # a missing reading stays NaN -- never imputed, zero-filled or invented
    assert math.isnan(df["pressure"].iloc[-1])
    assert df["pressure"].iloc[:-1].notna().all()


def test_rows_without_timestamp_dropped_and_sorted(synthetic_frame):
    hist = _history_dicts(synthetic_frame, "AAA", 5)
    hist.append({"temperature": 25.0, "humidity": 50.0, "pressure": 1010.0})  # no ts
    df = normalize_live_history(hist, station_id="AAA")
    assert len(df) == 5                          # the timestamp-less row was dropped
    assert df["timestamp"].is_monotonic_increasing


def test_baseline_source_station_specific_vs_global(models_dir, synthetic_frame):
    eng = _engine(models_dir)
    hist = _history_dicts(synthetic_frame, "AAA", 50)
    # AAA is in the (temp-)trained baselines -> station-specific
    assert assess_live(hist, station_id="AAA", engine=eng)["baseline_source"] == "station_specific"
    # a live location the model never trained on falls back to global climatology
    assert assess_live(hist, station_id="DL-001", engine=eng)["baseline_source"] == "global_fallback"
    assert baseline_source("AAA", eng.baselines) == "station_specific"
    assert baseline_source("DL-001", eng.baselines) == "global_fallback"
