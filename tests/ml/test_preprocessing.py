"""Quality-control + leakage-free chronological split tests (spec sections 4 & 5)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ml.pipeline.preprocessing import (
    chronological_split,
    infer_sampling_seconds,
    run_quality_control,
    split_bounds,
)


def test_infer_sampling_seconds_hourly():
    ts = pd.Series(pd.date_range("2021-01-01", periods=48, freq="1h"))
    assert infer_sampling_seconds(ts) == 3600.0


def test_chronological_split_is_leakage_free(synthetic_frame):
    train, val, test = chronological_split(synthetic_frame)
    # every split is non-empty and the union reconstructs the input
    assert len(train) and len(val) and len(test)
    assert len(train) + len(val) + len(test) == len(synthetic_frame)
    # strict temporal ordering: no future row ever leaks into an earlier split
    assert train["timestamp"].max() < val["timestamp"].min()
    assert val["timestamp"].max() < test["timestamp"].min()


def test_chronological_split_fractions(synthetic_frame):
    train, val, test = chronological_split(synthetic_frame)
    frac = len(train) / len(synthetic_frame)
    assert 0.6 < frac < 0.8  # ~0.70 by construction
    t_end, v_end = split_bounds(synthetic_frame)
    assert t_end <= v_end


def test_qc_flags_without_mutating_values(synthetic_frame):
    df = synthetic_frame.copy()
    # inject a missing value and an out-of-range value
    df.loc[df.index[0], "temperature"] = np.nan
    df.loc[df.index[1], "pressure"] = 5000.0  # far above SENSOR_BOUNDS
    out, summary = run_quality_control(df)
    assert summary["q_missing"] >= 1
    assert summary["q_out_of_range"] >= 1
    assert set(("q_missing", "q_out_of_range", "q_gap", "q_any")).issubset(out.columns)
    # QC annotates, it never alters observed values: the non-null pressure set is
    # preserved (same multiset of values, modulo the ones we deliberately changed).
    orig_valid = np.sort(df["pressure"].dropna().to_numpy())
    out_valid = np.sort(out["pressure"].dropna().to_numpy())
    assert np.array_equal(orig_valid, out_valid)


def test_qc_detects_duplicate_timestamp(synthetic_frame):
    df = synthetic_frame.copy()
    dup = df.iloc[[0]].copy()
    df = pd.concat([df, dup], ignore_index=True)
    _out, summary = run_quality_control(df)
    assert summary["q_duplicate_ts"] >= 1
