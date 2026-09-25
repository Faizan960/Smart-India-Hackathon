"""Interval-aware feature engineering tests (spec sections 7-10)."""
from __future__ import annotations

import numpy as np

from ml.pipeline.config import CORE_SENSORS, DEFAULT_CONFIG
from ml.pipeline.features import build_features, to_model_matrix


def test_build_features_has_all_model_columns(feat_all):
    for col in DEFAULT_CONFIG.if_features:
        assert col in feat_all.columns, f"missing engineered feature: {col}"


def test_features_sorted_by_station_then_time(feat_all):
    # concat is per-station; within each station timestamps must be ascending
    for _sid, g in feat_all.groupby("station_id"):
        ts = g["timestamp"].to_numpy()
        assert np.all(ts[:-1] <= ts[1:])


def test_to_model_matrix_shape_and_finiteness(feat_all):
    X, complete = to_model_matrix(feat_all)
    assert X.shape[0] == len(feat_all)
    assert X.shape[1] == len(DEFAULT_CONFIG.if_features)
    # engineered NaN/inf are neutralised to 0.0 before the model ever sees them
    assert np.isfinite(X.to_numpy()).all()
    # clean synthetic data is fully complete
    assert complete.all()


def test_to_model_matrix_marks_incomplete_rows(synthetic_frame, baselines):
    df = synthetic_frame.copy()
    df.loc[df.index[0], "humidity"] = np.nan
    feat = build_features(df, baselines=baselines)
    _X, complete = to_model_matrix(feat)
    # exactly the rows missing a raw core sensor are flagged incomplete
    n_missing = int(feat[list(CORE_SENSORS)].isna().any(axis=1).sum())
    assert (~complete).sum() == n_missing
    assert n_missing >= 1


def test_to_model_matrix_missing_column_raises(feat_all):
    import pytest
    bad = feat_all.drop(columns=["vpd"])
    with pytest.raises(KeyError):
        to_model_matrix(bad)


def test_rates_are_finite_mid_series(feat_all):
    # rate-of-change is undefined at the first row of each station but finite after
    g = feat_all[feat_all["station_id"] == "AAA"].reset_index(drop=True)
    assert np.isfinite(g["temp_rate"].iloc[1:]).mean() > 0.9
