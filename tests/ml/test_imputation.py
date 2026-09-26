"""Gap imputation tests (spec section 21)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml.pipeline.config import DEFAULT_CONFIG
from ml.pipeline.imputation import impute_gaps


def _frame():
    n = 12
    ts = pd.date_range("2021-06-01", periods=n, freq="1h")
    temperature = np.linspace(20.0, 31.0, n)   # step 1.0 per hour
    temperature[3] = np.nan                    # short interior gap (2 rows / 3h span)
    temperature[4] = np.nan
    humidity = np.linspace(40.0, 51.0, n)
    humidity[0] = np.nan                        # leading gap -> must stay NaN
    pressure = np.linspace(1010.0, 1021.0, n)
    pressure[2:10] = np.nan                     # 8-row / 9h interior gap -> too long
    return pd.DataFrame({
        "timestamp": ts, "station_id": "S",
        "temperature": temperature, "humidity": humidity, "pressure": pressure,
    })


def test_short_interior_gap_is_filled_linearly_and_flagged():
    out, report = impute_gaps(_frame())
    assert out["temperature_imputed"].iloc[[3, 4]].all()
    # linear-in-time between temp[2]=22 and temp[5]=25 -> 23, 24
    assert out["temperature"].iloc[3] == pytest.approx(23.0, abs=1e-6)
    assert out["temperature"].iloc[4] == pytest.approx(24.0, abs=1e-6)
    assert report["temperature"] == 2


def test_leading_and_long_gaps_are_left_untouched():
    out, report = impute_gaps(_frame())
    # leading NaN is never fabricated
    assert np.isnan(out["humidity"].iloc[0])
    assert not out["humidity_imputed"].iloc[0]
    assert report["humidity"] == 0
    # an over-long interior gap remains a visible dropout, not silently filled
    assert out["pressure"].iloc[2:10].isna().all()
    assert not out["pressure_imputed"].iloc[2:10].any()
    assert report["pressure"] == 0


def test_report_is_auditable():
    _out, report = impute_gaps(_frame())
    assert report["total_imputed"] == 2
    assert report["max_gap_hours"] == DEFAULT_CONFIG.impute_max_gap_hours
