"""Laya typed-contract adapter tests (spec section 18)."""
from __future__ import annotations

import importlib.util

import numpy as np
import pandas as pd
import pytest

from ml.pipeline.laya_adapter import (
    fuse_with_detector,
    laya_questions,
    pipeline_decision,
    run_laya,
    to_laya_state,
)


def _assessment(**kw):
    base = dict(legacy_label="TEMPERATURE_SPIKE", fault_confidence=0.8,
                fault_present=0.7, fault_type="TRANSIENT_SPIKE",
                severity="WARNING", reasons=["classifier: transient spike"])
    base.update(kw)
    return base


def test_pipeline_decision_maps_typed_primitives():
    d = pipeline_decision(_assessment())
    assert d.decision == "TEMPERATURE_SPIKE"      # legacy_label -> typed choice
    assert d.confidence == 0.8                     # -> choice confidence
    assert d.fault_present == 0.7                  # -> noul
    # tagged pipeline-sourced so it is never misread as the Laya model's output
    assert d.raw["source"] == "aws_sentinel_pipeline"
    assert d.raw["fault_type"] == "TRANSIENT_SPIKE"


def test_pipeline_decision_coerces_unknown_labels():
    anomalous = pipeline_decision(_assessment(legacy_label="NOT_A_REAL_LABEL",
                                              fault_type="UNKNOWN_ANOMALY"))
    assert anomalous.decision == "UNKNOWN_ANOMALY"
    normal = pipeline_decision(_assessment(legacy_label="NOT_A_REAL_LABEL",
                                           fault_type="NORMAL"))
    assert normal.decision == "NORMAL"


def test_fuse_with_detector_never_averages():
    normal = pipeline_decision(_assessment(legacy_label="NORMAL", fault_type="NORMAL"))
    # a NORMAL typed decision stays NORMAL even if the detector fired
    v = fuse_with_detector(normal, {"is_anomaly": True, "anomaly_score": 0.95})
    assert v["verification_status"] == "NORMAL"

    spike = pipeline_decision(_assessment())
    confirmed = fuse_with_detector(spike, {"is_anomaly": True, "anomaly_score": 0.9})
    unverified = fuse_with_detector(spike, {"is_anomaly": False, "anomaly_score": 0.1})
    assert confirmed["verification_status"] == "CONFIRMED"
    assert unverified["verification_status"] == "UNVERIFIED"
    # the IF score is passed through verbatim, never blended into the Laya score
    assert confirmed["isolation_forest_score"] == 0.9
    assert confirmed["laya_fault_probability"] == 0.7


def test_to_laya_state_satisfies_existing_contract():
    # a canonical frame WITHOUT the auxiliary wind_speed column must still shape
    # into the existing Laya state (the adapter supplies wind_speed as null).
    hist = pd.DataFrame({
        "timestamp": pd.date_range("2021-06-01", periods=5, freq="1h"),
        "temperature": np.linspace(20, 24, 5),
        "humidity": np.linspace(40, 50, 5),
        "pressure": np.linspace(1010, 1012, 5),
    })
    state = to_laya_state(hist)
    assert state["task"] == "automatic_weather_station_sensor_fault_detection"
    assert len(state["recent_observations"]) == 5
    assert state["current_observation"]["wind_speed"] is None
    assert "expected_fault_labels" in state


def test_laya_questions_are_typed_choice_and_noul():
    q = laya_questions()
    assert q["fault_type"]["type"] == "choice"
    assert q["fault_present"]["type"] == "noul"
    assert "NORMAL" in q["fault_type"]["criteria"]


def test_run_laya_fails_honestly_without_checkpoint():
    if importlib.util.find_spec("laya") is not None:  # pragma: no cover
        pytest.skip("laya is installed; the honest-failure path is not exercised")
    hist = pd.DataFrame({
        "timestamp": pd.date_range("2021-06-01", periods=3, freq="1h"),
        "temperature": [20.0, 21.0, 22.0], "humidity": [40.0, 41.0, 42.0],
        "pressure": [1010.0, 1011.0, 1012.0],
    })
    with pytest.raises(RuntimeError):
        run_laya(hist)
