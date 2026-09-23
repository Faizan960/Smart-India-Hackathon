"""Isolation Forest detector + calibration tests (spec section 11)."""
from __future__ import annotations

import numpy as np

from ml.pipeline.anomaly_detector import AnomalyDetector
from ml.pipeline.config import DEFAULT_CONFIG
from ml.pipeline.features import build_features, to_model_matrix


def test_scores_bounded_and_incomplete_are_nan(synthetic_frame, baselines, detector):
    df = synthetic_frame.copy()
    df.loc[df.index[5], "pressure"] = np.nan
    feat = build_features(df, baselines=baselines)
    scored = detector.score(feat)
    s = scored["anomaly_score"].to_numpy(dtype=float)
    finite = s[np.isfinite(s)]
    assert finite.min() >= 0.0 and finite.max() <= 1.0
    # a row missing a raw core sensor is never scored (honest: not zero-filled)
    incomplete = ~scored["core_complete"].to_numpy()
    assert np.isnan(s[incomplete]).all()
    assert incomplete.sum() >= 1


def test_calibration_anchored_on_training_distribution(feat_train, detector):
    X, complete = to_model_matrix(feat_train)
    Xs = detector.scaler.transform(X[complete])
    raw = -detector.model.decision_function(Xs)
    center = float(np.percentile(raw, DEFAULT_CONFIG.calib_center_pct))
    # the logistic centre is exactly the configured TRAINING percentile (not tuned)
    assert detector.calibration["center"] == center
    # => about (100 - center_pct)% of training rows score at/above 0.5
    scored = detector.score(feat_train)
    frac_hot = float((scored["anomaly_score"] >= 0.5).mean())
    assert 0.02 <= frac_hot <= 0.10


def test_score_is_monotonic_in_raw(feat_train, detector):
    X, complete = to_model_matrix(feat_train)
    Xs = detector.scaler.transform(X[complete])
    raw = -detector.model.decision_function(Xs)
    from ml.pipeline.anomaly_detector import _sigmoid
    score = _sigmoid((raw - detector.calibration["center"]) / detector.calibration["scale"])
    order = np.argsort(raw)
    s_sorted = score[order]
    assert np.all(np.diff(s_sorted) >= -1e-9)  # non-decreasing


def test_is_anomaly_uses_warning_threshold(feat_all, detector):
    scored = detector.score(feat_all)
    s = scored["anomaly_score"]
    flagged = scored["is_anomaly"]
    expected = (s >= DEFAULT_CONFIG.severity_warning_score).fillna(False)
    assert flagged.equals(expected)


def test_save_load_roundtrip_identical_scores(tmp_path, detector, feat_all):
    detector.save(tmp_path)
    loaded = AnomalyDetector.load(tmp_path)
    a = detector.score(feat_all)["anomaly_score"].to_numpy(dtype=float)
    b = loaded.score(feat_all)["anomaly_score"].to_numpy(dtype=float)
    assert np.allclose(a, b, equal_nan=True)
    assert loaded.features == detector.features
