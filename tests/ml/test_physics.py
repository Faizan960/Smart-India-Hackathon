"""Thermodynamic feature tests (spec section 9)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml.pipeline import physics


def test_saturation_vapor_pressure_reference():
    # es(0 C) is a well-known reference value.
    assert physics.saturation_vapor_pressure(0.0) == pytest.approx(6.1094)
    # monotonically increasing in temperature
    assert physics.saturation_vapor_pressure(30.0) > physics.saturation_vapor_pressure(10.0)


def test_dewpoint_rh_roundtrip():
    t = np.array([25.0, 10.0, 35.0])
    rh = np.array([40.0, 80.0, 55.0])
    dp = physics.rh_to_dewpoint(t, rh)
    rh_back = physics.dewpoint_to_rh(t, dp)
    assert np.allclose(rh_back, rh, atol=0.5)
    # dew point is always at/below air temperature for sub-saturated air
    assert np.all(dp <= t + 1e-6)


def test_vpd_nonnegative_and_zero_at_saturation():
    assert physics.vapor_pressure_deficit(20.0, 100.0) == pytest.approx(0.0, abs=1e-9)
    assert physics.vapor_pressure_deficit(20.0, 50.0) > 0.0


def test_thermo_features_consistent_data_has_no_flag():
    df = pd.DataFrame({"temperature": [25.0, 30.0], "humidity": [40.0, 55.0]})
    out = physics.thermodynamic_features(df)
    assert not out["thermo_inconsistency"].any()
    assert (out["thermo_inconsistency_score"] <= 1e-6).all()
    assert (out["vpd"] >= 0).all()


def test_thermo_features_flags_supersaturation():
    # RH well above 100% is physically inconsistent and must be flagged with a
    # positive inconsistency score (never silently accepted).
    df = pd.DataFrame({"temperature": [20.0], "humidity": [140.0]})
    out = physics.thermodynamic_features(df)
    assert bool(out["thermo_inconsistency"].iloc[0]) is True
    assert out["thermo_inconsistency_score"].iloc[0] > 0.0


def test_thermo_features_nan_safe():
    df = pd.DataFrame({"temperature": [np.nan, 20.0], "humidity": [50.0, np.nan]})
    out = physics.thermodynamic_features(df)
    assert out["vpd"].isna().all()
    assert not out["thermo_inconsistency"].any()
