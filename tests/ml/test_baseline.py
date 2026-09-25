"""Diurnal baseline tests (spec section 6)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ml.pipeline.baseline import (
    DEV_COLS,
    compute_baselines,
    deviation_features,
    load_baselines,
    save_baselines,
)
from ml.pipeline.config import DEFAULT_CONFIG


def test_baseline_structure_and_train_only(split):
    train, _val, _test = split
    b = compute_baselines(train)
    assert set(("meta", "smh", "sm", "s", "global")).issubset(b)
    assert b["meta"]["n_train_rows"] == len(train)
    assert b["meta"]["keys"] == ["station_id", "month", "hour"]
    for sensor in ("temperature", "humidity", "pressure"):
        assert "median" in b["global"][sensor] and "sigma" in b["global"][sensor]


def test_deviation_zero_at_median_large_when_offset(split, baselines):
    train, _val, _test = split
    out = deviation_features(train, baselines)
    # a value equal to its own climatological median deviates ~0
    assert np.nanmedian(np.abs(out[DEV_COLS["temperature"]])) < 3.0
    # deviations are clipped to the configured z-score range
    for col in DEV_COLS.values():
        assert out[col].abs().max() <= DEFAULT_CONFIG.zscore_clip + 1e-9


def test_deviation_flags_a_large_offset(split, baselines):
    train, _val, _test = split
    df = train.copy()
    # push one row's temperature far from any plausible normal
    df.loc[df.index[0], "temperature"] = 200.0
    out = deviation_features(df, baselines)
    assert out[DEV_COLS["temperature"]].iloc[0] == DEFAULT_CONFIG.zscore_clip


def test_baseline_save_load_roundtrip(tmp_path, baselines):
    p = save_baselines(baselines, tmp_path / "baselines.json")
    loaded = load_baselines(p)
    assert loaded["meta"]["n_train_rows"] == baselines["meta"]["n_train_rows"]
    assert loaded["global"]["temperature"]["median"] == \
        baselines["global"]["temperature"]["median"]


def test_baseline_is_deterministic(split):
    train, _val, _test = split
    b1 = compute_baselines(train)
    b2 = compute_baselines(train)
    assert b1["global"] == b2["global"]
    assert b1["smh"]["temperature"]["median"] == b2["smh"]["temperature"]["median"]
