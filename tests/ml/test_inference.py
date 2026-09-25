"""End-to-end runtime inference tests (spec section 36, phase 10).

Exercises SentinelInference against a detector trained and saved into a temp
models directory by the shared fixtures -- no committed artifacts required.
"""
from __future__ import annotations

import json

import numpy as np

from ml.pipeline.inference import SentinelInference

_SEVERITY = {"NORMAL", "WARNING", "CRITICAL"}
_STATUS = {"NORMAL", "CONFIRMED", "UNVERIFIED"}
_HEALTH = {"HEALTHY", "WATCH", "DEGRADED", "CRITICAL", "UNKNOWN"}


def test_predict_frame_columns_and_ranges(models_dir, synthetic_frame):
    eng = SentinelInference(models_dir=models_dir)
    out = eng.predict_frame(synthetic_frame)
    expected = {"station_id", "timestamp", "anomaly_score", "is_anomaly", "severity",
                "fused_status", "fault_type", "fault_confidence", "legacy_label",
                "fault_present", "structural_fault", "reasons", "health_status"}
    assert expected.issubset(out.columns)
    s = out["anomaly_score"].to_numpy(dtype=float)
    finite = s[np.isfinite(s)]
    assert finite.min() >= 0.0 and finite.max() <= 1.0
    assert set(out["severity"].unique()).issubset(_SEVERITY)
    assert set(out["fused_status"].unique()).issubset(_STATUS)
    assert set(out["health_status"].unique()).issubset(_HEALTH)
    # honest false-positive discipline: clean synthetic data is mostly NORMAL
    assert (out["severity"] == "NORMAL").mean() > 0.8


def test_predict_frame_explain_adds_explanation(models_dir, synthetic_frame):
    eng = SentinelInference(models_dir=models_dir)
    out = eng.predict_frame(synthetic_frame.head(200), explain=True)
    assert "explanation" in out.columns


def test_predict_observation_is_json_serializable(models_dir, synthetic_frame):
    eng = SentinelInference(models_dir=models_dir)
    hist = synthetic_frame[synthetic_frame["station_id"] == "AAA"]
    res = eng.predict_observation(hist)
    for k in ("station_id", "timestamp", "anomaly_score", "severity", "fault_type",
              "fused_status", "reasons", "explanation", "laya_decision",
              "verification", "health"):
        assert k in res
    # the Laya-typed decision is explicitly pipeline-sourced, never the model's own
    assert res["laya_decision"]["source"] == "aws_sentinel_pipeline"
    assert res["verification"]["verification_status"] in _STATUS
    # the whole result must round-trip through strict JSON (a runtime API contract)
    json.dumps(res)
